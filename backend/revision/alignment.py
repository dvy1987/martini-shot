"""D-15 Revision Room: versioned script lineage, deterministic diff, and
affected-span mapping over persisted alignment evidence.

Alignment evidence itself (which script span maps to which shot_id /
timestamp range) is produced by a real Gemini video-understanding call in
the Revision Room Agent (`backend/supervisor/station_agents/revision_room.py`)
plus deterministic timestamps when caption timing already exists; this
module only owns the deterministic version lineage, diff, and span-mapping
math so it stays unit-testable without any model call (C-3.3 TDD split).
"""

from __future__ import annotations

import difflib
import uuid
from dataclasses import dataclass
from typing import Any

from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso

VERSIONS = "pc-script-versions"
ALIGNMENTS = "pc-script-alignments"


class StaleVersionError(ValueError):
    """Raised when an edit is proposed against a version that is no
    longer the project's latest — the caller must re-diff against the
    current head rather than silently overwrite (C-1.1 fail loud)."""


def latest_version(store: FirestoreStore, project_id: str) -> dict[str, Any] | None:
    rows = store.list_where(VERSIONS, "project_id", project_id)
    if not rows:
        return None
    rows.sort(key=lambda row: int(row.get("version_number") or 0))
    return rows[-1]


def create_version(
    store: FirestoreStore,
    *,
    project_id: str,
    text: str,
    based_on_version_id: str | None,
) -> dict[str, Any]:
    """Append a new script version. Idempotency (C-6.3): staleness is
    caught here, not left to the caller — `based_on_version_id` must name
    the project's current head (or None for the first version)."""
    current = latest_version(store, project_id)
    current_id = str(current.get("version_id")) if current else None
    if current is not None and based_on_version_id != current_id:
        raise StaleVersionError(
            f"based_on_version_id={based_on_version_id!r} is not the current "
            f"head {current_id!r}; re-diff against the latest version first"
        )
    version_number = int(current.get("version_number") or 0) + 1 if current else 1
    version_id = f"scr-{uuid.uuid4().hex[:12]}"
    doc = {
        "version_id": version_id,
        "project_id": project_id,
        "version_number": version_number,
        "text": text,
        "based_on_version_id": based_on_version_id,
        "created_at": utc_now_iso(),
    }
    store.set_doc(VERSIONS, version_id, doc)
    return doc


@dataclass(frozen=True)
class SpanDiff:
    start: int
    end: int
    kind: str  # "insert" | "delete" | "replace"
    old_text: str
    new_text: str


def diff_spans(old_text: str, new_text: str) -> list[SpanDiff]:
    """Deterministic char-range diff (stdlib difflib — no model call).
    Ranges are in NEW-text coordinates for inserts/replaces, so callers can
    map them straight onto the new version's alignment spans."""
    matcher = difflib.SequenceMatcher(a=old_text, b=new_text, autojunk=False)
    diffs: list[SpanDiff] = []
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            continue
        kind = {"insert": "insert", "delete": "delete", "replace": "replace"}[tag]
        diffs.append(
            SpanDiff(
                start=b0,
                end=b1 if b1 > b0 else b0,
                kind=kind,
                old_text=old_text[a0:a1],
                new_text=new_text[b0:b1],
            )
        )
    return diffs


def persist_alignment(
    store: FirestoreStore,
    *,
    version_id: str,
    spans: list[dict[str, Any]],
) -> None:
    """Persist alignment evidence: one span per {span_id, start_char,
    end_char, shot_id, language, start_ms, end_ms}. Stable span identifiers
    (C-6.3) so later diffs can reference the same span across edits."""
    store.set_doc(
        ALIGNMENTS,
        version_id,
        {"version_id": version_id, "spans": spans, "updated_at": utc_now_iso()},
    )


def get_alignment(store: FirestoreStore, version_id: str) -> list[dict[str, Any]]:
    doc = store.get_doc(ALIGNMENTS, version_id) or {}
    return list(doc.get("spans") or [])


def affected_spans(
    diffs: list[SpanDiff], alignment_spans: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Map each character-range diff onto the alignment spans it overlaps
    (deterministic interval overlap — the precision/recall the EDD suite
    scores). A diff outside every known span is still reported with an
    empty target list rather than silently dropped."""
    hits: list[dict[str, Any]] = []
    for diff in diffs:
        overlapping = [
            span
            for span in alignment_spans
            if int(span.get("start_char", -1)) < diff.end
            and int(span.get("end_char", -1)) > diff.start
        ]
        hits.append(
            {
                "diff_start": diff.start,
                "diff_end": diff.end,
                "kind": diff.kind,
                "new_text": diff.new_text,
                "affected_span_ids": [str(s.get("span_id")) for s in overlapping],
                "affected_shot_ids": sorted(
                    {str(s.get("shot_id")) for s in overlapping if s.get("shot_id")}
                ),
                "affected_languages": sorted(
                    {str(s.get("language")) for s in overlapping if s.get("language")}
                ),
            }
        )
    return hits
