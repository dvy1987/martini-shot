"""Scene-aware loudness targets (owner 2026-09-07).

Dialogue stays easy to hear. The show stays in one loudness family.
A whisper is quieter than talk; an explosion, a crash of pans, or a
sudden disruption is louder. The meter still wins on the number; this
table only chooses the TARGET.
"""

from __future__ import annotations

SCENE_CLASSES = (
    "silence",
    "whisper",
    "dialogue",
    "shout",
    "impact",
    "explosion",
)

DIALOGUE_ANCHOR_LUFS = -16.0
SPEECH_FLOOR_LUFS = -23.0
SHOW_SPAN_LU = 8.0
TRUE_PEAK_CEILING_DBTP = -1.5

# Offset from the dialogue anchor. Impacts/explosions may jump the family;
# speech classes stay audible and near the season.
_OFFSETS_LU = {
    "silence": -8.0,
    "whisper": -4.0,
    "dialogue": 0.0,
    "shout": 2.0,
    "impact": 5.0,
    "explosion": 7.0,
}


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
    speech = scene_class in {"whisper", "dialogue", "shout"}
    if speech:
        target = max(target, SPEECH_FLOOR_LUFS)
    if season_median is not None and scene_class != "explosion":
        lo = season_median - SHOW_SPAN_LU
        hi = season_median + SHOW_SPAN_LU
        if scene_class == "impact":
            hi = season_median + SHOW_SPAN_LU + 2.0
        target = min(max(target, lo), hi)
        if speech:
            target = max(target, SPEECH_FLOOR_LUFS)
    return round(target, 1)


def clamp_agent_target(agent_target: float, scene_target: float) -> float:
    """Agent may nudge ±2 LU around the table. Speech never drops under the floor."""
    clamped = min(scene_target + 2.0, max(scene_target - 2.0, agent_target))
    return round(
        max(clamped, SPEECH_FLOOR_LUFS)
        if scene_target >= SPEECH_FLOOR_LUFS
        else clamped,
        1,
    )
