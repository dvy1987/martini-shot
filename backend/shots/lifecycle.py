"""Shot + alternate lifecycle over Firestore (AL-1, TDD).

The shot document is the source of truth for `locked` and
`current_alternate_id`; alternate statuses are derived labels kept in step
by the transitions below. Lock state is read by the approval machine's
locked-target guard (central, dispatch-time).
"""

from __future__ import annotations

import uuid
from typing import Any

from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso

SHOTS = "pc-shots"
ALTERNATES = "pc-alternates"

# Commands that must stay executable on a locked shot (unlock is the whole
# point; lock is idempotent). The dispatcher's locked-target guard exempts
# exactly these.
LOCK_COMMANDS = {"lock_shot", "unlock_shot"}

ALTERNATE_STATUSES = {"draft", "continuity", "retired"}


def ensure_shot(store: FirestoreStore, *, project_id: str, title: str) -> str:
    """Idempotently create a shot record; returns its id."""
    shot_id = f"shot-{uuid.uuid4().hex[:12]}"
    store.set_doc(
        SHOTS,
        shot_id,
        {
            "shot_id": shot_id,
            "project_id": project_id,
            "title": title,
            "locked": False,
            "locked_by": None,
            "locked_at": None,
            "current_alternate_id": None,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        },
    )
    return shot_id


def get_shot(store: FirestoreStore, shot_id: str) -> dict[str, Any] | None:
    return store.get_doc(SHOTS, shot_id)


def is_locked(store: FirestoreStore, shot_id: str) -> bool:
    doc = store.get_doc(SHOTS, shot_id)
    return bool(doc.get("locked")) if doc else False


def lock_shot(store: FirestoreStore, shot_id: str, *, locked_by: str) -> None:
    def _apply(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            **doc,
            "locked": True,
            "locked_by": locked_by,
            "locked_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }

    store.transactional_update(SHOTS, shot_id, _apply)


def unlock_shot(store: FirestoreStore, shot_id: str) -> None:
    def _apply(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            **doc,
            "locked": False,
            "locked_by": None,
            "locked_at": None,
            "updated_at": utc_now_iso(),
        }

    store.transactional_update(SHOTS, shot_id, _apply)


def record_scene_understanding(
    store: FirestoreStore,
    shot_id: str,
    *,
    spoken_words: str,
    has_speech: bool,
    scene: str,
    cost_micros: int = 0,
) -> dict[str, Any]:
    """Persist ingest watch fields on the shot (the scene record)."""
    spoken = str(spoken_words or "").strip() if has_speech else ""
    understanding = {
        "ingested": True,
        "spoken_words": spoken,
        "has_speech": bool(has_speech) and bool(spoken),
        "scene": str(scene or "").strip(),
        "cost_micros": int(cost_micros),
        "updated_at": utc_now_iso(),
    }

    def _apply(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            **doc,
            "scene_understanding": understanding,
            "updated_at": utc_now_iso(),
        }

    store.transactional_update(SHOTS, shot_id, _apply)
    return understanding


def record_alternate(
    store: FirestoreStore,
    *,
    shot_id: str,
    project_id: str,
    op: str,
    artifact_ref: str,
    eval_scores: dict[str, float],
    tier: str = "draft",
) -> str:
    """Register a generated clip as an ALTERNATE (never in-continuity).
    `tier` is the render grade (draft 360p vs master 720p); `status` stays
    `draft` until add_to_continuity promotes it."""
    alternate_id = f"alt-{uuid.uuid4().hex[:12]}"
    store.set_doc(
        ALTERNATES,
        alternate_id,
        {
            "alternate_id": alternate_id,
            "shot_id": shot_id,
            "project_id": project_id,
            "op": op,
            "artifact_ref": artifact_ref,
            "eval_scores": eval_scores,
            "tier": tier,
            "status": "draft",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        },
    )
    return alternate_id


def promote_to_continuity(
    store: FirestoreStore, shot_id: str, alternate_id: str
) -> None:
    """Make this alternate the shot's current cut; the previous one is
    retired (kept for revert). Called only by the add_to_continuity command
    (approval-tracked through H-0)."""
    previous: str | None = None

    def _apply(doc: dict[str, Any]) -> dict[str, Any]:
        nonlocal previous
        previous = doc.get("current_alternate_id") or None
        return {
            **doc,
            "current_alternate_id": alternate_id,
            "updated_at": utc_now_iso(),
        }

    store.transactional_update(SHOTS, shot_id, _apply)
    _set_alternate_status(store, alternate_id, "continuity")
    if previous and previous != alternate_id:
        _set_alternate_status(store, previous, "retired")


def retire_alternate(store: FirestoreStore, alternate_id: str) -> None:
    """Remove an alternate from continuity (the one-click revert path)."""
    alternate = store.get_doc(ALTERNATES, alternate_id) or {}
    shot_id = str(alternate.get("shot_id") or "")
    _set_alternate_status(store, alternate_id, "retired")
    if shot_id:
        current = get_shot(store, shot_id) or {}
        if current.get("current_alternate_id") == alternate_id:

            def _clear(doc: dict[str, Any]) -> dict[str, Any]:
                return {
                    **doc,
                    "current_alternate_id": None,
                    "updated_at": utc_now_iso(),
                }

            store.transactional_update(SHOTS, shot_id, _clear)


def list_alternates(store: FirestoreStore, shot_id: str) -> list[dict[str, Any]]:
    return store.list_where(ALTERNATES, "shot_id", shot_id)


def _set_alternate_status(
    store: FirestoreStore, alternate_id: str, status: str
) -> None:
    if status not in ALTERNATE_STATUSES:
        raise ValueError(f"unknown alternate status {status!r}")

    def _apply(doc: dict[str, Any]) -> dict[str, Any]:
        return {**doc, "status": status, "updated_at": utc_now_iso()}

    store.transactional_update(ALTERNATES, alternate_id, _apply)


def stamp_alternate_qc(
    store: FirestoreStore,
    alternate_id: str,
    *,
    draft_state: str,
    visual_qc: str,
    cost_delta_micros: int | None = None,
) -> None:
    """Persist Visual QC / draft-first state onto the alternate (D-11)."""

    def _apply(doc: dict[str, Any]) -> dict[str, Any]:
        updated = {
            **doc,
            "draft_state": draft_state,
            "visual_qc": visual_qc,
            "updated_at": utc_now_iso(),
        }
        if cost_delta_micros is not None:
            updated["cost_delta_micros"] = int(cost_delta_micros)
        return updated

    store.transactional_update(ALTERNATES, alternate_id, _apply)
