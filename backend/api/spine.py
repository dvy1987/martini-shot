"""Spine HTTP: projects, jobs, ingest upload, SSE (spec §7, gate G1)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, PositiveInt

from backend.api.events import EventHub
from backend.api.present import approval_to_api, job_to_api, project_to_api
from backend.approvals.machine import (
    APPROVALS,
    ApprovalConflict,
    ApprovalNotFound,
    ApprovalStateMachine,
    propose_approval,
)
from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.jobs.models import Job, utc_now_iso
from backend.jobs.queue import FirestoreLeaseQueue
from backend.shots import lifecycle as shots
from backend.stations.ingest.run import STATION
from backend.supervisor import budget_loop
from backend.supervisor.deliberation import DELIBERATIONS

log = logging.getLogger("pc.api")
PROJECTS = "pc-projects"
REPORTS = "pc-morning-reports"


class DecisionIn(BaseModel):
    decision: str
    reason: str | None = Field(default=None)


class ShotActionIn(BaseModel):
    """Optional body for lock/unlock proposals — only a reason, no decision
    (the decision happens when the approval is approved)."""

    reason: str | None = Field(default=None)


class ExtendIn(BaseModel):
    """Body for an extend proposal (D-9): which stored artifact to extend
    and why. The render is queued only when the approval is approved."""

    source_uri: str
    reason: str | None = Field(default=None)
    prompt: str | None = Field(default=None)


class CorrectIn(BaseModel):
    source_uri: str
    intent: str
    reason: str | None = Field(default=None)
    protected_subjects: list[str] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    consult_agent: bool = True


class RelightIn(BaseModel):
    source_uri: str
    preset: str
    reason: str | None = Field(default=None)


class CoverageIn(BaseModel):
    source_uri: str
    angle: str
    intent: str
    reference_uris: list[str]
    reason: str | None = Field(default=None)


class CameraLanguageIn(BaseModel):
    source_uri: str
    movement: str
    reference_style: str | None = Field(default=None)
    reason: str | None = Field(default=None)


class RenderMasterIn(BaseModel):
    op: str
    source_uri: str | None = Field(default=None)
    reason: str | None = Field(default=None)
    intent: str | None = Field(default=None)
    preset: str | None = Field(default=None)
    angle: str | None = Field(default=None)
    movement: str | None = Field(default=None)


class ScriptVersionIn(BaseModel):
    text: str
    based_on_version_id: str | None = Field(default=None)
    consult_agent: bool = True


class RegenerateSpansIn(BaseModel):
    spans: list[dict[str, Any]]
    reason: str | None = Field(default=None)


class SettingsIn(BaseModel):
    """Partial body for PATCH /settings (H-0b round-trip): the autonomy
    toggle and the nightly envelope. Only provided fields move."""

    autonomy: Literal["propose_only", "retry_once", "act"] | None = Field(default=None)
    post_command_budget_micros: PositiveInt | None = Field(default=None)


def _shot_project(store: FirestoreStore, shot_id: str) -> str:
    doc = shots.get_shot(store, shot_id) or {}
    return str(doc.get("project_id") or "")


def _grafana_annotator(settings: Settings):
    """Real MCP annotation per approval transition (C-4.3). Heavy by design:
    one connector per call, same pattern as the worker's annotate_job."""

    def annotate(text: str, tags: list[str]) -> dict[str, Any]:
        from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config

        with GrafanaMcpConnector(build_server_config(settings)) as connector:
            return connector.add_annotation(text, tags=tags)

    return annotate


