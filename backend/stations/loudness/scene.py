"""Scene-aware loudness targets (owner 2026-09-07).

Six kinds: quiet / normal / loud, each with or without dialogue.
Comfortable hearing range: loud may sit louder, quiet softer.
If there is speech, it stays hearable. A continuing shot blends
toward the previous mix. The meter still wins on the number.
"""

from __future__ import annotations

SCENE_CLASSES = (
    "quiet-no-dialogue",
    "quiet-with-dialogue",
    "normal-no-dialogue",
    "normal-with-dialogue",
    "loud-no-dialogue",
    "loud-with-dialogue",
)

DIALOGUE_ANCHOR_LUFS = -16.0
SPEECH_FLOOR_LUFS = -23.0
SHOW_SPAN_LU = 8.0
TRUE_PEAK_CEILING_DBTP = -1.5
COMFORT_LO_LUFS = -26.0
COMFORT_HI_LUFS = -10.0

# Offset from the dialogue anchor (normal-with-dialogue ≈ -16).
_OFFSETS_LU = {
    "quiet-no-dialogue": -8.0,
    "quiet-with-dialogue": -4.0,
    "normal-no-dialogue": 0.0,
    "normal-with-dialogue": 0.0,
    "loud-no-dialogue": 6.0,
    "loud-with-dialogue": 4.0,
}


def has_dialogue(scene_class: str) -> bool:
    return scene_class.endswith("-with-dialogue")


def season_median_lufs(rows: list[float]) -> float | None:
    values = sorted(float(v) for v in rows)
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def scene_target_lufs(
    scene_class: str,
    *,
    season_median: float | None = None,
    dialogue_anchor: float = DIALOGUE_ANCHOR_LUFS,
) -> float:
    """Integrated LUFS the station should mix toward for this scene class."""
    if scene_class not in _OFFSETS_LU:
        raise ValueError(f"unknown scene class {scene_class!r}")
    target = dialogue_anchor + _OFFSETS_LU[scene_class]
    target = min(max(target, COMFORT_LO_LUFS), COMFORT_HI_LUFS)
    if has_dialogue(scene_class):
        target = max(target, SPEECH_FLOOR_LUFS)
    if season_median is not None and not scene_class.startswith("loud-"):
        lo = season_median - SHOW_SPAN_LU
        hi = season_median + SHOW_SPAN_LU
        target = min(max(target, lo), hi)
        if has_dialogue(scene_class):
            target = max(target, SPEECH_FLOOR_LUFS)
    return round(target, 1)


def continuation_target(
    scene_class: str,
    *,
    previous_target: float | None,
    is_continuation: bool,
    season_median: float | None = None,
) -> float:
    """If this shot continues the last one, speech and room don't jump."""
    table = scene_target_lufs(scene_class, season_median=season_median)
    if not is_continuation or previous_target is None:
        return table
    blended = (table + float(previous_target)) / 2.0
    blended = min(max(blended, COMFORT_LO_LUFS), COMFORT_HI_LUFS)
    if has_dialogue(scene_class):
        blended = max(blended, SPEECH_FLOOR_LUFS)
    return round(blended, 1)


def clamp_agent_target(agent_target: float, scene_target: float) -> float:
    """Agent may nudge ±2 LU around the table. Speech never drops under the floor."""
    clamped = min(scene_target + 2.0, max(scene_target - 2.0, agent_target))
    clamped = min(max(clamped, COMFORT_LO_LUFS), COMFORT_HI_LUFS)
    if scene_target >= SPEECH_FLOOR_LUFS:
        clamped = max(clamped, SPEECH_FLOOR_LUFS)
    return round(clamped, 1)
