"""D-1 RED: ffprobe + corruption + missing-audio classification (AC-S1.1/.2)."""

from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.core.media import FFmpeg
from backend.stations.ingest.classify import (
    REASON_DECODE,
    REASON_EMPTY,
    REASON_MISSING_AUDIO,
    classify_payload,
)

ROOT = Path(__file__).resolve().parents[1]
SLATE = ROOT / "fixtures" / "g1" / "slate.mp4"
SPIKE = ROOT / "fixtures" / "spike" / "shot-01-meadow.mp4"


@pytest.fixture()
def media() -> FFmpeg:
    settings = get_settings()
    assert settings.ffmpeg_bin and settings.ffprobe_bin
    return FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)


def test_healthy_slate_passes(media: FFmpeg) -> None:
    verdict, reason, probe = classify_payload(SLATE.read_bytes(), media)
    assert verdict == "pass"
    assert reason is None
    assert probe["duration_s"] > 0
    assert probe["has_audio"] is True


def test_bitflip_at_80_percent_quarantines(media: FFmpeg) -> None:
    payload = bytearray(SLATE.read_bytes())
    payload[int(len(payload) * 0.8)] ^= 0xFF
    verdict, reason, _probe = classify_payload(bytes(payload), media)
    assert verdict == "quarantined"
    assert reason in {REASON_DECODE, "corrupt_probe"}


def test_empty_payload_quarantines(media: FFmpeg) -> None:
    verdict, reason, _probe = classify_payload(b"", media)
    assert verdict == "quarantined"
    assert reason == REASON_EMPTY


def test_missing_audio_is_flagged(media: FFmpeg, tmp_path: Path) -> None:
    silent = tmp_path / "silent.mp4"
    settings = get_settings()
    import subprocess

    built = subprocess.run(
        [
            settings.ffmpeg_bin,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=0.5",
            "-an",
            str(silent),
        ],
        capture_output=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    verdict, reason, probe = classify_payload(silent.read_bytes(), media)
    assert probe["has_audio"] is False
    assert verdict == "quarantined"
    assert reason == REASON_MISSING_AUDIO


DEMO_CLIP01 = Path(
    r"C:\Users\reall\Building_Apps\Misc\martini-shot\demo-clip-bank\test-clips\test-clip01.mp4"
)


def test_phone_export_with_muxer_dts_warning_is_not_quarantined(media: FFmpeg) -> None:
    """Owner demo clip01 probes and decodes; null-muxer DTS chatter is not corruption."""
    if not DEMO_CLIP01.exists():
        pytest.skip("owner demo clip bank not on disk")
    payload = DEMO_CLIP01.read_bytes()
    assert media.decode_clean(DEMO_CLIP01) is True
    verdict, reason, probe = classify_payload(payload, media)
    assert probe["duration_s"] > 0
    assert probe["has_audio"] is True
    assert verdict == "pass"
    assert reason is None


def test_probe_reports_audio_on_spike(media: FFmpeg) -> None:
    if not SPIKE.exists():
        pytest.skip("spike fixture not on disk")
    info = media.probe(SPIKE)
    assert info["has_audio"] is True
    assert info["codec"] in ("h264", "avc1")
