"""Classify ingested bytes: probe, decode, audio presence (AC-S1.1)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from backend.core.media import FFmpeg

REASON_EMPTY = "empty_payload"
REASON_PROBE = "corrupt_probe"
REASON_DECODE = "corrupt_decode"
REASON_MISSING_AUDIO = "missing_audio"

Verdict = tuple[str, str | None, dict[str, Any]]


def classify_payload(payload: bytes, media: FFmpeg) -> Verdict:
    """Return (pass|quarantined, reason_code, probe_dict)."""
    if not payload:
        return "quarantined", REASON_EMPTY, {}
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
        handle.write(payload)
        tmp = Path(handle.name)
    try:
        try:
            probe = media.probe(tmp)
        except Exception:
            return "quarantined", REASON_PROBE, {}
        if not media.decode_clean(tmp):
            return "quarantined", REASON_DECODE, probe
        if not probe.get("has_audio"):
            return "quarantined", REASON_MISSING_AUDIO, probe
        return "pass", None, probe
    finally:
        tmp.unlink(missing_ok=True)
