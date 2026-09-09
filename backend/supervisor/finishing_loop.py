"""Pause unfinished work; assemble originals + passed jobs only; enqueue."""

from __future__ import annotations

import logging
from typing import Any

from backend.jobs.models import Job
from backend.supervisor.inspect import (
    DEFAULT_COST_MICROS,
    InspectNote,
    attendance_rows,
)
from backend.supervisor.rank import (
    RankPlan,
    RankResult,
    budget_cut,
    note_key,
    rank_notes,
)

log = logging.getLogger("pc.finishing")

PAUSE_REASON = "paused: finishing envelope exhausted"
DEFAULT_BUDGET_MICROS = 50_000_000
INSPECT_ESTIMATE_MICROS = 200_000  # per station billed look, printed (C-7.2)


def predecessor_station(to_station: str) -> str:
    """Locked house order: ingest → loudness → pickups → leftover work → delivery."""
    if to_station == "loudness":
        return "ingest"
    if to_station == "pickups":
        return "loudness"
    if to_station == "ingest":
        return "ingest"
    if to_station == "delivery":
        return "pickups"
    return "pickups"


def _stamp_job_scene(
    result: dict[str, Any],
    scene_understanding: dict[str, Any] | None,
    *,
    project_id: str,
    to_station: str,
    source_uri: str,
    from_station: str | None = None,
) -> None:
    from backend.jobs.handoff import turnover_manifest
    from backend.supervisor.station_agents.ingest_understand import (
        attach_scene_fields,
        scene_bag,
    )

    bag = scene_bag(scene_understanding)
    if not bag.get("ingested"):
        return
    attach_scene_fields(result, bag)
    files = [{"ref": source_uri, "sha256": "", "bytes": 0}] if source_uri else []
    result["handoff"] = turnover_manifest(
        project_id=project_id,
        from_station=from_station or predecessor_station(to_station),
        to_station=to_station,
        files=files,
        scene=bag,
    )


def pause_inflight(jobs: list[Job], remaining_micros: int) -> list[Job]:
    """When the envelope is gone, in-flight jobs do not get to finish.

    `throttled` is the existing non-terminal-but-stopped vocabulary (spend
    control). Unfinished artifact refs must not enter the final cut.
    """
    if remaining_micros > 0:
        return jobs
    paused: list[Job] = []
    for job in jobs:
        if job.status in {"leased", "queued"}:
            job.status = "throttled"
            job.error = PAUSE_REASON
        paused.append(job)
    return paused


def assemble_final(*, original_refs: list[str], jobs: list[Job]) -> list[str]:
    """Playable final = originals plus only jobs that already passed.

    Original ingest URIs are always kept (AL-1). Half-renders, failures,
    and paused work stay off the cut.
    """
    refs: list[str] = []
    seen: set[str] = set()
    for ref in original_refs:
        if ref and ref not in seen:
            refs.append(ref)
            seen.add(ref)
    for job in jobs:
        if job.status != "passed":
            continue
        artifact = str((job.result or {}).get("artifact_ref") or "")
        if artifact and artifact not in seen:
            refs.append(artifact)
            seen.add(artifact)
    return refs


def worklist_doc(
    *,
    project_id: str,
    budget_micros: int,
    spent_micros: int = 0,
    attendance: list[dict[str, Any]] | None = None,
    ranked: list[dict[str, Any]] | None = None,
    items: list[dict[str, Any]] | None = None,
    final_refs: list[str] | None = None,
    original_refs: list[str] | None = None,
    status: str = "inspecting",
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "budget_micros": budget_micros,
        "spent_micros": spent_micros,
        "attendance": attendance or [],
        "ranked": ranked or [],
        "items": items or [],
        "final_refs": final_refs or [],
        "original_refs": original_refs or [],
        "status": status,
    }


def inspect_estimate_micros(clip_count: int) -> int:
    return INSPECT_ESTIMATE_MICROS * len(PROPOSE_STATIONS) * max(1, clip_count)


def plan_finishing(
    notes: list[InspectNote],
    *,
    shot_order: dict[str, int],
    remaining_micros: int,
) -> RankResult:
    attendance = attendance_rows(notes)
    ranked = rank_notes(attendance, shot_order=shot_order)
    take, wait = budget_cut(ranked.ordered, remaining_micros=remaining_micros)
    return RankResult(ordered=take, waiting=ranked.waiting + wait)


