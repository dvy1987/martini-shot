"""ffmpeg/ffprobe wrapper (plan A-4). Real binaries only (C-1.1) — pointed at
FFMPEG_BIN/FFPROBE_BIN. No subprocess shortcuts, no fallback engines.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class FFmpeg:
    def __init__(self, ffmpeg_bin: str, ffprobe_bin: str) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def _run(
        self, args: list[str], timeout: int = 120
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(args, capture_output=True, timeout=timeout, check=False)

    def probe(self, path: Path | str) -> dict[str, object]:
        path = Path(path)
        result = self._run(
            [
                self.ffprobe_bin,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffprobe failed on {path.name}: {result.stderr[:400]!r}"
            )
        data = json.loads(result.stdout.decode("utf-8", "replace"))
        video: dict[str, object] = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"), {}
        )
        fps_raw = str(video.get("avg_frame_rate", "0/1"))
        num, _, den = fps_raw.partition("/")
        fps = float(num) / float(den) if den not in ("", "0") else 0.0
        return {
            "duration_s": float(data.get("format", {}).get("duration", 0.0)),
            "fps": fps,
            "codec": str(video.get("codec_name", "")),
        }

    def extract_frames(
        self, path: Path | str, out_dir: Path | str, fps: float
    ) -> list[Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pattern = out_dir / "frame-%05d.png"
        result = self._run(
            [
                self.ffmpeg_bin,
                "-v",
                "error",
                "-i",
                str(path),
                "-vf",
                f"fps={fps}",
                str(pattern),
            ],
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"frame extraction failed: {result.stderr[:400]!r}")
        return sorted(out_dir.glob("frame-*.png"))

    def reassemble(self, frames: list[Path], out_path: Path | str, fps: float) -> None:
        if not frames:
            raise ValueError("no frames to reassemble")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        first = frames[0]
        result = self._run(
            [
                self.ffmpeg_bin,
                "-v",
                "error",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(first.parent / "frame-%05d.png"),
                "-pix_fmt",
                "yuv420p",
                str(out_path),
            ],
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"reassembly failed: {result.stderr[:400]!r}")

    def loudness_lufs(self, path: Path | str) -> float:
        """Integrated LUFS via the ebur128 filter (real measurement, A-4 base
        for the D-2 loudness engine)."""
        result = self._run(
            [
                self.ffmpeg_bin,
                "-v",
                "info",
                "-i",
                str(path),
                "-filter_complex",
                "ebur128=framelog=verbose",
                "-f",
                "null",
                "-",
            ],
            timeout=300,
        )
        stderr = result.stderr.decode("utf-8", "replace")
        for line in stderr.splitlines():
            if "I:" in line and "LUFS" in line:
                tail = line.split("I:")[-1].strip()
                value = tail.split("LUFS")[0].strip()
                try:
                    return float(value)
                except ValueError:
                    continue
        raise RuntimeError(f"ebur128 output not parsed: {stderr[-400:]!r}")


def get_media(settings: object) -> FFmpeg:  # typed via Settings import cycle-safe
    from backend.core.config import Settings

    assert isinstance(settings, Settings)
    return FFmpeg(ffmpeg_bin=settings.ffmpeg_bin, ffprobe_bin=settings.ffprobe_bin)
