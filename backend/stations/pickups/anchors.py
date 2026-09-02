"""Anchor prompts for pickups ops (D-5). Generation stays behind eval + --yes."""

from __future__ import annotations


def build_anchor_prompt(op: str, hint: str, *, strengthen: bool = False) -> str:
    prompt = f"{hint.strip()} Keep everything else the same. Op={op}."
    if strengthen:
        prompt += " Use the reference keyframe as a hard identity lock."
    return prompt


def prev_frame_note(index: int) -> str:
    if index <= 0:
        return "first frame; no previous-frame condition"
    return f"condition on previous frame index {index - 1:05d}"
