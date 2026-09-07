"""ffmpeg/ffprobe wrapper (plan A-4). Real binaries only (C-1.1) — pointed at
FFMPEG_BIN/FFPROBE_BIN. No subprocess shortcuts, no fallback engines.
"""

from __future__ import annotations

import json
import math
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

    def extract_wav(self, path: Path | str) -> bytes:
        """Decode the soundtrack to LINEAR16 WAV for a listen-capable agent."""
        path = Path(path)
        out = path.with_suffix(".watch.wav")
        result = self._run(
            [
                self.ffmpeg_bin,
                "-v",
                "error",
                "-y",
                "-i",
                str(path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(out),
            ],
            timeout=120,
        )
        if result.returncode != 0 or not out.exists():
            raise RuntimeError(f"audio extract failed: {result.stderr[:400]!r}")
        try:
            return out.read_bytes()
        finally:
            out.unlink(missing_ok=True)

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

    def lift_speech_over_room(
        self,
        src: Path | str,
        dst: Path | str,
        *,
        voice_db: float = 6.0,
        room_db: float = -4.0,
    ) -> None:
        """Split voice band from the room and lift the line relative to ambience.

        Voice ≈ 300–3400 Hz. Room is everything else. Real ffmpeg filters,
        not a fake stem. Then re-measure.
        """
        src_path = Path(src)
        dst_path = Path(dst)
        filt = (
            f"[0:a]asplit=3[v][lo][hi];"
            f"[v]highpass=f=300,lowpass=f=3400,volume={voice_db}dB[voice];"
            f"[lo]lowpass=f=300,volume={room_db}dB[roomlo];"
            f"[hi]highpass=f=3400,volume={room_db}dB[roomhi];"
            f"[voice][roomlo][roomhi]amix=inputs=3:normalize=0[aout]"
        )
        probe = self.probe(src_path)
        args = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-i",
            str(src_path),
            "-filter_complex",
            filt,
            "-map",
            "[aout]",
        ]
        if int(probe.get("width") or 0) > 0:
            args.extend(["-map", "0:v:0", "-c:v", "copy"])
        args.append(str(dst_path))
        result = self._run(args, timeout=300)
        if result.returncode != 0 or not dst_path.exists():
            raise RuntimeError(
                "speech lift failed: "
                f"{result.stderr.decode('utf-8', 'replace')[-400:]!r}"
            )

    def apply_loudnorm(
        self,
        src: Path | str,
        dst: Path | str,
        *,
        integrated_lufs: float,
        true_peak_dbtp: float = -1.5,
    ) -> None:
        """Two-pass ffmpeg loudnorm toward an integrated target (then re-measure)."""
        src_path = Path(src)
        dst_path = Path(dst)
        filt = (
            f"loudnorm=I={integrated_lufs}:TP={true_peak_dbtp}:LRA=11:print_format=json"
        )
        measure = self._run(
            [
                self.ffmpeg_bin,
                "-hide_banner",
                "-i",
                str(src_path),
                "-af",
                filt,
                "-f",
                "null",
                "-",
            ],
            timeout=300,
        )
        measured = _loudnorm_measured(measure.stderr.decode("utf-8", "replace"))
        if not _loudnorm_is_mixable(measured):
            raise RuntimeError(
                "loudnorm cannot mix silent or unmeterable audio "
                f"(input_i={measured.get('input_i')!r}, "
                f"target_offset={measured.get('target_offset')!r})"
            )
        apply_filt = (
            f"loudnorm=I={integrated_lufs}:TP={true_peak_dbtp}:LRA=11:"
            f"measured_I={measured['input_i']}:"
            f"measured_LRA={measured['input_lra']}:"
            f"measured_TP={measured['input_tp']}:"
            f"measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}:"
            "linear=true"
        )
        probe = self.probe(src_path)
        args = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-i",
            str(src_path),
            "-af",
            apply_filt,
        ]
        if probe.get("codec"):
            args.extend(["-c:v", "copy"])
        args.append(str(dst_path))
        result = self._run(args, timeout=300)
        if result.returncode != 0 or not dst_path.exists():
            raise RuntimeError(
                f"loudnorm apply failed: {result.stderr.decode('utf-8', 'replace')[-400:]!r}"
            )


def _loudnorm_is_mixable(measured: dict[str, str]) -> bool:
    for key in ("input_i", "target_offset"):
        try:
            if not math.isfinite(float(measured[key])):
                return False
        except (TypeError, ValueError, KeyError):
            return False
    return True


def _loudnorm_measured(stderr: str) -> dict[str, str]:
    """Parse the JSON blob ffmpeg loudnorm prints on the measure pass."""
    start, end = stderr.rfind("{"), stderr.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"loudnorm json missing: {stderr[-400:]!r}")
    payload = json.loads(stderr[start : end + 1])
    required = (
        "input_i",
        "input_lra",
        "input_tp",
        "input_thresh",
        "target_offset",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise RuntimeError(f"loudnorm json missing keys {missing}: {payload!r}")
    return {key: str(payload[key]) for key in required}


def get_media(settings: object) -> FFmpeg:  # typed via Settings import cycle-safe
    from backend.core.config import Settings

    assert isinstance(settings, Settings)
    return FFmpeg(ffmpeg_bin=settings.ffmpeg_bin, ffprobe_bin=settings.ffprobe_bin)
