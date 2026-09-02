"""Sweeper — the watchdog that never leaves an action silently stuck (H-0).

Patience is the contract (locked design §Sweeper + pre-mortem clauses):
- A watched job that is still queued/leased is LEFT ALONE — the lease-expiry
  machinery owns it, and auto-retrying a render is forbidden.
- An `acting` approval older than 15 minutes with a non-terminal job fails
  with `needs_human_review` (backstop; the job itself is never touched).
- A fast action that crashed between its two transitions (status 'approved',
  no result) is re-driven — safe precisely because fast commands are
  fail-closed idempotent — capped at 3 sweep retries, then failed.
- Order-safety: before any re-drive, a newer decision on the same target
  (same station for intake commands) makes this one `superseded` — the newer
  (often human) decision always stands.

The sweeper writes approval status ONLY through the machine (single-writer).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.approvals.machine import APPROVALS, ApprovalStateMachine
from backend.jobs.queue import FirestoreLeaseQueue

log = logging.getLogger("pc.approvals.sweeper")

FAST_REDRIVE_AFTER = timedelta(seconds=30)
STALE_ACTING_AFTER = timedelta(minutes=15)
MAX_SWEEP_RETRIES = 3
JOB_TERMINAL = {"passed", "failed", "quarantined"}
# Commands that target a shared mutable resource the order-safety guard
# understands today (intake pause flags). New target types extend this.
TARGETED_COMMANDS = {"pause_intake", "resume_intake"}


def _parse_iso(value: object) -> datetime | None:
    try:
        raw = str(value or "").replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _age_past(value: object, limit: timedelta, now: datetime) -> bool:
    stamp = _parse_iso(value)
    return stamp is not None and (now - stamp) > limit


def _superseded(store: Any, collection: str, doc: dict[str, Any]) -> bool:
    """True when a NEWER decision already touched the same target."""
    command = doc.get("command") or {}
    if command.get("name") not in TARGETED_COMMANDS:
        return False
    station = (command.get("args") or {}).get("station")
    if station is None:
        return False
    mine = str(doc.get("decided_at") or "")
    try:
        rows = store.list_where(collection, "project_id", doc.get("project_id"))
    except Exception:
        log.exception("superseded check failed; refusing to redrive")
        return True  # fail-closed: can't prove freshness -> don't act
    for row in rows:
        if row.get("approval_id") == doc.get("approval_id"):
            continue
        other = row.get("command") or {}
        if other.get("name") not in TARGETED_COMMANDS:
            continue
        if (other.get("args") or {}).get("station") != station:
            continue
        if row.get("status") == "proposed":
            continue
        if str(row.get("decided_at") or "") > mine:
            return True
    return False


def sweep_once(
    store: Any,
    queue: FirestoreLeaseQueue,
    machine: ApprovalStateMachine,
    *,
    collection: str = APPROVALS,
) -> dict[str, int]:
    """One watchdog tick. Returns a small tally for logs/metrics."""
    summary = {
        "reconciled": 0,
        "failed_stale": 0,
        "redriven": 0,
        "superseded": 0,
        "watching": 0,
    }
    now = datetime.now(timezone.utc)
    for snap in store.client.collection(collection).stream():
        doc = snap.to_dict() or {}
        approval_id = str(doc.get("approval_id") or snap.id)
        status = doc.get("status")

        if status == "acting":
            job_id = str(doc.get("job_id") or "")
            job = queue.get(job_id) if job_id else None
            if job is not None and job.status in JOB_TERMINAL:
                # Crash between the job's terminal write and the hook.
                if machine.on_job_terminal(job):
                    summary["reconciled"] += 1
                continue
            if _age_past(doc.get("acting_since"), STALE_ACTING_AFTER, now):
                machine.fail_stale(
                    approval_id,
                    expected_status="acting",
                    note=(
                        f"acting > {STALE_ACTING_AFTER} with job "
                        f"{job_id or '-'} non-terminal; needs human review"
                    ),
                )
                summary["failed_stale"] += 1
                continue
            summary["watching"] += 1  # patience: the job owns the outcome
            continue

        if (
            status == "approved"
            and not doc.get("result")
            and (doc.get("command") or {}).get("name")
        ):
            # Fast action whose process died mid-call.
            if _superseded(store, collection, doc):
                machine.mark_superseded(approval_id)
                summary["superseded"] += 1
                continue
            if int(doc.get("sweep_retries") or 0) >= MAX_SWEEP_RETRIES:
                machine.fail_stale(
                    approval_id,
                    expected_status="approved",
                    note=f"fast action still unresolved after {MAX_SWEEP_RETRIES} redrive attempts",
                )
                summary["failed_stale"] += 1
                continue
            if not _age_past(doc.get("decided_at"), FAST_REDRIVE_AFTER, now):
                summary["watching"] += 1  # may still be running right now
                continue
            try:
                machine.redrive_fast(approval_id)
                summary["redriven"] += 1
            except Exception:
                # Conflict = someone else moved it first; sweep moves on.
                log.exception("redrive of %s skipped", approval_id)
                summary["watching"] += 1

    if any(summary.values()):
        log.info("sweeper tick", extra=summary)
    return summary
