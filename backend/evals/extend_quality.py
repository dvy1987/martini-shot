"""D-9 Extend quality gate (owner 2026-09-07).

A Veo-finished job is not an Omni pass. Original clips + Omni render +
flicker under the bar + draft alternate.
"""

from __future__ import annotations

from typing import Any

from backend.core.models import OMNI_MODEL
from backend.stations.extend.run import FLICKER_GATE

FLICKER_THRESHOLD = FLICKER_GATE


def is_omni_render(record: dict[str, Any]) -> bool:
    if record.get("omni_fallback") is True:
        return False
    model = str(record.get("render_model") or "").lower()
    return "omni" in model


def summarize_extend_quality(
    records: list[dict[str, Any]],
    *,
    min_drafts: int = 0,
    min_masters: int = 0,
) -> dict[str, Any]:
    n = len(records)
    omni_n = sum(1 for row in records if is_omni_render(row))
    drafts = [row for row in records if str(row.get("tier") or "draft") != "master"]
    masters = [row for row in records if str(row.get("tier") or "") == "master"]
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
    if len(drafts) < min_drafts:
        fail_reasons.append("too_few_drafts")
    if len(masters) < min_masters:
        fail_reasons.append("too_few_masters")
    omni_rate = (omni_n / n) if n else 0.0
    return {
        "suite": "extend_quality",
        "metric": "mean_output_flicker",
        "threshold": FLICKER_THRESHOLD,
        "mean_output_flicker": round(mean_flicker, 5),
        "omni_render_rate": omni_rate,
        "omni_model": OMNI_MODEL,
        "n": n,
        "drafts": len(drafts),
        "masters": len(masters),
        "renders_completed": omni_n,
        "pass": not fail_reasons,
        "fail_reason": ",".join(fail_reasons),
    }
