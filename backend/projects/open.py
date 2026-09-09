"""Open an empty show so the operator can start without leftover lab data."""

from __future__ import annotations

import uuid
from typing import Any

from backend.api.present import project_to_api
from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso

PROJECTS = "pc-projects"
DEFAULT_TITLE = "Untitled show"
MAX_TITLE = 80


def open_show(store: FirestoreStore, *, title: str | None = None) -> dict[str, Any]:
    cleaned = (title or "").strip()
    if not cleaned:
        cleaned = DEFAULT_TITLE
    cleaned = cleaned[:MAX_TITLE]
    project_id = f"show-{uuid.uuid4().hex[:12]}"
    created_at = utc_now_iso()
    store.set_doc(
        PROJECTS,
        project_id,
        {
            "project_id": project_id,
            "title": cleaned,
            "created_at": created_at,
        },
    )
    return project_to_api(
        project_id=project_id,
        title=cleaned,
        created_at=created_at,
        jobs=[],
    )


def rename_show(
    store: FirestoreStore,
    project_id: str,
    *,
    title: str,
    jobs: list[Any] | None = None,
) -> dict[str, Any]:
    cleaned = (title or "").strip()
    if not cleaned:
        raise ValueError("title required")
    cleaned = cleaned[:MAX_TITLE]
    doc = store.get_doc(PROJECTS, project_id)
    if doc is None:
        raise KeyError(project_id)
    created_at = str(doc.get("created_at") or utc_now_iso())
    store.set_doc(
        PROJECTS,
        project_id,
        {
            **doc,
            "project_id": project_id,
            "title": cleaned,
            "created_at": created_at,
        },
    )
    return project_to_api(
        project_id=project_id,
        title=cleaned,
        created_at=created_at,
        jobs=list(jobs or []),
    )
