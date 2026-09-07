"""Worklist persistence (pc-worklists)."""

from __future__ import annotations

from typing import Any

from backend.jobs.models import utc_now_iso

WORKLISTS = "pc-worklists"


def save_worklist(store: Any, project_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    payload = {**doc, "project_id": project_id, "updated_at": utc_now_iso()}
    store.set_doc(WORKLISTS, project_id, payload)
    return payload


def load_worklist(store: Any, project_id: str) -> dict[str, Any] | None:
    return store.get_doc(WORKLISTS, project_id)


def reorder_items(doc: dict[str, Any], order: list[str]) -> dict[str, Any]:
    """Human reorder of remaining needs_work / waiting items only."""
    items = list(doc.get("items") or [])
    by_id = {str(item.get("id") or item.get("station")): item for item in items}
    terminal = {
        str(item.get("id") or item.get("station"))
        for item in items
        if str(item.get("status") or "")
        in {"passed", "failed", "paused", "empty", "ok"}
    }
    remaining_ids = [
        item_id for item_id in order if item_id in by_id and item_id not in terminal
    ]
    seen = set(remaining_ids)
    rest = [
        str(item.get("id") or item.get("station"))
        for item in items
        if str(item.get("id") or item.get("station")) not in seen
    ]
    new_order = remaining_ids + rest
    doc["items"] = [by_id[item_id] for item_id in new_order if item_id in by_id]
    return doc
