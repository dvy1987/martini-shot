"""Walk-away finishing HTTP: start, worklist, reorder.

Long inspect/rank is a background job (C-6.5) — POST returns immediately.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.api.events import EventHub
from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.jobs.queue import FirestoreLeaseQueue
from backend.shots import lifecycle as shots
from backend.supervisor.finishing_loop import (
    DEFAULT_BUDGET_MICROS,
    PROPOSE_STATIONS,
    assemble_final,
    collect_original_refs,
    dispatch_next,
    inspect_estimate_micros,
    items_from_rank,
    mandatory_cleanup_items,
    proposal_clip_uri,
    refresh_final_refs,
    worklist_doc,
)
from backend.supervisor.inspect import attendance_rows
from backend.supervisor.inspect_impl import run_inspect
from backend.supervisor.rank_impl import rank_complete_bag
from backend.supervisor.worklist import load_worklist, reorder_items, save_worklist

log = logging.getLogger("pc.api.finish")


def clip_context_after_ingest(
    *,
    store: FirestoreStore,
    settings: Settings,
    source_uri: str,
    shot_id: str,
    project_id: str,
    budget_micros: int,
) -> dict[str, Any]:
    """First agent step after a healthy ingest job: watch, then stamp context."""
    from backend.core.gcs import get_gcs
    from backend.core.media import get_media
    from backend.supervisor.station_agents.ingest_understand import (
        attach_scene_fields,
        ensure_scene_understanding,
        scene_bag,
        scene_understanding_from_shot,
    )

    existing = scene_understanding_from_shot(store, shot_id)
    if existing and existing.get("ingested"):
        ctx = {
            "clip_uri": source_uri,
            "shot_id": shot_id,
            "project_id": project_id,
            "budget_micros": budget_micros,
        }
        return attach_scene_fields(ctx, existing)
    payload = get_gcs(settings).download_bytes(source_uri)
    bag = ensure_scene_understanding(
        store,
        shot_id,
        settings=settings,
        payload=payload,
        media=get_media(settings),
    )
    ctx = {
        "clip_uri": source_uri,
        "shot_id": shot_id,
        "project_id": project_id,
        "budget_micros": budget_micros,
    }
    return attach_scene_fields(ctx, scene_bag(bag))


class FinishIn(BaseModel):
    budget_micros: int = Field(default=DEFAULT_BUDGET_MICROS, gt=0)


class WorklistPatchIn(BaseModel):
    order: list[str]


def _publish(hub: EventHub, project_id: str, doc: dict[str, Any]) -> None:
    hub.publish(project_id, "worklist.updated", {"worklist": doc})


def _run_attendance(
    settings: Settings,
    *,
    store: FirestoreStore,
    source_uri: str,
    shot_id: str,
    project_id: str,
    budget_micros: int,
    preview_cache: Any | None = None,
) -> list[Any]:
    print(
        "finishing inspect estimate: "
        f"${inspect_estimate_micros(1) / 1_000_000:.2f} "
        f"({inspect_estimate_micros(1)} micros) before billed looks "
        f"project={project_id} budget_micros={budget_micros}",
        flush=True,
    )
    notes = []
    context = clip_context_after_ingest(
        store=store,
        settings=settings,
        source_uri=source_uri,
        shot_id=shot_id,
        project_id=project_id,
        budget_micros=budget_micros,
    )
    for station in PROPOSE_STATIONS:
        notes.append(
            run_inspect(
                station,
                settings=settings,
                context=context,
                preview_cache=preview_cache,
            )
        )
    return notes


def _finish_once(
    *,
    settings: Settings,
    store: FirestoreStore,
    queue: FirestoreLeaseQueue,
    hub: EventHub,
    project_id: str,
    budget_micros: int,
) -> dict[str, Any]:
    originals = collect_original_refs(store, project_id)
    doc = worklist_doc(
        project_id=project_id,
        budget_micros=budget_micros,
        original_refs=originals,
        attendance=[n.to_doc() for n in attendance_rows([])],
        status="inspecting",
        spent_micros=0,
    )
    save_worklist(store, project_id, doc)
    _publish(hub, project_id, doc)
    if not originals:
        doc["status"] = "waiting_for_ingest"
        save_worklist(store, project_id, doc)
        _publish(hub, project_id, doc)
        return doc

    source_by_shot: dict[str, str] = {}
    shot_order: dict[str, int] = {}
    scene_by_shot: dict[str, Any] = {}
    shots_for_cleanup: list[tuple[str, str, int]] = []
    for index, source_uri in enumerate(originals):
        shot_id = shots.ensure_shot(store, project_id=project_id, title=source_uri)
        source_by_shot[shot_id] = source_uri
        shot_order[shot_id] = index
        context = clip_context_after_ingest(
            store=store,
            settings=settings,
            source_uri=source_uri,
            shot_id=shot_id,
            project_id=project_id,
            budget_micros=budget_micros,
        )
        bag = {
            "ingested": context.get("ingested"),
            "spoken_words": context.get("spoken_words"),
            "scene": context.get("scene"),
        }
        scene_by_shot[shot_id] = bag
        shots_for_cleanup.append((shot_id, source_uri, index))

    items = mandatory_cleanup_items(
        shots=shots_for_cleanup, scene_by_shot=scene_by_shot
    )
    doc = worklist_doc(
        project_id=project_id,
        budget_micros=budget_micros,
        original_refs=originals,
        attendance=[n.to_doc() for n in attendance_rows([])],
        ranked=[],
        items=items,
        final_refs=assemble_final(original_refs=originals, jobs=[]),
        status="running",
        spent_micros=0,
    )
    doc["scene_by_shot"] = scene_by_shot
    doc["shot_order"] = shot_order
    doc["source_by_shot"] = source_by_shot
    doc["proposals_started"] = False
    doc["phase"] = "cleanup"
    doc["orchestrator_spine"] = list(doc.get("orchestrator_spine") or [])
    doc = dispatch_next(doc, queue=queue, project_id=project_id)
    refresh_final_refs(doc, store)
    save_worklist(store, project_id, doc)
    _publish(hub, project_id, doc)
    return doc


def run_proposal_phase(
    doc: dict[str, Any],
    *,
    settings: Settings,
    store: FirestoreStore,
    queue: FirestoreLeaseQueue,
    hub: EventHub,
) -> dict[str, Any]:
    """After every mix+pickups job: leftover Gemini looks, spend prices, rank."""
    from dataclasses import replace

    from backend.supervisor.clip_preview import ClipPreviewCache
    from backend.supervisor.rank import note_key
    from backend.supervisor.station_agents.spend_pricing import (
        apply_prices,
        decide_spend_pricing,
    )

    if doc.get("proposals_started"):
        return doc
    doc["proposals_started"] = True
    doc["phase"] = "propose"
    project_id = str(doc.get("project_id") or "")
    budget_micros = int(doc.get("budget_micros") or 0)
    remaining = budget_micros - int(doc.get("spent_micros") or 0)
    source_by_shot = dict(doc.get("source_by_shot") or {})
    shot_order = dict(doc.get("shot_order") or {})
    scene_by_shot = dict(doc.get("scene_by_shot") or {})
    items = list(doc.get("items") or [])
    ordered_shots = sorted(shot_order.items(), key=lambda row: int(row[1]))
    print(
        "finishing inspect estimate: "
        f"${inspect_estimate_micros(max(1, len(ordered_shots))) / 1_000_000:.2f} "
        f"({inspect_estimate_micros(max(1, len(ordered_shots)))} micros) "
        f"leftover looks after pickups project={project_id}",
        flush=True,
    )
    preview_cache = ClipPreviewCache(settings)
    all_notes: list[Any] = []
    for shot_id, index in ordered_shots:
        original = source_by_shot.get(shot_id, "")
        clip_uri = proposal_clip_uri(items, shot_id, original)
        bag = scene_by_shot.get(shot_id) if isinstance(scene_by_shot, dict) else {}
        if not isinstance(bag, dict):
            bag = {}
        context = {
            "clip_uri": clip_uri,
            "shot_id": shot_id,
            "project_id": project_id,
            "budget_micros": remaining,
            "upload_index": int(index),
            "upload_count": len(ordered_shots),
            "ingested": bag.get("ingested"),
            "spoken_words": bag.get("spoken_words"),
            "scene": bag.get("scene"),
            "neighbor_shots": [
                {
                    "shot_id": other_id,
                    "upload_index": int(other_idx),
                    "scene": (scene_by_shot.get(other_id) or {}).get("scene")
                    if isinstance(scene_by_shot.get(other_id), dict)
                    else None,
                    "spoken_words": (scene_by_shot.get(other_id) or {}).get(
                        "spoken_words"
                    )
                    if isinstance(scene_by_shot.get(other_id), dict)
                    else None,
                }
                for other_id, other_idx in ordered_shots
                if other_id != shot_id
            ],
        }
        notes: list[Any]
        try:
            from backend.supervisor.adk_finishing import run_finishing_runner_sync

            notes, _last = run_finishing_runner_sync(
                settings, context, preview_cache=preview_cache
            )
        except Exception:
            log.exception("ADK leftover looks failed; billed python inspect fallback")
            notes = _run_attendance(
                settings,
                store=store,
                source_uri=clip_uri,
                shot_id=shot_id,
                project_id=project_id,
                budget_micros=remaining,
                preview_cache=preview_cache,
            )
        for note in notes:
            if not note.shot_id:
                note = replace(note, shot_id=shot_id)
            all_notes.append(note)

    candidates = [
        {
            "id": note_key(note),
            "station": note.station,
            "shot_id": note.shot_id,
            "impact": note.impact,
            "kind": note.kind,
            "summary": note.summary,
            "cost_estimate_micros": note.cost_estimate_micros,
        }
        for note in all_notes
        if note.status == "needs_work" and note.proposal
    ]
    try:
        prices, _cost = decide_spend_pricing(
            settings, candidates=candidates, remaining_micros=remaining
        )
        apply_prices(all_notes, prices)
    except Exception:
        log.exception("spend pricing failed; station defaults remain advice only")

    spine = list(doc.get("orchestrator_spine") or [])
    try:
        from backend.supervisor.adk_finishing import run_orchestrator_rank_sync

        plan = run_orchestrator_rank_sync(
            settings,
            all_notes,
            remaining_micros=remaining,
            shot_order=shot_order,
            scene_by_shot=scene_by_shot,
            orchestrator_spine=spine,
        )
        if not plan.ordered and candidates:
            raise RuntimeError("ADK orchestrator returned no order")
    except Exception:
        log.exception("ADK orchestrator rank failed; billed rank fallback")
        plan = rank_complete_bag(
            settings,
            all_notes,
            shot_order=shot_order,
            remaining_micros=remaining,
            scene_by_shot=scene_by_shot,
            orchestrator_spine=spine,
        )
    proposed = items_from_rank(
        plan, source_by_shot=source_by_shot, scene_by_shot=scene_by_shot
    )
    for row in proposed:
        shot_id = str(row.get("shot_id") or "")
        original = source_by_shot.get(shot_id, "")
        row["source_uri"] = proposal_clip_uri(items, shot_id, original)
        row["phase"] = "propose"
    cleanup = [
        row
        for row in items
        if str(row.get("phase") or "") == "cleanup"
        or str(row.get("station") or "") in {"loudness", "pickups"}
    ]
    doc["items"] = cleanup + proposed
    doc["attendance"] = [n.to_doc() for n in all_notes]
    doc["ranked"] = list(proposed)
    doc["rank_reason"] = plan.reason
    doc = dispatch_next(doc, queue=queue, project_id=project_id)
    refresh_final_refs(doc, store)
    save_worklist(store, project_id, doc)
    _publish(hub, project_id, doc)
    return doc


def install_finish_routes(
    app: FastAPI,
    *,
    queue: FirestoreLeaseQueue,
    store: FirestoreStore,
    hub: EventHub,
    settings: Settings,
) -> None:
    @app.post("/api/v1/projects/{project_id}/finish")
    def start_finish(project_id: str, body: FinishIn | None = None) -> dict[str, Any]:
        budget = body.budget_micros if body is not None else DEFAULT_BUDGET_MICROS
        existing = load_worklist(store, project_id)
        if existing and str(existing.get("status") or "") in {
            "inspecting",
            "running",
            "waiting_for_ingest",
        }:
            return existing
        seed = worklist_doc(
            project_id=project_id,
            budget_micros=budget,
            original_refs=collect_original_refs(store, project_id),
            attendance=[n.to_doc() for n in attendance_rows([])],
            status="inspecting",
        )
        save_worklist(store, project_id, seed)
        _publish(hub, project_id, seed)

        async def _bg() -> None:
            try:
                await asyncio.to_thread(
                    _finish_once,
                    settings=settings,
                    store=store,
                    queue=queue,
                    hub=hub,
                    project_id=project_id,
                    budget_micros=budget,
                )
            except Exception:
                log.exception("finishing loop failed project=%s", project_id)

        try:
            asyncio.get_running_loop().create_task(
                _bg(), name=f"pc-finish-{project_id}"
            )
        except RuntimeError:
            _finish_once(
                settings=settings,
                store=store,
                queue=queue,
                hub=hub,
                project_id=project_id,
                budget_micros=budget,
            )
        return seed

    @app.get("/api/v1/projects/{project_id}/worklist")
    def get_worklist(project_id: str) -> dict[str, Any]:
        doc = load_worklist(store, project_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no worklist")
        return doc

    @app.patch("/api/v1/projects/{project_id}/worklist")
    def patch_worklist(project_id: str, body: WorklistPatchIn) -> dict[str, Any]:
        doc = load_worklist(store, project_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no worklist")
        updated = reorder_items(doc, body.order)
        if str(updated.get("status") or "") not in {
            "inspecting",
            "waiting_for_ingest",
        }:
            updated = dispatch_next(updated, queue=queue, project_id=project_id)
        save_worklist(store, project_id, updated)
        _publish(hub, project_id, updated)
        return updated

    @app.get("/api/v1/projects/{project_id}/run-pulse")
    def get_run_pulse(project_id: str) -> dict[str, Any]:
        from backend.supervisor.run_pulse import assemble_run_pulse

        return assemble_run_pulse(store, project_id, settings=settings)
