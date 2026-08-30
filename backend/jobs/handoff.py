"""Handoff Validator, silent mode (spec S0b, plan A-5, AC-S0b.1).

Runs inside the spine at every station transition: verifies a turnover
manifest (v1 JSON: files with ref/sha256/bytes) against the actually
delivered files. Discrepancies block the transition, emit reason codes,
and write a real annotation referencing `job_id` (C-4.3). No UI in
Stage 1. Manifests never pass silently: an unreadable manifest is a
block, not a skip.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso

ANNOTATION_COLLECTION = "pc-annotations"


@dataclass
class HandoffResult:
    passed: bool
    codes: list[str] = field(default_factory=list)
    blocked_files: list[str] = field(default_factory=list)
    annotation_id: str | None = None


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _codes_and_blocks(
    manifest: dict[str, Any], delivered: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    codes: list[str] = []
    blocked: list[str] = []
    if (
        not isinstance(manifest, dict)
        or manifest.get("version") != 1
        or not isinstance(manifest.get("files"), list)
    ):
        return ["MANIFEST_INVALID"], []

    expected: list[dict[str, Any]] = manifest["files"]
    delivered_by_ref = {
        d.get("ref"): d for d in delivered if isinstance(d, dict) and d.get("ref")
    }

    if len(expected) != len(delivered):
        codes.append("COUNT_MISMATCH")

    for entry in expected:
        ref = entry.get("ref")
        if not ref or ref not in delivered_by_ref:
            codes.append("MISSING_FILE")
            blocked.append(str(ref))
            continue
        got = delivered_by_ref[ref]
        expected_sha = entry.get("sha256")
        got_sha = got.get("sha256")
        if expected_sha and got_sha and expected_sha != got_sha:
            codes.append("CHECKSUM_MISMATCH")
            blocked.append(str(ref))
    return codes, blocked


class HandoffValidator:
    def __init__(self, store: FirestoreStore | None = None) -> None:
        self._store = store

    @classmethod
    def without_store(cls) -> HandoffValidator:
        """Pure gate for unit contexts (no annotation persistence)."""
        return cls(store=None)

    def validate(
        self,
        manifest: dict[str, Any],
        delivered: list[dict[str, Any]],
        *,
        job_id: str,
    ) -> HandoffResult:
        codes, blocked = _codes_and_blocks(manifest, delivered)
        result = HandoffResult(passed=not codes, codes=codes, blocked_files=blocked)
        if not result.passed:
            result.annotation_id = self._annotate(manifest, job_id, result)
        return result

    def _annotate(
        self, manifest: dict[str, Any], job_id: str, result: HandoffResult
    ) -> str | None:
        if self._store is None:
            return None
        doc_id = f"ann-{job_id}-{utc_now_iso().replace(':', '')}"
        self._store.set_doc(
            ANNOTATION_COLLECTION,
            doc_id,
            {
                "type": "handoff.blocked",
                "job_id": job_id,
                "project_id": manifest.get("project_id", ""),
                "from_station": manifest.get("from_station", ""),
                "to_station": manifest.get("to_station", ""),
                "codes": result.codes,
                "blocked_files": result.blocked_files,
                "at": utc_now_iso(),
            },
        )
        return doc_id
