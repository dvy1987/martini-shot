"""Walk-away finishing HTTP: start, worklist, reorder.

Long inspect/rank is a background job (C-6.5) — POST returns immediately.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
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
    assemble_final,
    collect_original_refs,
    dispatch_next,
    inspect_estimate_micros,
    items_from_rank,
    refresh_final_refs,
    worklist_doc,
)
from backend.supervisor.inspect import ROSTER, attendance_rows
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
    for station in ROSTER:
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

    all_notes: list[Any] = []
    source_by_shot: dict[str, str] = {}
    shot_order: dict[str, int] = {}
    from backend.supervisor.clip_preview import ClipPreviewCache

    preview_cache = ClipPreviewCache(settings)
    scene_by_shot: dict[str, Any] = {}
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
        scene_by_shot[shot_id] = {
            "ingested": context.get("ingested"),
            "spoken_words": context.get("spoken_words"),
            "scene": context.get("scene"),
        }
        notes: list[Any]
        try:
            from backend.supervisor.adk_finishing import run_finishing_runner_sync

            notes, _last = run_finishing_runner_sync(
                settings, context, preview_cache=preview_cache
            )
        except Exception:
            log.exception("ADK Runner failed; billed python inspect fallback")
            notes = _run_attendance(
                settings,
                store=store,
                source_uri=source_uri,
                shot_id=shot_id,
                project_id=project_id,
                budget_micros=budget_micros,
                preview_cache=preview_cache,
            )
        for note in notes:
            if not note.shot_id:
                note = replace(note, shot_id=shot_id)
            all_notes.append(note)

    try:
        from backend.supervisor.adk_finishing import run_orchestrator_rank_sync

        plan = run_orchestrator_rank_sync(
            settings,
            all_notes,
            remaining_micros=budget_micros,
            shot_order=shot_order,
            scene_by_shot=scene_by_shot,
        )
        if not plan.ordered and any(
            note.status == "needs_work" and note.proposal for note in all_notes
        ):
            raise RuntimeError("ADK orchestrator returned no order")
    except Exception:
        log.exception("ADK orchestrator rank failed; billed rank fallback")
        plan = rank_complete_bag(
            settings,
            all_notes,
            shot_order=shot_order,
            remaining_micros=budget_micros,
        )
    items = items_from_rank(
        plan, source_by_shot=source_by_shot, scene_by_shot=scene_by_shot
    )
    doc = worklist_doc(
        project_id=project_id,
        budget_micros=budget_micros,
        original_refs=originals,
        attendance=[n.to_doc() for n in all_notes],
        ranked=[item for item in items],
        items=items,
        final_refs=assemble_final(original_refs=originals, jobs=[]),
        status="running",
        spent_micros=0,
    )
    doc["rank_reason"] = plan.reason
    doc["scene_by_shot"] = scene_by_shot
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