GENERATIVE = frozenset(
    {"extend", "corrections", "relight", "coverage", "camera_language"}
)


def stamp_generative_job_result(
    result: dict[str, Any],
    station: str,
    *,
    summary: str = "",
    source_uri: str = "",
) -> dict[str, Any]:
    """Looker named args + defaults so a walk-away job can actually run."""
    if station not in GENERATIVE:
        return result
    result.setdefault("tier", "draft")
    if station == "corrections" and not str(result.get("intent") or "").strip():
        result["intent"] = summary
    if station == "relight":
        from backend.stations.relight.run import PRESETS

        if str(result.get("preset") or "") not in PRESETS:
            result["preset"] = "practical_lamp"
    if station == "coverage":
        from backend.stations.coverage.run import ANGLES

        if str(result.get("angle") or "") not in ANGLES:
            result["angle"] = "close_up"
        if not str(result.get("intent") or "").strip():
            result["intent"] = summary or "new coverage angle of the same subjects"
        refs = result.get("reference_uris") or []
        if not refs and source_uri:
            result["reference_uris"] = [source_uri]
    if station == "camera_language":
        from backend.stations.camera_language.run import MOVEMENTS

        if str(result.get("movement") or "") not in MOVEMENTS:
            result["movement"] = "dolly_tracking"
    return result


def jobs_from_notes(
    notes: list[InspectNote],
    *,
    project_id: str,
    source_uri: str,
    shot_id: str,
    scene_understanding: dict[str, Any] | None = None,
) -> list[Job]:
    jobs: list[Job] = []
    for note in notes:
        if note.status != "needs_work" or not note.proposal:
            continue
        target = str(note.proposal.get("station") or note.station)
        args = dict(note.proposal.get("args") or {})
        result = stamp_generative_job_result(
            {
                "shot_id": shot_id or note.shot_id or args.get("shot_id") or "",
                "finishing": True,
                **args,
            },
            target,
            summary=note.summary,
            source_uri=source_uri,
        )
        _stamp_job_scene(
            result,
            scene_understanding,
            project_id=project_id,
            to_station=target,
            source_uri=source_uri,
            from_station=predecessor_station(target),
        )
        jobs.append(
            Job(
                station=target,
                project_id=project_id,
                input_refs=[source_uri] if source_uri else [],
                result=result,
            )
        )
    return jobs


def collect_original_refs(
    store: Any, project_id: str, ingest_job_ids: list[str] | None = None
) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    try:
        rows = store.list_where("pc-jobs", "project_id", project_id)
    except Exception as exc:
        log.exception("collect_original_refs failed project=%s", project_id)
        if ingest_job_ids:
            raise RuntimeError("could not validate the requested ingest batch") from exc
        return refs
    ingest = [
        row
        for row in rows
        if str(row.get("station") or "") == "ingest"
        and str(row.get("status") or "") == "passed"
    ]
    if ingest_job_ids:
        if len(set(ingest_job_ids)) != len(ingest_job_ids):
            raise ValueError("ingest_job_ids must be unique")
        by_id = {str(row.get("id") or row.get("job_id") or ""): row for row in ingest}
        missing = [job_id for job_id in ingest_job_ids if job_id not in by_id]
        if missing:
            raise ValueError("every ingest_job_id must identify a passed ingest job")
        ingest = [by_id[job_id] for job_id in ingest_job_ids]
        if any(len(list(row.get("input_refs") or [])) != 1 for row in ingest):
            raise ValueError("every ingest job must resolve to exactly one original")
    else:
        ingest.sort(key=lambda row: str(row.get("created_at") or ""))
    for row in ingest:
        for ref in list(row.get("input_refs") or []):
            if ref and ref not in seen:
                refs.append(str(ref))
                seen.add(str(ref))
    return refs


def enqueue_jobs(queue: Any, jobs: list[Job]) -> list[str]:
    ids: list[str] = []
    for job in jobs:
        queue.submit(job)
        ids.append(job.id)
    return ids


_ACTIVE = frozenset({"queued", "leased", "running"})
_BLOCKING = frozenset({"waiting", "queued", "leased", "running"})


def _remaining(doc: dict[str, Any]) -> int:
    return int(doc.get("budget_micros") or 0) - int(doc.get("spent_micros") or 0)


