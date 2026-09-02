"""Loudness Marshal verdict tables (S3 / D-2). Pure logic; ffmpeg is the meter."""

from __future__ import annotations

STREAMING_TARGET_LUFS = -16.0
BROADCAST_TARGET_LUFS = -24.0
TOLERANCE_LU = 1.0
TRUE_PEAK_CEILING_DBTP = -1.0
FFMPEG_MATCH_TOLERANCE_DB = 0.3

TARGETS = {
    "streaming": STREAMING_TARGET_LUFS,
    "broadcast": BROADCAST_TARGET_LUFS,
}


def verdict(
    lufs: float,
    *,
    target: float,
    true_peak_dbtp: float | None = None,
) -> str:
    if true_peak_dbtp is not None and true_peak_dbtp > TRUE_PEAK_CEILING_DBTP:
        return "fail_true_peak"
    delta = lufs - target
    if abs(delta) <= TOLERANCE_LU:
        return "pass"
    return "fail_hot" if delta > 0 else "fail_quiet"


def stem_diagnosis(dialogue_band_lufs: float, music_band_lufs: float) -> str:
    """ffmpeg highpass/lowpass band comparison (dialogue ~300–3k, music highs)."""
    gap = dialogue_band_lufs - music_band_lufs
    if gap > 3.0:
        return "dialogue_hot"
    if gap < -3.0:
        return "music_hot"
    return "balanced"


def me_present(audio_streams: int) -> bool:
    return audio_streams >= 2


def matches_ffmpeg(measured: float, reference: float) -> bool:
    return abs(measured - reference) <= FFMPEG_MATCH_TOLERANCE_DB
