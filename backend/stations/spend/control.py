"""Intake pause flag in Firestore (Spend Control acts, does not only report).

Pause/resume go through the store's transactional compare-and-set (H-0
pre-mortem concurrency fix): two rapid opposite calls can never lose an
update — the last-committed transaction always wins, and whole-document
writes based on stale reads are impossible.
"""

from __future__ import annotations

from typing import Any

from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso

CONTROL = "pc-control"
INTAKE_DOC = "intake"


def is_intake_paused(store: FirestoreStore, station: str) -> bool:
    doc = store.get_doc(CONTROL, INTAKE_DOC) or {}
    if doc.get("paused_all"):
        return True
    paused = doc.get("paused_stations") or []
    return station in paused


def _apply_pause(station: str, *, add: bool, reason: str | None):
    """Pure mutation for transactional_update — same list, no store access."""

    def _apply(doc: dict[str, Any]) -> dict[str, Any]:
        paused = list(doc.get("paused_stations") or [])
        if add and station not in paused:
            paused.append(station)
        elif not add:
            paused = [s for s in paused if s != station]
        payload = {
            **doc,
            "paused_stations": paused,
            "updated_at": utc_now_iso(),
        }
        if reason is not None:
            payload["reason"] = reason
        return payload

    return _apply


def pause_intake(store: FirestoreStore, station: str, reason: str) -> None:
    store.transactional_update(
        CONTROL, INTAKE_DOC, _apply_pause(station, add=True, reason=reason)
    )


def resume_intake(store: FirestoreStore, station: str) -> None:
    store.transactional_update(
        CONTROL, INTAKE_DOC, _apply_pause(station, add=False, reason=None)
    )
