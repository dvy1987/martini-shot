"""Original eval/demo footage when a model refuses a tape for ownership."""

from __future__ import annotations

from typing import Any

from backend.core.config import Settings
from backend.core.generative import (
    _extract_video,
    _omni_client,
    estimate_extend_cost_micros,
)
from backend.core.models import OMNI_MODEL

_OWNERSHIP_MARKERS = (
    "recitation",
    "third-party content",
    "third party content",
    "copyright",
    "infringement",
    "image_recitation",
    "prohibited_content",
    "prohibited content",
    "interests of third-party",
)

# Original scenes only — never a named film, never a public-domain short.
ORIGINAL_PROMPTS = (
    "A person at a wooden cafe table looks at a small monitor. "
    "Morning light. They speak one short sentence. Camera does not move. Eight seconds.",
    "A quiet post-production desk: headphones, a paper cup, a laptop. "
    "Soft daylight. A person nods once and speaks. Camera still. Eight seconds.",
    "An empty soundstage corner with a tungsten practical lamp. "
    "A person in a dark shirt says a short line. No camera move. Eight seconds.",
)


class OwnershipRefusal(RuntimeError):
    """Omni/Veo refused the tape as copied material. Generate a new original."""


def is_ownership_refusal(exc: BaseException | str) -> bool:
    """True when Omni/Veo refused because the tape looks copied, not because
    the product feature failed. Callers must then generate a new original clip
    that still has the defect under test — never gradient stand-ins."""
    text = str(exc).lower()
    return any(marker in text for marker in _OWNERSHIP_MARKERS)


def estimate_original_clip_cost_micros() -> int:
    """One 8s 720p Omni text-to-video draft (same table as extend)."""
    return estimate_extend_cost_micros(8.0)


def generate_original_clip(
    settings: Settings,
    prompt: str,
    *,
    timeout_s: int = 900,
) -> dict[str, Any]:
    """REAL Omni text-to-video of a brand-new scene. No Veo inside this
    function. On ownership/infringement refusal, raises OwnershipRefusal so
    the caller can try a different original prompt. Other Omni failures
    raise as-is — the owner must be told, not silently routed to Veo."""
    client = _omni_client(settings, timeout_s=timeout_s)
    try:
        interaction = client.interactions.create(
            model=OMNI_MODEL,
            input=[{"type": "text", "text": prompt}],
            timeout=timeout_s,
        )
    except Exception as exc:
        if is_ownership_refusal(exc):
            raise OwnershipRefusal(str(exc)[:400]) from exc
        raise
    status = str(getattr(interaction, "status", "unknown"))
    errors = getattr(interaction, "errors", None)
    if status != "completed":
        err_text = f"omni original clip {status}: {str(errors)[:300]}"
        if is_ownership_refusal(err_text):
            raise OwnershipRefusal(err_text)
        raise RuntimeError(err_text)
    video_bytes = _extract_video(interaction)
    if not video_bytes:
        raise RuntimeError("omni original clip completed with no video")
    return {
        "video_bytes": video_bytes,
        "model": OMNI_MODEL,
        "prompt": prompt,
        "interaction_id": str(getattr(interaction, "id", "")),
        "cost_estimate_micros": estimate_original_clip_cost_micros(),
    }


def generate_original_clip_with_retries(
    settings: Settings,
    prompts: tuple[str, ...] = ORIGINAL_PROMPTS,
) -> dict[str, Any]:
    """Try each original prompt on Omni. Stop and surface the last error if
    every prompt is an ownership refusal or Omni cannot be called. Never
    falls through to Veo here."""
    last: BaseException | None = None
    for prompt in prompts:
        try:
            return generate_original_clip(settings, prompt)
        except OwnershipRefusal as exc:
            last = exc
            continue
    if last is not None:
        raise OwnershipRefusal(
            "Omni refused every original prompt as ownership/infringement. "
            f"Last: {last}"
        ) from last
    raise RuntimeError("no original prompts provided")
