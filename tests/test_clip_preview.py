"""Clip preview extracts real frames and audio — inspect must look, not guess."""

from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.core.media import FFmpeg
from backend.supervisor.clip_preview import preview_from_bytes

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