def install_spine_routes(
    app: FastAPI,
    *,
    queue: FirestoreLeaseQueue,
    store: FirestoreStore,
    gcs: GCSMedia,
    hub: EventHub,
    settings: Settings | None = None,
    machine: ApprovalStateMachine | None = None,
    settings_token_verifier: Any | None = None,
) -> None:
    # One machine instance serves the HTTP API, the worker hook and the
    # sweeper; single-writer is the MODULE, instances share its transactions.
    machine = machine or ApprovalStateMachine(
        store,
        queue=queue,
        hub=hub,
        annotator=_grafana_annotator(settings) if settings is not None else None,
    )

    @app.get("/api/v1/projects")
    def list_projects() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for snap in store.client.collection(PROJECTS).stream():
            doc = snap.to_dict() or {}
            project_id = doc.get("project_id") or snap.id
            jobs = queue.list_for_project(project_id)
            out.append(
                project_to_api(
                    project_id=project_id,
                    title=str(doc.get("title") or project_id),
                    created_at=str(doc.get("created_at") or utc_now_iso()),
                    jobs=jobs,
                )
            )
        out.sort(key=lambda row: str(row.get("created_at") or ""))
        return out

    @app.get("/api/v1/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        doc = store.get_doc(PROJECTS, project_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no such project")
        jobs = queue.list_for_project(project_id)
        return project_to_api(
            project_id=project_id,
            title=str(doc.get("title") or project_id),
            created_at=str(doc.get("created_at") or utc_now_iso()),
            jobs=jobs,
        )

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = queue.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such job")
        return job_to_api(job)

    @app.post("/api/v1/projects/{project_id}/ingest")
    async def ingest_clip(
        project_id: str, file: Annotated[UploadFile, File()]
    ) -> dict[str, Any]:
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="file name required",
            )
        payload = await file.read()
        if not payload:
            raise HTTPException(
                status_code=400,
                detail="empty file",
            )
        from backend.stations.spend.control import is_intake_paused

        if is_intake_paused(store, STATION):
            raise HTTPException(
                status_code=429,
                detail="intake paused by Spend Control",
            )
        job = Job(station=STATION, project_id=project_id, input_refs=[])
        key = f"projects/{project_id}/ingest/{job.id}/{file.filename}"
        gcs.upload_bytes(key, payload, content_type=file.content_type or "video/mp4")
        job.input_refs = [key]
        if store.get_doc(PROJECTS, project_id) is None:
            store.set_doc(
                PROJECTS,
                project_id,
                {
                    "project_id": project_id,
                    "title": "Gate G1" if project_id == "g1" else project_id,
                    "created_at": utc_now_iso(),
                },
            )
        queue.submit(job)
        hub.publish(project_id, "job.updated", {"job": job_to_api(job)})
        log.info(
            "ingest accepted",
            extra={
                "job_id": job.id,
                "station": STATION,
                "project_id": project_id,
            },
        )
        return job_to_api(job)

    @app.get("/api/v1/approvals")
    def list_approvals() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for snap in store.client.collection(APPROVALS).stream():
            doc = snap.to_dict() or {}
            if not doc.get("approval_id"):
                doc["approval_id"] = snap.id
            rows.append(approval_to_api(doc))
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
        return rows

    @app.post("/api/v1/approvals/{approval_id}/decision")
    def decide_approval(approval_id: str, body: DecisionIn) -> dict[str, Any]:
        # Input validation (400) beats resource lookup (404) — contract order.
        if body.decision not in {"approve", "reject"}:
            raise HTTPException(
                status_code=400, detail="decision must be approve or reject"
            )
        try:
            merged = machine.dispatch(
                approval_id,
                body.decision,
                approver="dev",
                reason=body.reason or "",
            )
        except ApprovalNotFound:
            raise HTTPException(status_code=404, detail="no such approval") from None
        except ApprovalConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return approval_to_api(merged)

    @app.get("/api/v1/projects/{project_id}/reports/morning")
    def morning_report(project_id: str, date: str) -> dict[str, Any]:
        doc = store.get_doc(REPORTS, f"{project_id}:{date}")
        if doc is None:
            raise HTTPException(status_code=404, detail="no morning report")
        return {
            "date": str(doc.get("date") or date),
            "generated_at": str(doc.get("generated_at") or utc_now_iso()),
            "verdicts": list(doc.get("verdicts") or []),
        }

    # -- H-1f: agent deliberations (real pc-deliberations docs) ----------------
    @app.get("/api/v1/projects/{project_id}/deliberations")
    def list_project_deliberations(
        project_id: str, job_id: str | None = None
    ) -> list[dict[str, Any]]:
        rows = store.list_where(DELIBERATIONS, "project_id", project_id)
        if job_id:
            rows = [
                row
                for row in rows
                if str((row.get("trigger") or {}).get("job_id") or "") == job_id
            ]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return [
            {
                "cycle_id": str(row.get("cycle_id") or ""),
                "case_id": str(row.get("case_id") or ""),
                "created_at": str(row.get("created_at") or ""),
                "trigger": dict(row.get("trigger") or {}),
                "specialists": list(row.get("specialists") or []),
                "verdict": dict(row.get("verdict") or {}),
                "recommendation": dict(row.get("recommendation") or {}),
                "status": str(row.get("status") or ""),
            }
            for row in rows
        ]

    # -- AL-1: shots, alternates, locks ---------------------------------------

    def _alternate_rows(shot_id: str) -> list[dict[str, Any]]:
        rows = shots.list_alternates(store, shot_id)
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
        return [
            {
                "alternate_id": str(row.get("alternate_id") or row.get("id")),
                "op": row.get("op"),
                "artifact_ref": row.get("artifact_ref"),
                "eval_scores": row.get("eval_scores"),
                "tier": row.get("tier") or "draft",
                "status": row.get("status"),
                "draft_state": row.get("draft_state"),
                "visual_qc": row.get("visual_qc"),
                "cost_delta_micros": row.get("cost_delta_micros"),
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]

    @app.get("/api/v1/projects/{project_id}/shots")
    def list_project_shots(project_id: str) -> list[dict[str, Any]]:
        rows = store.list_where(shots.SHOTS, "project_id", project_id)
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
        # Alternates are embedded so the FE lane needs one call, not N+1.
        return [
            {
                "shot_id": str(row.get("shot_id") or row.get("id")),
                "title": row.get("title"),
                "locked": bool(row.get("locked")),
                "locked_by": row.get("locked_by"),
                "current_alternate_id": row.get("current_alternate_id"),
                "created_at": row.get("created_at"),
                "scene_understanding": row.get("scene_understanding"),
                "alternates": _alternate_rows(str(row.get("shot_id") or row.get("id"))),
            }
            for row in rows
        ]

    @app.get("/api/v1/shots/{shot_id}")
    def get_shot_detail(shot_id: str) -> dict[str, Any]:
        doc = shots.get_shot(store, shot_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no such shot")
        return {
            "shot_id": shot_id,
            "project_id": doc.get("project_id"),
            "title": doc.get("title"),
            "locked": bool(doc.get("locked")),
            "locked_by": doc.get("locked_by"),
            "current_alternate_id": doc.get("current_alternate_id"),
            "scene_understanding": doc.get("scene_understanding"),
            "alternates": _alternate_rows(shot_id),
        }

    @app.post("/api/v1/shots/{shot_id}/lock")
    def propose_lock(shot_id: str, body: ShotActionIn | None = None) -> dict[str, Any]:
        """Locking is approval-tracked through H-0 — the API proposes, the
        executor acts (single-writer)."""
        if shots.get_shot(store, shot_id) is None:
            raise HTTPException(status_code=404, detail="no such shot")
        approval_id = propose_approval(
            store,
            {
                "project_id": _shot_project(store, shot_id),
                "kind": "fix",
                "title": f"Lock shot {shot_id}",
                "detail": (body.reason if body else "") or "",
                "command": {"name": "lock_shot", "args": {"shot_id": shot_id}},
            },
        )
        return {"approval_id": approval_id, "status": "proposed"}

    @app.post("/api/v1/shots/{shot_id}/unlock")
    def propose_unlock(
        shot_id: str, body: ShotActionIn | None = None
    ) -> dict[str, Any]:
        if shots.get_shot(store, shot_id) is None:
            raise HTTPException(status_code=404, detail="no such shot")
        approval_id = propose_approval(
            store,
            {
                "project_id": _shot_project(store, shot_id),
                "kind": "fix",
                "title": f"Unlock shot {shot_id}",
                "detail": (body.reason if body else "") or "",
                "command": {"name": "unlock_shot", "args": {"shot_id": shot_id}},
            },
        )
        return {"approval_id": approval_id, "status": "proposed"}

    @app.post("/api/v1/shots/{shot_id}/extend")
    def propose_extend(shot_id: str, body: ExtendIn) -> dict[str, Any]:
        """D-9: propose an Omni scene-extend. Approval-tracked through H-0;
        the approved command enqueues a real `extend` job whose render lands
        as a DRAFT alternate (never an overwrite)."""
        if shots.get_shot(store, shot_id) is None:
            raise HTTPException(status_code=404, detail="no such shot")
        if not body.source_uri.startswith("gs://"):
            raise HTTPException(
                status_code=400, detail="source_uri must be a gs:// URI"
            )
        project_id = _shot_project(store, shot_id)
        approval_id = propose_approval(
            store,
            {
                "project_id": project_id,
                "kind": "fix",
                "title": f"Extend shot {shot_id}",
                "detail": body.reason or "",
                "command": {
                    "name": "extend_shot",
                    "args": {
                        "shot_id": shot_id,
                        "project_id": project_id,
                        "source_uri": body.source_uri,
                        **({"prompt": body.prompt} if body.prompt else {}),
                    },
                },
            },
        )
        return {"approval_id": approval_id, "status": "proposed"}

    def _require_source(uri: str) -> str:
        if not uri.startswith("gs://"):
            raise HTTPException(
                status_code=400, detail="source_uri must be a gs:// URI"
            )
        return uri

    def _propose_shot_command(
        shot_id: str, *, name: str, title: str, detail: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        if shots.get_shot(store, shot_id) is None:
            raise HTTPException(status_code=404, detail="no such shot")
        project_id = _shot_project(store, shot_id)
        approval_id = propose_approval(
            store,
            {
                "project_id": project_id,
                "kind": "fix",
                "title": title,
                "detail": detail,
                "command": {
                    "name": name,
                    "args": {"shot_id": shot_id, "project_id": project_id, **args},
                },
            },
        )
        return {"approval_id": approval_id, "status": "proposed"}

    @app.post("/api/v1/shots/{shot_id}/correct")
    def propose_correct(shot_id: str, body: CorrectIn) -> dict[str, Any]:
        """D-10: propose a bounded Omni correction. The Corrections Agent
        judges the brief first (abstain on locked/ambiguous/injection);
        H-0 still executes. Output is always a draft alternate."""
        shot = shots.get_shot(store, shot_id)
        if shot is None:
            raise HTTPException(status_code=404, detail="no such shot")
        intent = body.intent.strip()
        if not intent:
            raise HTTPException(
                status_code=400, detail="correction requires explicit intent"
            )
        source_uri = _require_source(body.source_uri)
        locked = bool(shot.get("locked"))
        brief = {
            "intent": intent,
            "protected_subjects": body.protected_subjects,
            "continuity_constraints": body.continuity_constraints,
            "locked": locked,
            "shot_id": shot_id,
            "project_id": _shot_project(store, shot_id),
            "source_uri": source_uri,
        }
        agent_rationale = body.reason or intent
        agent_decision = "propose_correction"
        agent_cost_micros = 0
        from backend.supervisor.station_agents.corrections import suggestion_for_brief

        if suggestion_for_brief(brief) == "abstain":
            raise HTTPException(
                status_code=409,
                detail="correction refused: locked, ambiguous, or injective brief",
            )
        if body.consult_agent and settings is not None:
            from backend.supervisor.station_agents.corrections import decide_corrections

            decision, agent_cost_micros = decide_corrections(settings, brief=brief)
            agent_rationale = decision.reason
            agent_decision = decision.decision
            if decision.decision == "abstain":
                raise HTTPException(status_code=409, detail=decision.reason)
        proposed = _propose_shot_command(
            shot_id,
            name="correct_shot",
            title=f"Correct shot {shot_id}",
            detail=agent_rationale,
            args={
                "source_uri": source_uri,
                "intent": intent,
                "protected_subjects": body.protected_subjects,
                "continuity_constraints": body.continuity_constraints,
            },
        )
        return {
            **proposed,
            "agent": {
                "name": "corrections",
                "decision": agent_decision,
                "rationale": agent_rationale,
                "cost_micros": agent_cost_micros,
            },
        }

    @app.post("/api/v1/shots/{shot_id}/relight")
    def propose_relight(shot_id: str, body: RelightIn) -> dict[str, Any]:
        return _propose_shot_command(
            shot_id,
            name="relight_shot",
            title=f"Relight shot {shot_id}",
            detail=body.reason or body.preset,
            args={
                "source_uri": _require_source(body.source_uri),
                "preset": body.preset,
            },
        )

    @app.post("/api/v1/shots/{shot_id}/coverage")
    def propose_coverage(shot_id: str, body: CoverageIn) -> dict[str, Any]:
        if not body.reference_uris:
            raise HTTPException(status_code=400, detail="reference_uris required")
        for uri in body.reference_uris:
            _require_source(uri)
        return _propose_shot_command(
            shot_id,
            name="generate_coverage",
            title=f"Coverage for shot {shot_id}",
            detail=body.reason or body.intent,
            args={
                "source_uri": _require_source(body.source_uri),
                "angle": body.angle,
                "intent": body.intent,
                "reference_uris": body.reference_uris,
            },
        )

    @app.post("/api/v1/shots/{shot_id}/camera-language")
    def propose_camera_language(shot_id: str, body: CameraLanguageIn) -> dict[str, Any]:
        args: dict[str, Any] = {
            "source_uri": _require_source(body.source_uri),
            "movement": body.movement,
        }
        if body.reference_style:
            args["reference_style"] = body.reference_style
        return _propose_shot_command(
            shot_id,
            name="apply_camera_language",
            title=f"Camera language for shot {shot_id}",
            detail=body.reason or body.movement,
            args=args,
        )

    @app.post("/api/v1/shots/{shot_id}/master")
    def propose_master(shot_id: str, body: RenderMasterIn) -> dict[str, Any]:
        args: dict[str, Any] = {"op": body.op}
        if body.source_uri:
            args["source_uri"] = _require_source(body.source_uri)
        for key in ("intent", "preset", "angle", "movement"):
            value = getattr(body, key)
            if value:
                args[key] = value
        return _propose_shot_command(
            shot_id,
            name="render_master",
            title=f"Master render for shot {shot_id}",
            detail=body.reason or body.op,
            args=args,
        )

    @app.get("/api/v1/projects/{project_id}/scripts")
    def list_scripts(project_id: str) -> list[dict[str, Any]]:
        from backend.revision import alignment as revision

        rows = store.list_where(revision.VERSIONS, "project_id", project_id)
        rows.sort(key=lambda row: int(row.get("version_number") or 0))
        return rows

    @app.post("/api/v1/projects/{project_id}/scripts")
    def create_script_version(project_id: str, body: ScriptVersionIn) -> dict[str, Any]:
        from backend.revision import alignment as revision
        from backend.revision.alignment import StaleVersionError

        try:
            version = revision.create_version(
                store,
                project_id=project_id,
                text=body.text,
                based_on_version_id=body.based_on_version_id,
            )
        except StaleVersionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        previous_id = body.based_on_version_id
        diffs: list[dict[str, Any]] = []
        affected: list[dict[str, Any]] = []
        agent_payload: dict[str, Any] | None = None
        alignment_cost = 0
        shot_rows = store.list_where(shots.SHOTS, "project_id", project_id)
        shot_bags = [
            {
                "shot_id": str(row.get("shot_id") or row.get("id") or ""),
                "spoken_words": (row.get("scene_understanding") or {}).get(
                    "spoken_words"
                )
                if isinstance(row.get("scene_understanding"), dict)
                else None,
                "scene": (row.get("scene_understanding") or {}).get("scene")
                if isinstance(row.get("scene_understanding"), dict)
                else None,
            }
            for row in shot_rows
            if str(row.get("shot_id") or row.get("id") or "")
        ]
        if body.consult_agent and settings is not None and shot_bags:
            from backend.supervisor.station_agents.revision_room import decide_alignment

            try:
                spans, alignment_cost = decide_alignment(
                    settings, script_text=body.text, shots=shot_bags
                )
                if spans:
                    revision.persist_alignment(
                        store, version_id=str(version["version_id"]), spans=spans
                    )
            except Exception:
                log.exception("revision alignment Gemini call failed")
        if previous_id:
            previous = store.get_doc(revision.VERSIONS, previous_id) or {}
            span_diffs = revision.diff_spans(str(previous.get("text") or ""), body.text)
            diffs = [
                {
                    "start": item.start,
                    "end": item.end,
                    "kind": item.kind,
                    "old_text": item.old_text,
                    "new_text": item.new_text,
                }
                for item in span_diffs
            ]
            alignment_spans = revision.get_alignment(store, str(version["version_id"]))
            if not alignment_spans:
                alignment_spans = revision.get_alignment(store, previous_id)
            affected = revision.affected_spans(span_diffs, alignment_spans)
            if body.consult_agent and settings is not None:
                from backend.supervisor.station_agents.revision_room import (
                    decide_revision_room,
                )

                try:
                    decision, cost = decide_revision_room(
                        settings,
                        old_text=str(previous.get("text") or ""),
                        new_text=body.text,
                        diffs=diffs,
                        affected=affected,
                    )
                    agent_payload = {
                        "name": "revision_room",
                        "decision": decision.decision,
                        "rationale": decision.reason,
                        "cost_micros": cost + alignment_cost,
                    }
                except Exception:
                    log.exception("revision impact Gemini call failed")
        payload = {**version, "diffs": diffs, "affected": affected}
        if agent_payload is not None:
            payload["agent"] = agent_payload
        return payload

    @app.post("/api/v1/projects/{project_id}/scripts/{version_id}/regenerate")
    def propose_regenerate(
        project_id: str, version_id: str, body: RegenerateSpansIn
    ) -> dict[str, Any]:
        from backend.revision import alignment as revision

        version = store.get_doc(revision.VERSIONS, version_id)
        if version is None or str(version.get("project_id")) != project_id:
            raise HTTPException(status_code=404, detail="no such script version")
        if not body.spans:
            raise HTTPException(status_code=400, detail="spans required")
        approval_id = propose_approval(
            store,
            {
                "project_id": project_id,
                "kind": "fix",
                "title": f"Regenerate spans for {version_id}",
                "detail": body.reason or "",
                "command": {
                    "name": "regenerate_affected_spans",
                    "args": {
                        "project_id": project_id,
                        "version_id": version_id,
                        "spans": body.spans,
                    },
                },
            },
        )
        return {"approval_id": approval_id, "status": "proposed"}

    @app.get("/api/v1/alternates/{alternate_id}/media")
    def alternate_media(alternate_id: str) -> dict[str, Any]:
        """Signed download URL for the FE player (spec §3) — real GCS V4
        signing, no public buckets."""
        alternate = store.get_doc(shots.ALTERNATES, alternate_id)
        if alternate is None:
            raise HTTPException(status_code=404, detail="no such alternate")
        artifact_ref = str(alternate.get("artifact_ref") or "")
        if not artifact_ref.startswith("gs://"):
            raise HTTPException(
                status_code=400, detail="alternate has no stored artifact"
            )
        key = artifact_ref.removeprefix("gs://").split("/", 1)[1]
        url = gcs.signed_download_url(key, expires_minutes=60)
        return {"alternate_id": alternate_id, "url": url, "expires_in_minutes": 60}

    # -- H-0b settings round-trip: autonomy toggle + nightly envelope -------

    def _require_owner(request: Request) -> None:
        """Google sign-in gate for owner-class writes (review round 2,
        finding 4). The verifier is injectable for tests; production uses
        real ID-token verification (google_auth.verify_owner_id_token)."""
        token = request.headers.get("X-Google-ID-Token") or ""
        if settings_token_verifier is not None:
            verifier = settings_token_verifier
        elif settings is not None:
            from backend.api.google_auth import verify_owner_id_token

            def verifier(tok: str) -> dict[str, Any]:
                return verify_owner_id_token(tok, settings)

        else:
            # No settings = no gate configuration = locked (fail closed).
            from backend.api.google_auth import GoogleTokenError

            raise GoogleTokenError("owner sign-in gate is not configured")

        try:
            verifier(token)
        except Exception as gate_error:
            from fastapi import HTTPException

            from backend.api.google_auth import GoogleAuthError, GoogleTokenNotOwner

            if isinstance(gate_error, GoogleTokenNotOwner):
                raise HTTPException(
                    status_code=403, detail="signed-in account is not the owner"
                ) from gate_error
            if isinstance(gate_error, GoogleAuthError):
                raise HTTPException(
                    status_code=401, detail="owner Google sign-in required"
                ) from gate_error
            # An unexpected verifier failure also refuses the write.
            raise HTTPException(
                status_code=401, detail="owner Google sign-in required"
            ) from gate_error

    def _settings_payload() -> dict[str, Any]:
        doc = store.get_doc(budget_loop.CONTROL, budget_loop.SETTINGS_DOC) or {}
        envelope = budget_loop.load_envelope_micros(store)
        return {
            "autonomy": budget_loop.load_autonomy_mode(store),
            # Echo the effective envelope even when the doc omits it, so the
            # UI shows the number the loop will actually use.
            "post_command_budget_micros": int(
                doc.get("post_command_budget_micros") or envelope
            ),
        }

    @app.get("/api/v1/settings")
    def get_settings_route() -> dict[str, Any]:
        return _settings_payload()

    @app.patch("/api/v1/settings")
    def patch_settings(body: SettingsIn, request: Request) -> dict[str, Any]:
        """One flip, no redeploy: the budgeted autonomy loop reads this same
        Firestore doc at cycle time (`budget_loop.load_autonomy_mode` /
        `load_envelope_micros`).

        Owner-gated (review round 2, finding 4): the API key identifies the
        machine, but settings decide what the AUTONOMOUS loop may do — the
        write requires a Google ID token proving the signer is the owner
        (header `X-Google-ID-Token`). Unconfigured gate = locked gate."""
        _require_owner(request)
        doc = store.get_doc(budget_loop.CONTROL, budget_loop.SETTINGS_DOC) or {}
        if body.autonomy is not None:
            doc["autonomy"] = body.autonomy
        if body.post_command_budget_micros is not None:
            doc["post_command_budget_micros"] = body.post_command_budget_micros
        store.set_doc(budget_loop.CONTROL, budget_loop.SETTINGS_DOC, doc)
        return _settings_payload()

    @app.get("/api/v1/projects/{project_id}/events")
    async def project_events(project_id: str, request: Request) -> StreamingResponse:
        subscriber = hub.subscribe(project_id)

        async def gen() -> Any:
            try:
                yield ": ping\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(subscriber.get(), timeout=30)
                    except TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                hub.unsubscribe(project_id, subscriber)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if settings is not None:
        from backend.api.finish import install_finish_routes

        install_finish_routes(app, queue=queue, store=store, hub=hub, settings=settings)
