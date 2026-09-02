"""ffmpeg/ffprobe wrapper (plan A-4). Real binaries only (C-1.1) — pointed at
FFMPEG_BIN/FFPROBE_BIN. No subprocess shortcuts, no fallback engines.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _ebur_number(line: str, prefix: str, suffix: str) -> float | None:
    tail = line.split(prefix)[-1]
    value = tail.split(suffix)[0].strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


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
        streams = list(data.get("streams", []) or [])
        video: dict[str, object] = next(
            (s for s in streams if s.get("codec_type") == "video"), {}
        )
        audio_n = sum(1 for s in streams if s.get("codec_type") == "audio")
        fps_raw = str(video.get("avg_frame_rate", "0/1"))
        num, _, den = fps_raw.partition("/")
        fps = float(num) / float(den) if den not in ("", "0") else 0.0
        fmt = data.get("format", {}) or {}
        return {
            "duration_s": float(fmt.get("duration", 0.0) or 0.0),
            "fps": fps,
            "codec": str(video.get("codec_name", "")),
            "has_audio": audio_n > 0,
            "audio_streams": audio_n,
            "width": _as_int(video.get("width")),
            "height": _as_int(video.get("height")),
            "format": str(fmt.get("format_name", "")),
            "bit_rate": _as_int(fmt.get("bit_rate")),
        }

    def decode_clean(self, path: Path | str) -> bool:
        """True when ffmpeg can decode without packet errors (D-1 corruption)."""
        path = Path(path)
        result = self._run(
            [
                self.ffmpeg_bin,
                "-v",
                "error",
                "-err_detect",
                "explode",
                "-xerror",
                "-i",
                str(path),
                "-f",
                "null",
                "-",
            ]
        )
        if result.returncode != 0:
            return False
        return not result.stderr.strip()

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

    def loudness_report(self, path: Path | str) -> dict[str, float]:
        """Integrated LUFS, LRA, and true-peak from the ebur128 filter."""
        result = self._run(
            [
                self.ffmpeg_bin,
                "-v",
                "info",
                "-i",
                str(path),
                "-filter_complex",
                "ebur128=peak=true:framelog=verbose",
                "-f",
                "null",
                "-",
            ],
            timeout=300,
        )
        stderr = result.stderr.decode("utf-8", "replace")
        parsed: dict[str, float] = {}
        for line in stderr.splitlines():
            if "I:" in line and "LUFS" in line:
                value = _ebur_number(line, "I:", "LUFS")
                if value is not None:
                    parsed["lufs"] = value
            elif "LRA:" in line and "LU" in line:
                value = _ebur_number(line, "LRA:", "LU")
                if value is not None:
                    parsed["lra"] = value
            elif "Peak:" in line and "dBFS" in line:
                value = _ebur_number(line, "Peak:", "dBFS")
                if value is not None:
                    parsed["true_peak_dbtp"] = value
            elif "True peak:" in line:
                unit = "dBTP" if "dBTP" in line else "dBFS"
                value = _ebur_number(line, "True peak:", unit)
                if value is not None:
                    parsed["true_peak_dbtp"] = value
        if "lufs" not in parsed:
            raise RuntimeError(f"ebur128 output not parsed: {stderr[-400:]!r}")
        return parsed

    def loudness_lufs(self, path: Path | str) -> float:
        """Integrated LUFS via the ebur128 filter (A-4 / D-2)."""
        return self.loudness_report(path)["lufs"]

    def band_lufs(self, path: Path | str, highpass_hz: int, lowpass_hz: int) -> float:
        """LUFS of one frequency band — stem-hot heuristic (D-2)."""
        result = self._run(
            [
                self.ffmpeg_bin,
                "-v",
                "info",
                "-i",
                str(path),
                "-filter_complex",
                f"highpass=f={highpass_hz},lowpass=f={lowpass_hz},ebur128",
                "-f",
                "null",
                "-",
            ],
            timeout=300,
        )
        stderr = result.stderr.decode("utf-8", "replace")
        for line in stderr.splitlines():
            if "I:" in line and "LUFS" in line:
                value = _ebur_number(line, "I:", "LUFS")
                if value is not None:
                    return value
        raise RuntimeError(f"band ebur128 not parsed: {stderr[-400:]!r}")


def get_media(settings: object) -> FFmpeg:  # typed via Settings import cycle-safe
    from backend.core.config import Settings

    assert isinstance(settings, Settings)
    return FFmpeg(ffmpeg_bin=settings.ffmpeg_bin, ffprobe_bin=settings.ffprobe_bin)
