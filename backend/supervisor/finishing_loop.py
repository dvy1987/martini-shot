"""Pause unfinished work; assemble originals + passed jobs only; enqueue."""

from __future__ import annotations

import logging
from typing import Any

from backend.jobs.models import Job
from backend.supervisor.inspect import InspectNote, attendance_rows
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
    from backend.supervisor.inspect import ROSTER

    return INSPECT_ESTIMATE_MICROS * len(ROSTER) * max(1, clip_count)


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


def jobs_from_notes(
    notes: list[InspectNote],
    *,
    project_id: str,
    source_uri: str,
    shot_id: str,
) -> list[Job]:
    jobs: list[Job] = []
    for note in notes:
        if note.status != "needs_work" or not note.proposal:
            continue
        target = str(note.proposal.get("station") or note.station)
        args = dict(note.proposal.get("args") or {})
        result = {
            "shot_id": shot_id or note.shot_id or args.get("shot_id") or "",
            "finishing": True,
            **args,
        }
        jobs.append(
            Job(
                station=target,
                project_id=project_id,
                input_refs=[source_uri] if source_uri else [],
                result=result,
            )
        )
    return jobs


def collect_original_refs(store: Any, project_id: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    try:
        rows = store.list_where("pc-jobs", "project_id", project_id)
    except Exception:
        log.exception("collect_original_refs failed project=%s", project_id)
        return refs
    for row in rows:
        if str(row.get("station") or "") != "ingest":
            continue
        if str(row.get("status") or "") != "passed":
            continue
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


GENERATIVE = frozenset(
    {"extend", "corrections", "relight", "coverage", "camera_language"}
)
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


def _job_from_item(item: dict[str, Any], *, project_id: str) -> Job:
    proposal = dict(item.get("proposal") or {})
    args = dict(proposal.get("args") or {})
    station = str(proposal.get("station") or item.get("station") or "")
    source = str(item.get("source_uri") or "")
    shot_id = str(item.get("shot_id") or args.get("shot_id") or "")
    return Job(
        station=station,
        project_id=project_id,
        input_refs=[source] if source else [],
        result={
            "shot_id": shot_id,
            "finishing": True,
            "worklist_item": item.get("id"),
            **args,
        },
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
        job = _job_from_item(item, project_id=project_id)
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


def on_finishing_terminal(
    doc: dict[str, Any],
    job: Job,
    *,
    queue: Any,
    project_id: str,
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
            matched = True
    doc["items"] = items
    if not matched:
        return doc
    doc["spent_micros"] = int(doc.get("spent_micros") or 0) + int(job.cost_micros or 0)
    remaining = _remaining(doc)
    if remaining <= 0:
        waiting = any(str(i.get("status") or "") == "waiting" for i in items)
        doc["status"] = "waiting_for_budget" if waiting else "idle"
        return doc
    return dispatch_next(doc, queue=queue, project_id=project_id)


def items_from_rank(
    ranked: RankResult | RankPlan,
    *,
    source_by_shot: dict[str, str],
) -> list[dict[str, Any]]:
    """Every needs_work note becomes a waiting row. Dispatch applies budget."""
    if isinstance(ranked, RankPlan):
        notes = list(ranked.ordered)
        blocked_by = ranked.blocked_by
    else:
        notes = [*ranked.ordered, *ranked.waiting]
        blocked_by = {}
    items: list[dict[str, Any]] = []
    for note in notes:
        key = note_key(note)
        shot_id = note.shot_id or ""
        items.append(
            {
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
        )
    return items


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
