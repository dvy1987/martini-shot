"""Labeled INPUT clips for the finishing inspect eval (C-1.3).

Built at eval time from original Omni tapes already on GCS, plus a real
Chirp line when the deficit is hearability. Not vignettes. Not gradients.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.core.generative import tts_synthesize
from backend.core.media import FFmpeg

log = logging.getLogger("pc.eval.finish_inspect")

KITCHEN = "gs://martini-shot-media/original-probes/20260907T083210Z-kitchen-cooks.mp4"
TABLE = "gs://martini-shot-media/original-probes/20260907T080221Z-table-cup.mp4"
CAFE_SIGN = "gs://martini-shot-media/original-probes/20260907T080221Z-cafe-sign.mp4"

DIALOGUE = "I'll take the usual, thanks. Same as yesterday."


def _ffmpeg(media: FFmpeg, args: list[str], *, timeout: int = 120) -> None:
    result = media._run(
        [media.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", *args],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:400]!r}")


def _download(settings: Any, uri: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    from backend.core.gcs import get_gcs

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(get_gcs(settings).download_bytes(uri))
    return dest


def _mux_line(
    media: FFmpeg,
    *,
    picture: Path,
    wav: Path,
    dest: Path,
    volume_db: float,
) -> None:
    dur = float(media.probe(picture).get("duration_s") or 8.0)
    _ffmpeg(
        media,
        [
            "-i",
            str(picture),
            "-i",
            str(wav),
            "-filter_complex",
            f"[1:a]volume={volume_db}dB,apad=pad_dur={dur}[a]",
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            f"{dur:.2f}",
            str(dest),
        ],
    )


def ensure_inspect_clips(settings: Any, media: FFmpeg, work: Path) -> dict[str, Path]:
    """Real clips carrying the deficit under test. Cached in `work`."""
    work.mkdir(parents=True, exist_ok=True)
    kitchen = _download(settings, KITCHEN, work / "src-kitchen.mp4")
    table = _download(settings, TABLE, work / "src-table.mp4")
    cafe = _download(settings, CAFE_SIGN, work / "src-cafe.mp4")

    wav_path = work / "line.wav"
    if not wav_path.exists():
        render = tts_synthesize(
            settings, ssml=f"<speak>{DIALOGUE}</speak>", language_code="en-US"
        )
        wav_path.write_bytes(bytes(render["audio_bytes"]))

    quiet = work / "quiet_dialogue.mp4"
    if not quiet.exists():
        _mux_line(media, picture=table, wav=wav_path, dest=quiet, volume_db=-24.0)

    clean = work / "clean_dialogue.mp4"
    if not clean.exists():
        _mux_line(media, picture=table, wav=wav_path, dest=clean, volume_db=0.0)

    dark = work / "dark_faces.mp4"
    if not dark.exists():
        _ffmpeg(
            media,
            [
                "-i",
                str(table),
                "-vf",
                "eq=brightness=-0.45:gamma=0.65:saturation=0.7",
                "-c:a",
                "aac",
                str(dark),
            ],
        )

    cut = work / "dies_mid_thought.mp4"
    if not cut.exists():
        _ffmpeg(media, ["-i", str(kitchen), "-t", "2.2", str(cut)])

    locked = work / "locked_off.mp4"
    if not locked.exists():
        locked.write_bytes(table.read_bytes())

    closed = work / "signage_closed.mp4"
    if not closed.exists():
        _ffmpeg(
            media,
            [
                "-i",
                str(cafe),
                "-vf",
                (
                    "drawtext=fontfile=C\\\\:/Windows/Fonts/arial.ttf:text=CLOSED:"
                    "fontsize=72:fontcolor=white:borderw=4:bordercolor=black:"
                    "x=(w-text_w)/2:y=h*0.22"
                ),
                "-c:a",
                "aac",
                str(closed),
            ],
        )

    return {
        "quiet_dialogue": quiet,
        "clean_dialogue": clean,
        "dark_faces": dark,
        "dies_mid_thought": cut,
        "locked_off": locked,
        "signage_closed": closed,
        "spend_ok": locked,
    }
