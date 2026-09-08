"""Stage 1a Omni quality rows (Relight / Coverage / Camera Language).

Original GCS tapes only. A Veo-finished row is not an Omni pass.
"""

from __future__ import annotations

from typing import Any

from backend.core.models import OMNI_MODEL
from backend.stations.relight.run import FLICKER_GATE

TABLE = "gs://martini-shot-media/original-probes/20260907T080221Z-table-cup.mp4"
FLORIST = "gs://martini-shot-media/original-probes/20260907T081720Z-florist-tulips.mp4"
CAFE = "gs://martini-shot-media/original-probes/20260907T080221Z-cafe-sign.mp4"

FLICKER_THRESHOLD = FLICKER_GATE

STATIONS: dict[str, dict[str, Any]] = {
    "relight": {
        "command": "relight_shot",
        "prefix": "rlt",
        "op": "relight",
        "sources": [
            {
                "id": "table-lamp",
                "kind": "practical_lamp",
                "title": "Café table — practical lamp",
                "source_uri": TABLE,
                "args": {"preset": "practical_lamp"},
            },
            {
                "id": "florist-daylight",
                "kind": "ambient_daylight",
                "title": "Florist — ambient daylight",
                "source_uri": FLORIST,
                "args": {"preset": "ambient_daylight"},
            },
            {
                "id": "cafe-noir",
                "kind": "noir",
                "title": "Café sign — noir",
                "source_uri": CAFE,
                "args": {"preset": "noir"},
            },
        ],
    },
    "coverage": {
        "command": "generate_coverage",
        "prefix": "cov",
        "op": "coverage",
        "sources": [
            {
                "id": "table-reverse",
                "kind": "reverse_angle",
                "title": "Café table — reverse",
                "source_uri": TABLE,
                "args": {
                    "angle": "reverse_angle",
                    "intent": "Reverse angle on the same two people",
                    "reference_uris": [TABLE],
                },
            },
            {
                "id": "florist-close",
                "kind": "close_up",
                "title": "Florist — close-up",
                "source_uri": FLORIST,
                "args": {
                    "angle": "close_up",
                    "intent": "Close-up of the tulips and florist",
                    "reference_uris": [FLORIST],
                },
            },
            {
                "id": "cafe-wide",
                "kind": "wide_establishing",
                "title": "Café sign — wide establishing",
                "source_uri": CAFE,
                "args": {
                    "angle": "wide_establishing",
                    "intent": "Wide establishing of the café",
                    "reference_uris": [CAFE],
                },
            },
        ],
    },
    "camera_language": {
        "command": "apply_camera_language",
        "prefix": "cam",
        "op": "camera_language",
        "sources": [
            {
                "id": "table-dolly",
                "kind": "dolly_tracking",
                "title": "Café table — dolly",
                "source_uri": TABLE,
                "args": {"movement": "dolly_tracking"},
            },
            {
                "id": "florist-still",
                "kind": "locked_off",
                "title": "Florist — locked-off",
                "source_uri": FLORIST,
                "args": {"movement": "locked_off"},
            },
            {
                "id": "cafe-steadicam",
                "kind": "steadicam",
                "title": "Café sign — Steadicam",
                "source_uri": CAFE,
                "args": {"movement": "steadicam"},
            },
        ],
    },
}


def is_omni_render(record: dict[str, Any]) -> bool:
    if record.get("omni_fallback") is True:
        return False
    return "omni" in str(record.get("render_model") or "").lower()


def summarize_quality(
    records: list[dict[str, Any]], *, station: str, op: str
) -> dict[str, Any]:
    n = len(records)
    omni_n = sum(1 for row in records if is_omni_render(row))
    flickers = [
        float(row["flicker"])
        for row in records
        if isinstance(row.get("flicker"), (int, float))
    ]
    mean_flicker = sum(flickers) / len(flickers) if flickers else 1.0
    fail_reasons: list[str] = []
    if n == 0:
        fail_reasons.append("no_records")
    if omni_n != n:
        fail_reasons.append("omni_fallback_or_non_omni_model")
    if len(flickers) != n:
        fail_reasons.append("missing_flicker")
    if mean_flicker >= FLICKER_THRESHOLD:
        fail_reasons.append("mean_flicker_gate")
    if any(f >= FLICKER_THRESHOLD for f in flickers):
        fail_reasons.append("per_shot_flicker_gate")
    if any(row.get("qc_decision") != "pass" for row in records):
        fail_reasons.append("qc_not_pass")
    if any(row.get("alternate_status") != "draft" for row in records):
        fail_reasons.append("alternate_not_draft")
    if any(row.get("alternate_op") != op for row in records):
        fail_reasons.append("alternate_not_op")
    omni_rate = (omni_n / n) if n else 0.0
    return {
        "suite": f"{station}_quality",
        "metric": "mean_output_flicker",
        "threshold": FLICKER_THRESHOLD,
        "mean_output_flicker": round(mean_flicker, 5),
        "omni_render_rate": omni_rate,
        "omni_model": OMNI_MODEL,
        "n": n,
        "renders_completed": omni_n,
        "pass": not fail_reasons,
        "fail_reason": ",".join(fail_reasons),
    }
