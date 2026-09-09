"""Clip preview extracts real frames and audio — inspect must look, not guess.

ADR-0005: temporal judges (camera_language, pickups, extend) additionally get
the REAL clip as an inline video part — motion is invisible in stills.
"""

from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.core.media import FFmpeg
from backend.supervisor.clip_preview import preview_from_bytes, video_look

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "spike"


@pytest.fixture()
def media() -> FFmpeg:
    settings = get_settings()
    assert settings.ffmpeg_bin and settings.ffprobe_bin, (
        "FFMPEG_BIN/FFPROBE_BIN must be configured (real binaries, no shims)"
    )
    return FFmpeg(ffmpeg_bin=settings.ffmpeg_bin, ffprobe_bin=settings.ffprobe_bin)


def test_preview_from_bytes_returns_frames_and_wav(media: FFmpeg) -> None:
    payload = (FIXTURES / "shot-01-meadow.mp4").read_bytes()
    images, audio, _err = preview_from_bytes(media, payload)
    assert len(images) >= 1
    assert images[0][1] == "image/png"
    assert len(images[0][0]) > 100
    assert audio is not None
    assert audio[1] == "audio/wav"
    assert audio[0][:4] == b"RIFF"


def test_video_look_transcodes_real_clip_to_360p_mp4(
    media: FFmpeg, tmp_path: Path
) -> None:
    """ADR-0005: the temporal judges' video look must be REAL mp4 bytes,
    downscaled so the inline part stays small."""
    payload = (FIXTURES / "shot-01-meadow.mp4").read_bytes()
    data, mime = video_look(media, payload)
    assert mime == "video/mp4"
    assert data[:4] != b"RIFF"
    src = tmp_path / "look.mp4"
    src.write_bytes(data)
    probe = media.probe(src)
    assert int(probe["height"] or 0) <= 360
    assert float(probe["duration_s"] or 0.0) > 0.0
