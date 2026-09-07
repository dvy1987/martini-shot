"""D-10 Corrections quality gate (owner 2026-09-07).

Gradient/colorbar tape is not a pass. A Veo-finished job is not an Omni
pass. Original clips + Omni edit + flicker under the bar + draft alternate.
"""

from __future__ import annotations

from typing import Any

from backend.core.models import OMNI_MODEL
from backend.stations.corrections.run import FLICKER_GATE

FLICKER_THRESHOLD = FLICKER_GATE

SOURCES = [
    {
        "id": "cafe-sign",
        "kind": "signage",
        "title": "Café exterior — wooden sign",
        "source_uri": (
            "gs://martini-shot-media/original-probes/20260907T080221Z-cafe-sign.mp4"
        ),
        "intent": (
            "Replace the wooden sign text with OPEN. Keep the building, "
            "light, and framing the same."
        ),
        "protected_subjects": ["building", "street"],
    },
    {
        "id": "table-cup",
        "kind": "prop_removal",
        "title": "Café table — paper cup",
        "source_uri": (
            "gs://martini-shot-media/original-probes/20260907T080221Z-table-cup.mp4"
        ),
        "intent": (
            "Remove the paper cup from the table. Keep both people, wardrobe, "
            "and framing identical."
        ),
        "protected_subjects": ["both people", "wardrobe"],
    },
    {
        "id": "chalkboard-opnn",
        "kind": "on_set_graphic",
        "title": "Bookshop — misspelled chalkboard",
        "source_uri": ("gs://martini-shot-media/original-probes/chalkboard-opnn.mp4"),
        "intent": (
            "Rewrite the chalkboard text from OPNN to OPEN. Keep the shop, "
            "light, and framing the same."
        ),
        "protected_subjects": ["shop interior"],
        "generate_if_missing": (
            "A small bookshop interior. A wall chalkboard clearly misspells "
            "OPEN as OPNN in large letters. Soft indoor light. Camera does "
            "not move. Eight seconds."
        ),
    },
]


def is_omni_render(record: dict[str, Any]) -> bool:
    if record.get("omni_fallback") is True:
        return False
    model = str(record.get("render_model") or "").lower()
    return "omni" in model


def _bad_tape(uri: str) -> bool:
    lowered = uri.lower()
    return any(
        token in lowered
        for token in ("synthetic-drift", "synthetic-mark", "gradient", "colorbar")
    )


def summarize_corrections_quality(records: list[dict[str, Any]]) -> dict[str, Any]:
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
    if any(row.get("alternate_op") != "correction" for row in records):
        fail_reasons.append("alternate_not_correction")
    if any(_bad_tape(str(row.get("source_uri") or "")) for row in records):
        fail_reasons.append("gradient_or_synthetic_tape")
    omni_rate = (omni_n / n) if n else 0.0
    return {
        "suite": "corrections_quality",
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
