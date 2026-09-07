"""Download a source clip and extract a short look (frames + wav).

Inspect agents must see/hear the media. A URI in the prompt is not a look.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger("pc.finishing.preview")

PreviewParts = tuple[list[tuple[bytes, str]], tuple[bytes, str] | None, str]

AUDIO_STATIONS = frozenset({"loudness", "dub", "ingest", "delivery"})
VISUAL_STATIONS = frozenset(
    {
        "ingest",
        "pickups",
        "extend",
        "corrections",
        "relight",
        "coverage",
        "camera_language",
        "delivery",
    }
)


def preview_from_bytes(media: Any, payload: bytes) -> PreviewParts:
    """Extract up to 3 frames and a 16 kHz wav from already-downloaded bytes."""
    images: list[tuple[bytes, str]] = []
    audio: tuple[bytes, str] | None = None
    err = ""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "clip.mp4"
        src.write_bytes(payload)
        try:
            probe = media.probe(src)
            duration = float(probe.get("duration_s") or 1.0)
            fps = min(1.0, 3.0 / max(duration, 0.5))
            frames = media.extract_frames(src, Path(tmp) / "frames", fps=fps)[:3]
            images = [(path.read_bytes(), "image/png") for path in frames]
        except Exception as exc:
            log.exception("frame extract failed")
            err = str(exc)
        try:
            wav = media.extract_wav(src)
            audio = (wav, "audio/wav")
        except Exception as exc:
            log.exception("wav extract failed")
            if not err:
                err = str(exc)
    return images, audio, err


def load_clip_preview(settings: Any, clip_uri: str) -> PreviewParts:
    if not clip_uri:
        return [], None, "missing clip_uri"
    try:
        from backend.core.gcs import get_gcs
        from backend.core.media import get_media

        payload = get_gcs(settings).download_bytes(clip_uri)
        return preview_from_bytes(get_media(settings), payload)
    except Exception as exc:
        log.exception("clip download failed uri=%s", clip_uri)
        return [], None, str(exc)


class ClipPreviewCache:
    """One download/extract per clip for the whole station roster."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._by_uri: dict[str, PreviewParts] = {}

    def _load(self, clip_uri: str) -> PreviewParts:
        if clip_uri not in self._by_uri:
            self._by_uri[clip_uri] = load_clip_preview(self._settings, clip_uri)
        return self._by_uri[clip_uri]

    def parts_for(
        self, station: str, clip_uri: str
    ) -> tuple[list[tuple[bytes, str]] | None, tuple[bytes, str] | None, str]:
        images, audio, err = self._load(clip_uri)
        if station == "spend":
            return None, None, ""
        if station not in AUDIO_STATIONS:
            audio = None
        if station not in VISUAL_STATIONS:
            images = []
        return (images or None), audio, err
