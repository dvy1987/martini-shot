"""Read-only batch state for the Ingest Triage agent (A10-3).

The agent must see what its single-job view cannot (design decision 4):
sibling ingest jobs of the same batch. This module is strictly READ-ONLY —
one Firestore query per call, no writes, no lease side effects (C-6.3: the
queue is the only writer)."""

from __future__ import annotations

from typing import Any

JOBS_COLLECTION = "pc-jobs"


def read_ingest_batch_state(store: Any, batch_id: str) -> list[dict[str, Any]]:
    """All ingest jobs of a batch, normalized to the triage view:
    {episode_id, status, error, source_ref}. Raises on empty batch_id —
    a missing batch context is a caller bug, not an empty result."""
    if not batch_id:
        raise ValueError("batch_id is required (caller bug)")
    docs = store.list_where(JOBS_COLLECTION, "result.batch_id", batch_id)
    rows: list[dict[str, Any]] = []
    for doc in docs:
        if doc.get("station") != "ingest":
            continue
        result = doc.get("result") or {}
        refs = result.get("input_refs") or []
        source_ref = str(refs[0]) if refs else ""
        rows.append(
            {
                "episode_id": str(result.get("episode_id") or ""),
                "status": str(doc.get("status") or ""),
                "error": doc.get("error"),
                "source_ref": source_ref,
            }
        )
    return rows


def read_loudness_season_state(store: Any, batch_id: str) -> list[dict[str, Any]]:
    """All MEASURED loudness jobs of a batch (season coherence view):
    {episode_id, lufs}. Jobs without a measurement are skipped — an
    unmeasured episode cannot anchor coherence. Read-only (C-6.3)."""
    if not batch_id:
        raise ValueError("batch_id is required (caller bug)")
    docs = store.list_where(JOBS_COLLECTION, "result.batch_id", batch_id)
    rows: list[dict[str, Any]] = []
    for doc in docs:
        if doc.get("station") != "loudness":
            continue
        result = doc.get("result") or {}
        lufs = result.get("lufs")
        if lufs is None:
            continue
        rows.append(
            {
                "episode_id": str(result.get("episode_id") or ""),
                "lufs": float(lufs),
            }
        )
    return rows
