"""D-2 loudness verdict tables + ffmpeg ±0.3 dB match (AC-S3.1)."""

from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.core.media import FFmpeg
from backend.stations.loudness.verdict import (
    BROADCAST_TARGET_LUFS,
    FFMPEG_MATCH_TOLERANCE_DB,
    STREAMING_TARGET_LUFS,
    matches_ffmpeg,
    me_present,
    stem_diagnosis,
    verdict,
)

SPIKE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "spike" / "shot-03-clearing.mp4"
)


@pytest.mark.parametrize(
    ("lufs", "target", "peak", "expected"),
    [
        (-16.0, STREAMING_TARGET_LUFS, -2.0, "pass"),
        (-15.0, STREAMING_TARGET_LUFS, -2.0, "pass"),
        (-17.0, STREAMING_TARGET_LUFS, -2.0, "pass"),
        (-14.8, STREAMING_TARGET_LUFS, -2.0, "fail_hot"),
        (-17.2, STREAMING_TARGET_LUFS, -2.0, "fail_quiet"),
        (-16.0, STREAMING_TARGET_LUFS, -0.5, "fail_true_peak"),
        (-24.0, BROADCAST_TARGET_LUFS, -3.0, "pass"),
        (-22.5, BROADCAST_TARGET_LUFS, -3.0, "fail_hot"),
    ],
)
def test_verdict_boundaries(
    lufs: float, target: float, peak: float, expected: str
) -> None:
    assert verdict(lufs, target=target, true_peak_dbtp=peak) == expected


def test_stem_and_me_helpers() -> None:
    assert stem_diagnosis(-12.0, -20.0) == "dialogue_hot"
    assert stem_diagnosis(-22.0, -12.0) == "music_hot"
    assert stem_diagnosis(-16.0, -16.5) == "balanced"
    assert me_present(2) is True
    assert me_present(1) is False


def test_stem_diagnosis_catches_a_loud_low_broadband_room_a_music_band_miss() -> None:
    """A storm/wind/room bed sits low and broadband, not in the 4-12 kHz
    'music' band. Without the room-band reading this reads 'balanced' and
    the station just turns the whole mix up (2026-09-09 demo miss)."""
    dialogue, music, room = -16.0, -16.5, -6.0
    assert stem_diagnosis(dialogue, music) == "balanced"
    assert stem_diagnosis(dialogue, music, room) == "music_hot"
    # A quiet room with the same music-band reading stays balanced.
    assert stem_diagnosis(dialogue, music, -24.0) == "balanced"


def test_measured_lufs_matches_ffmpeg_reference() -> None:
    if not SPIKE.exists():
        pytest.skip("spike fixture not on disk")
    settings = get_settings()
    media = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
    report = media.loudness_report(SPIKE)
    reference = media.loudness_lufs(SPIKE)
    assert matches_ffmpeg(report["lufs"], reference)
    assert abs(report["lufs"] - reference) <= FFMPEG_MATCH_TOLERANCE_DB
