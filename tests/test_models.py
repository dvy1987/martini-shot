"""A-1 RED tests: core/models.py — model IDs live ONLY here (ADR 0002, G0-verified IDs)."""

from pathlib import Path

from backend.core import models

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def test_text_model_pin() -> None:
    """Owner ruling: ALL text-LLM reasoning on gemini-3.7-flash, thinking HIGH."""
    assert models.TEXT_MODEL == "gemini-3.7-flash"
    assert models.THINKING_LEVEL == "HIGH"
    assert models.THROUGH_THOUGHTS is True


def test_video_model_pins_g0_verified() -> None:
    """Omni: Vertex serves -preview (G0 probe). Veo: GA -001 ID proven at G0 sweep."""
    assert models.OMNI_MODEL == "gemini-omni-1.1-flash-preview"
    assert models.VEO_MODEL == "veo-3.1-fast-generate-001"


def test_model_ids_live_only_in_core_models() -> None:
    """ADR 0002: model IDs are centralized in backend/core/models.py — never
    hard-coded elsewhere in backend product code."""
    offenders: list[str] = []
    for py in BACKEND.rglob("*.py"):
        rel = py.relative_to(BACKEND).as_posix()
        if rel.replace("\\", "/") == "core/models.py":
            continue
        text = py.read_text(encoding="utf-8")
        for needle in ("gemini-", "veo-", "chirp-3", "imagen-"):
            if needle in text:
                offenders.append(f"{rel}: {needle}")
    assert not offenders, f"model IDs outside core/models.py: {offenders}"