def _busy_generative_shots(items: list[dict[str, Any]]) -> set[str]:
    busy: set[str] = set()
    for item in items:
        if str(item.get("station") or "") not in GENERATIVE:
            continue
        if str(item.get("status") or "") in _ACTIVE:
            busy.add(str(item.get("shot_id") or ""))
    return busy


def _job_from_item(
    item: dict[str, Any],
    *,
    project_id: str,
    scene_by_shot: dict[str, Any] | None = None,
) -> Job:
    proposal = dict(item.get("proposal") or {})
    args = dict(proposal.get("args") or {})
    station = str(proposal.get("station") or item.get("station") or "")
    source = str(item.get("source_uri") or "")
    shot_id = str(item.get("shot_id") or args.get("shot_id") or "")
    result = stamp_generative_job_result(
        {
            "shot_id": shot_id,
            "finishing": True,
            "worklist_item": item.get("id"),
            **args,
        },
        station,
        summary=str(item.get("summary") or ""),
        source_uri=source,
    )
    bag = item.get("scene_understanding")
    if not isinstance(bag, dict) and scene_by_shot:
        bag = scene_by_shot.get(shot_id)
    _stamp_job_scene(
        result,
        bag if isinstance(bag, dict) else None,
        project_id=project_id,
        to_station=station,
        source_uri=source,
        from_station=predecessor_station(station),
    )
    return Job(
        station=station,
        project_id=project_id,
        input_refs=[source] if source else [],
        result=result,
    )


