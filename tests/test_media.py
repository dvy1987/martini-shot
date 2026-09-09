"""A-4 RED tests: core/media.py — real ffmpeg/ffprobe wrapper on REAL fixtures
(plan A-4 DoD: round-trip on fixtures; ±1 frame per AC-S2.2 part 1)."""

from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.core.media import FFmpeg

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "spike"


@pytest.fixture()
def media() -> FFmpeg:
    settings = get_settings()
    assert settings.ffmpeg_bin and settings.ffprobe_bin, (
        "FFMPEG_BIN/FFPROBE_BIN must be configured (real binaries, no shims)"
    )
    return FFmpeg(ffmpeg_bin=settings.ffmpeg_bin, ffprobe_bin=settings.ffprobe_bin)


def test_probe_reports_duration_fps_codec(media: FFmpeg) -> None:
    info = media.probe(FIXTURES / "shot-01-meadow.mp4")
    assert 9.5 <= info["duration_s"] <= 11.0  # 10 s recuts from G0 (verified live)
    assert info["codec"] in ("h264", "avc1")
    assert 0.0 < info["fps"] <= 60.0


def test_extract_and_reassemble_roundtrips_within_one_frame(
    media: FFmpeg, tmp_path: Path
) -> None:
    src = FIXTURES / "shot-02-grove.mp4"
    frames_dir = tmp_path / "frames"
    frames = media.extract_frames(src, frames_dir, fps=2.0)
    assert len(frames) >= 20  # 12 s × 2 fps
    out = tmp_path / "roundtrip.mp4"
    media.reassemble(frames, out, fps=2.0)
    orig = media.probe(src)
    rebuilt = media.probe(out)
    # AC-S2.2 (part 1): duration within ±1 frame at this fps (0.5 s/frame)
    assert abs(orig["duration_s"] - rebuilt["duration_s"]) <= (1 / 2.0) + 0.05
    assert rebuilt["codec"] in ("h264", "avc1", "mpeg4")


def test_loudness_measure_returns_i_lufs(media: FFmpeg) -> None:
    """ebur128 invocation parses a real integrated LUFS value."""
    value = media.loudness_lufs(FIXTURES / "shot-03-clearing.mp4")
    assert -70.0 <= value <= 0.0


def test_split_segments_covers_the_whole_clip_under_the_cap(
    media: FFmpeg, tmp_path: Path
) -> None:
    """Omni's edit task has a real 10s cap (2026-09-09 demo failure).
    Splitting a clip must produce pieces that each land under the cap and,
    reassembled, cover the whole original duration."""
    src = FIXTURES / "shot-02-grove.mp4"
    total = media.probe(src)["duration_s"]
    segments = media.split_segments(src, tmp_path, max_seconds=5.0)
    assert len(segments) >= 2
    covered = 0.0
    for segment in segments:
        info = media.probe(segment)
        assert info["duration_s"] <= 5.05
        covered += info["duration_s"]
    assert abs(covered - total) <= 0.5


def test_concat_videos_reassembles_segments_into_one_clip(
    media: FFmpeg, tmp_path: Path
) -> None:
    src = FIXTURES / "shot-02-grove.mp4"
    total = media.probe(src)["duration_s"]
    segments = media.split_segments(src, tmp_path, max_seconds=5.0)
    out = tmp_path / "reassembled.mp4"
    media.concat_videos(segments, out)
    rebuilt = media.probe(out)
    assert abs(rebuilt["duration_s"] - total) <= 0.5
    assert rebuilt["codec"] in ("h264", "avc1", "mpeg4")


def test_concat_videos_single_segment_is_a_passthrough(
    media: FFmpeg, tmp_path: Path
) -> None:
    src = FIXTURES / "shot-01-meadow.mp4"
    out = tmp_path / "single.mp4"
    media.concat_videos([src], out)
    assert out.read_bytes() == src.read_bytes()
