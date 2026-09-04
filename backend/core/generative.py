"""Thin adapter over the Google media-model family (A5: thin adapters,
thick system). Omni video on the Vertex Agent Platform Interactions API is
the PRIMARY video path; Veo stays the fallback (decision log 2026-09-04,
evidence docs/evidence/G0/omni_probe_2026-09-04.json).

Proven call shape (the one that survived every probe failure):
- media by gs:// URI (Vertex runtime)
- op named via generation_config.video_config.task ("extend"/"edit")
- NO response_format — aspect_ratio there is rejected for extend/edit tasks
  and poisoned every earlier attempt
- prompts in the docs' simple style; elaborate instructions caused a
  generation refusal
"""

from __future__ import annotations

import math
from typing import Any

from backend.core.config import Settings
from backend.core.models import OMNI_MODEL

# Vertex list prices (2026-09): Omni 1.1 Flash ~$0.10/s of output at 720p;
# 360p drafts are ~1/3 of that. Integer micro-units (C-6.4), ceil per second.
PRICE_PER_SECOND_MICROS = {"720p": 100_000, "360p": 33_334}


def estimate_extend_cost_micros(duration_s: float, *, resolution: str = "720p") -> int:
    """Draft-first cost estimate (C-6.4): integer micros, ceil per second."""
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")
    if resolution not in PRICE_PER_SECOND_MICROS:
        raise ValueError(
            f"unknown resolution {resolution!r} "
            f"(table: {sorted(PRICE_PER_SECOND_MICROS)})"
        )
    per_second = PRICE_PER_SECOND_MICROS[resolution]
    return int(math.ceil(duration_s) * per_second)


def build_extend_prompt(shot_title: str) -> str:
    """Docs' extend guidance: keep it simple; the scene continues as
    established. Elaborate directions caused a generation refusal."""
    return (
        "Extend this video. The scene continues exactly as established, "
        "as if the shot simply keeps rolling. "
        "Keep everything else the same."
    )


def omni_extend(
    settings: Settings,
    *,
    input_uri: str,
    prompt: str,
    task: str = "extend",
    timeout_s: int = 900,
) -> dict[str, Any]:
    """One real Omni interaction (billed). Returns video bytes + usage.
    Not an HTTP path (C-6.5): stations run this inside lease-queue jobs."""
    from google import genai

    client = genai.Client(
        enterprise=True,
        project=settings.gcp_project_id,
        location="global",
    )
    interaction = client.interactions.create(
        model=OMNI_MODEL,
        input=[
            {"type": "text", "text": prompt},
            {"type": "video", "uri": input_uri, "mime_type": "video/mp4"},
        ],
        generation_config={"video_config": {"task": task}},
        timeout=timeout_s,
    )
    status = str(getattr(interaction, "status", "unknown"))
    if status != "completed":
        errors = getattr(interaction, "errors", None)
        raise RuntimeError(f"omni interaction {status}: {str(errors)[:300]}")
    video_bytes = _extract_video(interaction)
    if not video_bytes:
        raise RuntimeError("omni interaction completed with no video output")
    usage = getattr(interaction, "usage", None)
    return {
        "video_bytes": video_bytes,
        "interaction_id": str(getattr(interaction, "id", "")),
        "total_token_count": getattr(usage, "total_token_count", None),
    }


def _extract_video(interaction: Any) -> bytes | None:
    """Video out of an SDK interaction object (output_video, possibly a
    signed URI) — mirrors the probe's proven extraction."""
    import base64
    import urllib.request

    output_video = getattr(interaction, "output_video", None)
    if output_video is None:
        return None
    data = getattr(output_video, "data", None)
    if isinstance(data, (bytes, bytearray)) and data:
        return bytes(data)
    if isinstance(data, str) and data:
        try:
            return base64.b64decode(data)
        except Exception:
            return data.encode("utf-8")
    uri = getattr(output_video, "uri", None)
    if uri:
        try:
            with urllib.request.urlopen(str(uri), timeout=180) as response:
                return response.read()
        except Exception:
            return None
    return None