def _deps_cleared(item: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    by_id = {str(row.get("id") or ""): row for row in items}
    for blocker_id in item.get("blocked_by") or []:
        blocker = by_id.get(str(blocker_id))
        if blocker is None:
            continue
        if str(blocker.get("status") or "") in _BLOCKING:
            return False
    return True


CLEANUP_STATIONS = ("loudness", "pickups")
PROPOSE_STATIONS = (
    "delivery",
    "dub",
    "extend",
    "corrections",
    "relight",
    "coverage",
    "camera_language",
)
_PICTURE_SUFFIXES = (".mp4", ".mov", ".mkv", ".webm", ".m4v")


def _cleanup_row(
    *,
    item_id: str,
    station: str,
    shot_id: str,
    source_uri: str,
    bag: dict[str, Any],
    blocked_by: list[str],
    upload_index: int,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    row = {
        "id": item_id,
        "station": station,
        "status": "waiting",
        "impact": "high",
        "kind": "defect",
        "summary": (
            "Mandatory mix"
            if station == "loudness"
            else "Mandatory repair when damage is real"
        ),
        "shot_id": shot_id,
        "source_uri": source_uri,
        "upload_index": upload_index,
        "cost_estimate_micros": int(DEFAULT_COST_MICROS.get(station, 0)),
        "proposal": {"kind": "station_job", "station": station, "args": args},
        "blocked_by": list(blocked_by),
        "phase": "cleanup",
        "scene_understanding": dict(bag),
        "ingested": bag.get("ingested"),
        "spoken_words": bag.get("spoken_words"),
        "scene": bag.get("scene"),
    }
    return row


def _delivery_row(
    *,
    shot_id: str,
    source_uri: str,
    bag: dict[str, Any],
    blocked_by: list[str],
) -> dict[str, Any]:
    return {
        "id": f"delivery::{shot_id}",
        "station": "delivery",
        "status": "waiting",
        "impact": "high",
        "kind": "defect",
        "summary": "Mandatory delivery check",
        "shot_id": shot_id,
        "source_uri": source_uri,
        "cost_estimate_micros": int(DEFAULT_COST_MICROS.get("delivery", 0)),
        "proposal": {"kind": "station_job", "station": "delivery", "args": {}},
        "blocked_by": list(blocked_by),
        "phase": "delivery",
        "scene_understanding": dict(bag),
        "ingested": bag.get("ingested"),
        "spoken_words": bag.get("spoken_words"),
        "scene": bag.get("scene"),
    }


def pin_delivery_last(
    items: list[dict[str, Any]],
    *,
    source_by_shot: dict[str, str] | None = None,
    scene_by_shot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Delivery is the last house step. Ranked leftover cannot drop it."""
    source_by_shot = dict(source_by_shot or {})
    scene_by_shot = scene_by_shot or {}
    non_delivery = [dict(row) for row in items if row.get("station") != "delivery"]
    existing = {
        str(row.get("shot_id") or ""): dict(row)
        for row in items
        if row.get("station") == "delivery"
    }
    shot_ids: list[str] = []
    seen: set[str] = set()
    for row in items:
        shot_id = str(row.get("shot_id") or "")
        if shot_id and shot_id not in seen:
            seen.add(shot_id)
            shot_ids.append(shot_id)
    for shot_id in source_by_shot:
        if shot_id not in seen:
            seen.add(shot_id)
            shot_ids.append(shot_id)
    leftover_blockers = [
        str(row.get("id") or "") for row in non_delivery if row.get("id")
    ]
    deliveries: list[dict[str, Any]] = []
    for shot_id in shot_ids:
        others = [
            row for row in non_delivery if str(row.get("shot_id") or "") == shot_id
        ]
        row = existing.get(shot_id)
        if row is None:
            bag = (
                scene_by_shot.get(shot_id) if isinstance(scene_by_shot, dict) else None
            )
            if not isinstance(bag, dict):
                bag = {}
            uri = source_by_shot.get(shot_id) or next(
                (str(item.get("source_uri") or "") for item in others),
                "",
            )
            row = _delivery_row(
                shot_id=shot_id,
                source_uri=uri,
                bag=bag,
                blocked_by=leftover_blockers,
            )
        else:
            deps = [str(dep) for dep in (row.get("blocked_by") or []) if dep]
            for blocker_id in leftover_blockers:
                if blocker_id and blocker_id not in deps:
                    deps.append(blocker_id)
            row["blocked_by"] = deps
        deliveries.append(row)
    return non_delivery + deliveries


def mandatory_cleanup_items(
    *,
    shots: list[tuple[str, str, int]],
    scene_by_shot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Always mix, then repair. Leftover stations are not in this bag."""
    ordered = sorted(shots, key=lambda row: int(row[2]))
    items: list[dict[str, Any]] = []
    prev_loud = ""
    for shot_id, uri, index in ordered:
        bag = scene_by_shot.get(shot_id) if isinstance(scene_by_shot, dict) else None
        if not isinstance(bag, dict):
            bag = {}
        loud_id = f"loudness::{shot_id}"
        pick_id = f"pickups::{shot_id}"
        loud_blocked = [prev_loud] if prev_loud else []
        items.append(
            _cleanup_row(
                item_id=loud_id,
                station="loudness",
                shot_id=shot_id,
                source_uri=uri,
                bag=bag,
                blocked_by=loud_blocked,
                upload_index=index,
            )
        )
        items.append(
            _cleanup_row(
                item_id=pick_id,
                station="pickups",
                shot_id=shot_id,
                source_uri=uri,
                bag=bag,
                blocked_by=[loud_id],
                upload_index=index,
            )
        )
        prev_loud = loud_id
    return items


def cleanup_finished(items: list[dict[str, Any]]) -> bool:
    cleanup = [
        row
        for row in items
        if str(row.get("phase") or "") == "cleanup"
        or str(row.get("station") or "") in CLEANUP_STATIONS
    ]
    if not cleanup:
        return False
    return all(str(row.get("status") or "") not in _BLOCKING for row in cleanup)


def picture_mix_uri(job: Job) -> str | None:
    artifact = str((job.result or {}).get("artifact_ref") or "")
    if not artifact:
        return None
    lower = artifact.lower()
    if any(lower.endswith(suffix) for suffix in _PICTURE_SUFFIXES):
        return artifact
    return None


def proposal_clip_uri(items: list[dict[str, Any]], shot_id: str, original: str) -> str:
    """Prefer the post-pickup picture, then the mix, then the original."""
    for station in ("pickups", "loudness"):
        for item in items:
            if str(item.get("station") or "") != station:
                continue
            if str(item.get("shot_id") or "") != shot_id:
                continue
            artifact = str(item.get("artifact_ref") or "")
            if artifact and any(
                artifact.lower().endswith(suffix) for suffix in _PICTURE_SUFFIXES
            ):
                return artifact
            source = str(item.get("source_uri") or "")
            if source and station == "pickups":
                return source
    return original


def collect_spine_note(job: Job) -> dict[str, Any] | None:
    result = job.result or {}
    note = str(result.get("handoff_orchestrator_note") or "").strip()
    if not note:
        return None
    return {
        "shot_id": str(result.get("shot_id") or ""),
        "job_id": job.id,
        "station": job.station,
        "note": note,
        "spoken_words": result.get("spoken_words"),
        "scene": result.get("scene"),
    }


def apply_cleanup_artifacts(doc: dict[str, Any], job: Job) -> dict[str, Any]:
    """Point pickups at a picture mix; stamp continuation onto the next shot."""
    items = list(doc.get("items") or [])
    result = job.result or {}
    worklist_item = str(result.get("worklist_item") or "")
    shot_id = ""
    for item in items:
        if str(item.get("job_id") or "") == job.id or (
            worklist_item and str(item.get("id") or "") == worklist_item
        ):
            artifact = str(result.get("artifact_ref") or "")
            if artifact:
                item["artifact_ref"] = artifact
            shot_id = str(item.get("shot_id") or result.get("shot_id") or "")
            break
    mix = picture_mix_uri(job) if job.station == "loudness" else None
    if mix and shot_id:
        for item in items:
            if (
                str(item.get("station") or "") == "pickups"
                and str(item.get("shot_id") or "") == shot_id
            ):
                item["source_uri"] = mix
    if (
        job.station == "loudness"
        and job.status == "passed"
        and shot_id
        and result.get("target_lufs") is not None
    ):
        order = doc.get("shot_order") if isinstance(doc.get("shot_order"), dict) else {}
        current = order.get(shot_id)
        next_shot = ""
        if current is not None:
            nxt = int(current) + 1
            for sid, idx in order.items():
                if int(idx) == nxt:
                    next_shot = str(sid)
                    break
        if next_shot:
            for item in items:
                if str(item.get("id") or "") == f"loudness::{next_shot}":
                    proposal = dict(item.get("proposal") or {})
                    args = dict(proposal.get("args") or {})
                    args["previous_target_lufs"] = float(result["target_lufs"])
                    args["continuation"] = True
                    proposal["args"] = args
                    item["proposal"] = proposal
    doc["items"] = items
    return doc


def apply_cleanup_sequence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Loudness then pickups first per shot; Stage 1a/dub wait until those pass."""
    by_shot: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_shot.setdefault(str(item.get("shot_id") or ""), []).append(item)
    ordered: list[dict[str, Any]] = []
    for rows in by_shot.values():
        loud = next((r for r in rows if r.get("station") == "loudness"), None)
        pick = next((r for r in rows if r.get("station") == "pickups"), None)
        rest = [r for r in rows if r.get("station") not in CLEANUP_STATIONS]
        if loud is not None:
            loud = dict(loud)
            loud["blocked_by"] = []
            ordered.append(loud)
        if pick is not None:
            pick = dict(pick)
            pick["blocked_by"] = [str(loud.get("id") or "")] if loud else []
            pick["blocked_by"] = [b for b in pick["blocked_by"] if b]
            ordered.append(pick)
        blocker_id = str((pick or loud or {}).get("id") or "")
        for row in rest:
            row = dict(row)
            deps = [str(d) for d in (row.get("blocked_by") or []) if d]
            if blocker_id and blocker_id not in deps:
                deps.append(blocker_id)
            row["blocked_by"] = deps
            ordered.append(row)
    return ordered


def dispatch_next(
    doc: dict[str, Any], *, queue: Any, project_id: str
) -> dict[str, Any]:
    """Start the next ranked waiting items that fit budget and sequencing.

    Stack order is preserved. Independent clips / non-fighting stations may
    start together. One generative picture edit per shot at a time. Work that
    does not fit stays waiting for the human (or the next tick).
    """
    items = list(doc.get("items") or [])
    remaining = _remaining(doc)
    busy = _busy_generative_shots(items)
    started: list[Job] = []
    for item in items:
        if str(item.get("status") or "") != "waiting":
            continue
        cost = int(item.get("cost_estimate_micros") or 0)
        if cost > remaining:
            continue
        station = str(item.get("station") or "")
        shot = str(item.get("shot_id") or "")
        if station in GENERATIVE and shot in busy:
            continue
        if not _deps_cleared(item, items):
            continue
        job = _job_from_item(
            item,
            project_id=project_id,
            scene_by_shot=doc.get("scene_by_shot")
            if isinstance(doc.get("scene_by_shot"), dict)
            else None,
        )
        started.append(job)
        item["status"] = "queued"
        item["job_id"] = job.id
        remaining -= cost
        if station in GENERATIVE:
            busy.add(shot)
    enqueue_jobs(queue, started)
    doc["items"] = items
    if remaining <= 0 and any(str(i.get("status")) == "waiting" for i in items):
        doc["status"] = "waiting_for_budget"
    elif any(str(i.get("status")) in _ACTIVE for i in items):
        doc["status"] = "running"
    elif any(str(i.get("status")) == "waiting" for i in items):
        doc["status"] = "waiting_for_budget"
    else:
        doc["status"] = "idle"
    return doc


def apply_draft_qc(
    doc: dict[str, Any],
    job: Job,
    *,
    settings: Any | None = None,
    store: Any | None = None,
) -> dict[str, Any]:
    """After a generative draft, Visual QC (Gemini when settings exist) names
    master_eligible / revise / escalate. Flicker breach never waves through.
    """
    from backend.stations.draft_first import (
        MAX_REVISIONS,
        map_visual_qc_decision,
        metrics_from_job_result,
    )
    from backend.supervisor.station_agents.visual_qc import suggestion_for_metrics

    if job.station not in GENERATIVE or job.status != "passed":
        return doc
    result = dict(job.result or {})
    revision_count = int(result.get("revision_count") or 0)
    metrics = metrics_from_job_result(result)
    qc_cost = 0
    if settings is not None:
        from backend.supervisor.station_agents.visual_qc import decide_visual_qc

        decision, qc_cost = decide_visual_qc(
            settings,
            job={"id": job.id, "station": job.station, "result": result},
            metrics_doc=metrics,
        )
        qc = decision.decision
        reason = decision.reason
    else:
        qc = suggestion_for_metrics(metrics)
        reason = "deterministic visual qc (no live settings)"
    state = map_visual_qc_decision(qc, revision_count=revision_count)
    result["visual_qc"] = qc
    result["draft_state"] = state
    result["visual_qc_reason"] = reason
    if qc_cost:
        result["visual_qc_cost_micros"] = qc_cost
    try:
        from backend.core.generative import estimate_extend_cost_micros
        from backend.stations.draft_first import cost_delta_micros

        result["cost_delta_micros"] = cost_delta_micros(
            int(job.cost_micros or 0),
            estimate_extend_cost_micros(7.0, resolution="720p"),
        )
    except Exception:
        result.setdefault("cost_delta_micros", 0)
    job.result = result
    items = list(doc.get("items") or [])
    worklist_item = str(result.get("worklist_item") or "")
    for item in items:
        if str(item.get("job_id") or "") == job.id or (
            worklist_item and str(item.get("id") or "") == worklist_item
        ):
            item["draft_state"] = state
            item["visual_qc"] = qc
            if state == "escalate":
                item["status"] = "needs_human"
            if state == "master_eligible":
                item["master_eligible"] = True
            break
    if state == "revise" and revision_count < MAX_REVISIONS:
        shot_id = str(result.get("shot_id") or "")
        source = ""
        if job.input_refs:
            source = str(job.input_refs[0])
        retry_id = f"{job.station}::{shot_id}::revise"
        if not any(str(item.get("id") or "") == retry_id for item in items):
            items.append(
                {
                    "id": retry_id,
                    "station": job.station,
                    "status": "waiting",
                    "impact": "medium",
                    "kind": "defect",
                    "summary": f"bounded revision after visual QC: {reason}"[:240],
                    "shot_id": shot_id,
                    "source_uri": source,
                    "cost_estimate_micros": int(
                        result.get("cost_estimate_micros") or job.cost_micros or 0
                    ),
                    "proposal": {
                        "kind": "station_job",
                        "station": job.station,
                        "args": {
                            key: result[key]
                            for key in (
                                "preset",
                                "intent",
                                "angle",
                                "movement",
                                "reference_uris",
                                "tier",
                            )
                            if key in result
                        }
                        | {"revision_count": revision_count + 1, "tier": "draft"},
                    },
                }
            )
    doc["items"] = items
    alternate_id = str(result.get("alternate_id") or "")
    if store is not None and alternate_id:
        from backend.shots import lifecycle as shots

        shots.stamp_alternate_qc(
            store,
            alternate_id,
            draft_state=state,
            visual_qc=qc,
            cost_delta_micros=int(result.get("cost_delta_micros") or 0) or None,
        )
    return doc


def on_finishing_terminal(
    doc: dict[str, Any],
    job: Job,
    *,
    queue: Any,
    project_id: str,
    settings: Any | None = None,
    store: Any | None = None,
) -> dict[str, Any]:
    """Tick the finished item, count real spend, start the next ranked work."""
    items = list(doc.get("items") or [])
    mapped = {
        "passed": "passed",
        "failed": "failed",
        "needs_human": "needs_human",
        "throttled": "paused",
        "quarantined": "failed",
    }
    new_status = mapped.get(job.status, job.status)
    worklist_item = str((job.result or {}).get("worklist_item") or "")
    matched = False
    for item in items:
        if str(item.get("job_id") or "") == job.id or (
            worklist_item and str(item.get("id") or "") == worklist_item
        ):
            item["status"] = new_status
            item["cost_actual_micros"] = int(job.cost_micros or 0)
            matched = True
    doc["items"] = items
    if not matched:
        return doc
    spine_note = collect_spine_note(job)
    if spine_note is not None:
        spine = list(doc.get("orchestrator_spine") or [])
        spine.append(spine_note)
        doc["orchestrator_spine"] = spine
    apply_cleanup_artifacts(doc, job)
    apply_draft_qc(doc, job, settings=settings, store=store)
    doc["spent_micros"] = int(doc.get("spent_micros") or 0) + int(job.cost_micros or 0)
    remaining = _remaining(doc)
    if remaining <= 0:
        waiting = any(
            str(i.get("status") or "") == "waiting" for i in doc.get("items") or []
        )
        doc["status"] = "waiting_for_budget" if waiting else "idle"
        return doc
    return dispatch_next(doc, queue=queue, project_id=project_id)


def items_from_rank(
    ranked: RankResult | RankPlan,
    *,
    source_by_shot: dict[str, str],
    scene_by_shot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Every needs_work note becomes a waiting row. Dispatch applies budget."""
    if isinstance(ranked, RankPlan):
        notes = list(ranked.ordered)
        blocked_by = ranked.blocked_by
    else:
        notes = [*ranked.ordered, *ranked.waiting]
        blocked_by = {}
    scene_by_shot = scene_by_shot or {}
    items: list[dict[str, Any]] = []
    for note in notes:
        key = note_key(note)
        shot_id = note.shot_id or ""
        bag = scene_by_shot.get(shot_id) if isinstance(scene_by_shot, dict) else None
        row = {
            "id": key,
            "station": note.station,
            "status": "waiting",
            "impact": note.impact,
            "kind": note.kind,
            "summary": note.summary,
            "shot_id": shot_id,
            "source_uri": source_by_shot.get(shot_id, ""),
            "cost_estimate_micros": int(note.cost_estimate_micros),
            "proposal": dict(note.proposal),
            "blocked_by": list(blocked_by.get(key) or []),
        }
        if isinstance(bag, dict):
            row["scene_understanding"] = bag
            row["ingested"] = bag.get("ingested")
            row["spoken_words"] = bag.get("spoken_words")
            row["scene"] = bag.get("scene")
        items.append(row)
    return pin_delivery_last(
        apply_cleanup_sequence(items),
        source_by_shot=source_by_shot,
        scene_by_shot=scene_by_shot,
    )


def refresh_final_refs(doc: dict[str, Any], store: Any) -> dict[str, Any]:
    originals = [str(ref) for ref in (doc.get("original_refs") or []) if ref]
    jobs: list[Job] = []
    try:
        rows = store.list_where("pc-jobs", "project_id", doc.get("project_id"))
        jobs = [Job.from_dict(row) for row in rows]
    except Exception:
        log.exception("refresh_final_refs failed")
    doc["final_refs"] = assemble_final(original_refs=originals, jobs=jobs)
    return doc


def stamp_ingest_watch(store: Any, job_id: str, bag: dict[str, Any]) -> None:
    """Write Gemini watch notes onto the ingest file-check job.

    Mix and pickups already carry the bag; the ingest row must too, or the
    board keeps Ingest in progress after later stages have finished.
    """
    if not job_id or not hasattr(store, "transactional_update"):
        return

    notes = {
        "ingested": bool(bag.get("ingested")),
        "spoken_words": bag.get("spoken_words"),
        "scene": bag.get("scene"),
    }

    def mutate(doc: dict[str, Any]) -> dict[str, Any]:
        result = dict(doc.get("result") or {})
        result["ingested"] = notes["ingested"]
        if notes["spoken_words"] is not None:
            result["spoken_words"] = notes["spoken_words"]
        if notes["scene"] is not None:
            result["scene"] = notes["scene"]
        return {**doc, "result": result}

    store.transactional_update("pc-jobs", job_id, mutate)
