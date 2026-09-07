"""TDD contract for the D-10 correction workflow."""

from __future__ import annotations

import pytest


def test_correction_prompt_requires_explicit_intent_and_protects_subjects() -> None:
    from backend.stations.corrections.run import build_correction_prompt

    prompt = build_correction_prompt(
        intent="Replace the café sign text with OPEN",
        protected_subjects=["lead actor", "red jacket"],
        continuity_constraints=["preserve framing"],
    )

    assert "OPEN" in prompt
    assert "lead actor" in prompt
    assert "preserve framing" in prompt
    assert "Keep everything else the same" in prompt


@pytest.mark.parametrize("intent", ["", "  "])
def test_correction_prompt_refuses_ambiguous_intent(intent: str) -> None:
    from backend.stations.corrections.run import build_correction_prompt

    with pytest.raises(ValueError, match="explicit intent"):
        build_correction_prompt(
            intent=intent,
            protected_subjects=[],
            continuity_constraints=[],
        )
