"""Omni-first pickup repair; Veo fallback if Omni fails (product ruling)."""

from __future__ import annotations

from typing import Any, Callable

from backend.core.config import Settings
from backend.core.generative import omni_edit, veo_extend

OmniEdit = Callable[..., dict[str, Any]]
VeoExtend = Callable[..., dict[str, Any]]


def render_pickup_repair(
    settings: Settings,
    *,
    input_uri: str,
    prompt: str,
    omni_edit: OmniEdit = omni_edit,
    veo_extend: VeoExtend = veo_extend,
) -> dict[str, Any]:
    """Re-render a damaged pickup. Product: Omni edit first; if Omni fails,
    Veo still finishes a clip so the operator is not stuck. Callers must
    record omni_fallback / omni_error (eval must not count Veo as Omni)."""
    try:
        render = omni_edit(settings, input_uri=input_uri, prompt=prompt)
        return {
            "video_bytes": render["video_bytes"],
            "model": render.get("model"),
            "interaction_id": render.get("interaction_id"),
            "omni_fallback": False,
            "omni_error": "",
        }
    except Exception as omni_error:
        omni_error_text = f"{type(omni_error).__name__}: {str(omni_error)[:240]}"
        render = veo_extend(settings, input_uri=input_uri, prompt=prompt)
        return {
            "video_bytes": render["video_bytes"],
            "model": render.get("model"),
            "interaction_id": render.get("interaction_id"),
            "omni_fallback": True,
            "omni_error": omni_error_text,
        }
