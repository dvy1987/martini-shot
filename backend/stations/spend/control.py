"""Intake pause flag in Firestore (Spend Control acts, does not only report)."""

from __future__ import annotations

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


def pause_intake(store: FirestoreStore, station: str, reason: str) -> None:
    doc = store.get_doc(CONTROL, INTAKE_DOC) or {}
    paused = list(doc.get("paused_stations") or [])
    if station not in paused:
        paused.append(station)
    store.set_doc(
        CONTROL,
        INTAKE_DOC,
        {
            **doc,
            "paused_stations": paused,
            "reason": reason,
            "updated_at": utc_now_iso(),
        },
    )


def resume_intake(store: FirestoreStore, station: str) -> None:
    doc = store.get_doc(CONTROL, INTAKE_DOC) or {}
    paused = [s for s in list(doc.get("paused_stations") or []) if s != station]
    store.set_doc(
        CONTROL,
        INTAKE_DOC,
        {**doc, "paused_stations": paused, "updated_at": utc_now_iso()},
    )
