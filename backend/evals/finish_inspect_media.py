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
FLORIST = "gs://martini-shot-media/original-probes/20260907T081720Z-florist-tulips.mp4"
CHALKBOARD = "gs://martini-shot-media/original-probes/chalkboard-opnn.mp4"

DIALOGUE = "I'll take the usual, thanks. Same as yesterday."

INSPECT_CLIP_KEYS = frozenset(
    {
        "quiet_dialogue",
        "clean_dialogue",
        "dark_faces",
        "dies_mid_thought",
        "extra_air",
        "complete_shot",
        "locked_off",
        "signage_closed",
        "table_cup",
        "chalkboard_opnn",
        "clean_picture",
        "spend_ok",
    }
)


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


def _copy_clip(src: Path, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    dest.write_bytes(src.read_bytes())
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


def _want(needed: set[str] | None, *names: str) -> bool:
    if needed is None:
        return True
    return bool(needed.intersection(names))


def ensure_inspect_clips(
    settings: Any,
    media: FFmpeg,
    work: Path,
    *,
    needed: set[str] | None = None,
) -> dict[str, Path]:
    """Real clips carrying the deficit under test. Cached in `work`."""
    if needed is not None:
        unknown = needed - INSPECT_CLIP_KEYS
        if unknown:
            raise RuntimeError(f"unknown inspect clips: {sorted(unknown)}")
    work.mkdir(parents=True, exist_ok=True)
    kitchen = table = cafe = florist = chalkboard = None
    if _want(needed, "dies_mid_thought"):
        kitchen = _download(settings, KITCHEN, work / "src-kitchen.mp4")
    if _want(
        needed,
        "quiet_dialogue",
        "clean_dialogue",
        "dark_faces",
        "locked_off",
        "complete_shot",
        "table_cup",
        "spend_ok",
    ):
        table = _download(settings, TABLE, work / "src-table.mp4")
    if _want(needed, "signage_closed"):
        cafe = _download(settings, CAFE_SIGN, work / "src-cafe.mp4")
    if _want(needed, "clean_picture", "extra_air"):
        florist = _download(settings, FLORIST, work / "src-florist.mp4")
    if _want(needed, "chalkboard_opnn"):
        chalkboard = _download(settings, CHALKBOARD, work / "src-chalkboard.mp4")

    clips: dict[str, Path] = {}

    if _want(needed, "quiet_dialogue", "clean_dialogue"):
        assert table is not None
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
        clips["quiet_dialogue"] = quiet
        clips["clean_dialogue"] = clean

    if _want(needed, "dark_faces"):
        assert table is not None
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
        clips["dark_faces"] = dark

    if _want(needed, "dies_mid_thought"):
        assert kitchen is not None
        cut = work / "dies_mid_thought.mp4"
        if not cut.exists():
            _ffmpeg(media, ["-i", str(kitchen), "-t", "2.2", str(cut)])
        clips["dies_mid_thought"] = cut

    if _want(needed, "extra_air"):
        assert florist is not None
        dest = work / "extra_air.mp4"
        dest.write_bytes(florist.read_bytes())
        clips["extra_air"] = dest

    if _want(needed, "complete_shot"):
        assert table is not None
        clips["complete_shot"] = _copy_clip(table, work / "complete_shot.mp4")

    if _want(needed, "locked_off", "spend_ok"):
        assert table is not None
        locked = work / "locked_off.mp4"
        if not locked.exists():
            locked.write_bytes(table.read_bytes())
        clips["locked_off"] = locked
        clips["spend_ok"] = locked

    if _want(needed, "signage_closed"):
        assert cafe is not None
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
        clips["signage_closed"] = closed

    if _want(needed, "table_cup"):
        assert table is not None
        clips["table_cup"] = _copy_clip(table, work / "table_cup.mp4")

    if _want(needed, "chalkboard_opnn"):
        assert chalkboard is not None
        clips["chalkboard_opnn"] = _copy_clip(chalkboard, work / "chalkboard_opnn.mp4")

    if _want(needed, "clean_picture"):
        assert florist is not None
        clips["clean_picture"] = _copy_clip(florist, work / "clean_picture.mp4")

    return clips
