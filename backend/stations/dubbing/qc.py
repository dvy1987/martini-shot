"""Dub timing QC — deterministic measurements (E-2, spec S4).

The numbers an agent judges, never the reverse: duration delta against the
original segment and sync-offset estimation via cross-correlation of energy
envelopes. Both operate on real LINEAR16 WAV bytes (Chirp 3 HD TTS output,
24 kHz mono — the adapter's contract).
"""

from __future__ import annotations

import io
import math
import struct
import wave
from typing import Any


def truncate_wav(wav: bytes, ms: int) -> bytes:
    """Deterministic tail truncation — the eval's labeled INPUT mutation
    (C-1.3): a dub cut `ms` short post-synthesis. ms <= 0 is an identity.
    Copies codec params explicitly (never nframes): the input may carry a
    streaming header (nframes=0xFFFFFFFF) from piped ffmpeg output."""
    if ms <= 0:
        return wav
    with wave.open(io.BytesIO(wav), "rb") as w:
        rate, channels, sampwidth = (
            w.getframerate(),
            w.getnchannels(),
            w.getsampwidth(),
        )
        frames = w.readframes(w.getnframes())
    width = sampwidth * channels
    cut = int(rate * ms / 1000) * width
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(frames[:-cut] if cut < len(frames) else b"")
    return out.getvalue()


def truncate_speech_wav(wav: bytes, ms: int) -> bytes:
    """Truncation DEFECT mutation for the eval: the file ends mid-speech —
    the real-world signature of a render cut short. A plain tail cut
    removes only TTS trailing silence, and soft sentence-final words sit
    below any noise floor (both leave the phrase complete — the agent is
    RIGHT to call that clean, verified twice on fr-03). So: windowed RMS
    over 50 ms, speech end = last window above 10% of the loudest window,
    then the FILE is hard-cut `ms` before it — mid-word EOF, no fade."""
    if ms <= 0:
        return wav
    with wave.open(io.BytesIO(wav), "rb") as w:
        rate, channels, sampwidth = (
            w.getframerate(),
            w.getnchannels(),
            w.getsampwidth(),
        )
        raw = w.readframes(w.getnframes())
    width = sampwidth * channels
    n = len(raw) // width
    if n == 0:
        return wav
    samples = struct.unpack(f"<{n}h", raw)
    window = int(rate * 0.05) * channels
    rms: list[float] = []
    for start in range(0, n - window + 1, window):
        chunk = samples[start : start + window]
        rms.append((sum(v * v for v in chunk) / len(chunk)) ** 0.5)
    loud = max(rms) or 1.0
    floor = loud * 0.10
    last_loud = max(i for i, v in enumerate(rms) if v > floor)
    speech_end_samples = (last_loud + 1) * window
    cut_samples = int(rate * ms / 1000) * channels
    cut_point = speech_end_samples - cut_samples
    if cut_point <= 0:
        cut_point = max(0, n - int(rate * ms / 1000) * channels)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(raw[: cut_point * width])
    return out.getvalue()


def source_wav(data: bytes, *, ffmpeg_bin: str = "ffmpeg") -> bytes:
    """Any real source container → the LINEAR16 24 kHz mono WAV the timing
    measurement and the agent contract require (Chirp 3 HD output is 24 kHz
    mono — rates must match for the cross-correlation). WAV input passes
    through unchanged; anything else is decoded by the real ffmpeg and
    fails loud on garbage (C-1.1)."""
    if data[:4] == b"RIFF":
        return data
    import subprocess

    result = subprocess.run(
        [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-map",
            "0:a",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "pipe:1",
        ],
        input=data,
        capture_output=True,
        check=True,
    )
    if not result.stdout:
        raise RuntimeError(
            f"ffmpeg decoded no audio from source: {result.stderr[:200]!r}"
        )
    return result.stdout


def atempo_wav(wav: bytes, tempo: float, *, ffmpeg_bin: str = "ffmpeg") -> bytes:
    """Deterministic waveform time-stretch (ffmpeg atempo) — how a studio
    time-compresses a dub to picture. Scales duration by 1/tempo EXACTLY
    (no TTS re-render noise) while preserving pitch. tempo ∈ [0.5, 2.0]
    (ffmpeg's single-filter range); refuses outside — fail loud."""
    import subprocess

    if not 0.5 <= tempo <= 2.0:
        raise ValueError(f"tempo {tempo} outside ffmpeg atempo range [0.5, 2.0]")
    result = subprocess.run(
        [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-map",
            "0:a",
            "-filter:a",
            f"atempo={tempo:.6f}",
            "-f",
            "wav",
            "pipe:1",
        ],
        input=wav,
        capture_output=True,
        check=True,
    )
    if not result.stdout:
        raise RuntimeError(f"ffmpeg atempo produced no audio: {result.stderr[:200]!r}")
    return result.stdout


def _read_wav(wav: bytes) -> tuple[int, list[float]]:
    """(sample_rate, samples) from LINEAR16 mono WAV bytes; fail loud on
    anything else — a mis-decoded dub must never look like silence. Reads
    to EOF rather than trusting nframes: ffmpeg's piped WAV output writes a
    streaming header (0xFFFFFFFF frames)."""
    with wave.open(io.BytesIO(wav), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"expected 16-bit WAV, got sampwidth={w.getsampwidth()}")
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())
    n = len(raw) // 2
    samples = list(struct.unpack(f"<{n}h", raw)) if n else []
    return rate, samples


def duration_delta_ms(original_wav: bytes, dubbed_wav: bytes) -> int:
    """Dubbed duration minus original, in milliseconds (negative = the dub
    is SHORTER — the truncation signature, spec S4)."""
    rate_o, samples_o = _read_wav(original_wav)
    rate_d, samples_d = _read_wav(dubbed_wav)
    if rate_o != rate_d:
        raise ValueError(f"sample rate mismatch: {rate_o} vs {rate_d}")
    return int((len(samples_d) - len(samples_o)) / rate_o * 1000)


def energy_envelope(wav: bytes, *, window_ms: int = 20) -> list[float]:
    """RMS energy per window — the signal cross-correlation aligns."""
    rate, samples = _read_wav(wav)
    window = max(1, int(rate * window_ms / 1000))
    env: list[float] = []
    for start in range(0, len(samples), window):
        chunk = samples[start : start + window]
        if not chunk:
            break
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
        env.append(rms)
    return env


def sync_offset_ms(
    original_wav: bytes, dubbed_wav: bytes, *, window_ms: int = 20
) -> float:
    """Estimate how far the dub is shifted vs the original via normalized
    cross-correlation of energy envelopes; returns the offset in ms
    (positive = the dub starts late). Window resolution bounds accuracy —
    with 20 ms windows the answer is exact to ±1 window plus interpolation."""
    rate, _ = _read_wav(original_wav)
    env_o = energy_envelope(original_wav, window_ms=window_ms)
    env_d = energy_envelope(dubbed_wav, window_ms=window_ms)
    if not env_o or not env_d:
        return 0.0

    def _norm(v: list[float]) -> list[float]:
        mean = sum(v) / len(v)
        centered = [x - mean for x in v]
        norm = math.sqrt(sum(x * x for x in centered)) or 1.0
        return [x / norm for x in centered]

    o = _norm(env_o)
    d = _norm(env_d)
    if not o or not d:
        return 0.0
    best_lag, best_score = 0, -2.0
    max_lag = max(len(o), len(d))

    # score(s): NORMALIZED cross-correlation of o[t] with d[t + s] — divided
    # by the SLICE norms so lags with tiny overlap can't win on noise
    # (s > 0 means the dub's content sits s windows LATE in its file).
    def _slice_norm(v: list[float]) -> float:
        return math.sqrt(sum(x * x for x in v)) or 1.0

    # A single-window overlap normalizes to ±1 — degenerate. Demand real
    # overlap, and evaluate lags nearest zero first so ties keep the
    # smallest shift.
    min_overlap = max(4, int(0.5 * min(len(o), len(d))))
    for s in sorted(range(-max_lag, max_lag + 1), key=lambda x: (abs(x), x)):
        if s >= 0:
            n = min(len(o), len(d) - s)
            if n < min_overlap:
                continue
            a, b = o[:n], d[s : s + n]
        else:
            n = min(len(o) + s, len(d))
            if n < min_overlap:
                continue
            a, b = o[-s : -s + n], d[:n]
        score = sum(x * y for x, y in zip(a, b, strict=False)) / (
            _slice_norm(a) * _slice_norm(b)
        )
        if score > best_score:
            best_score, best_lag = score, s
    return best_lag * window_ms


def timing_verdict(*, delta_ms: int, tolerance_ms: int) -> str:
    """Deterministic pre-agent verdict (spec S4: ≤45 ms tolerance target).
    ADVISORY input to the Dub QC Agent — the agent may override it with a
    stated reason (A10), and its override is logged as such."""
    return "pass" if abs(delta_ms) <= tolerance_ms else "flagged"


def measure_timing(
    original_wav: bytes, dubbed_wav: bytes, *, tolerance_ms: int
) -> dict[str, Any]:
    """One deterministic measurement bundle for the Dub QC Agent — includes
    the raw durations so the station can time-fit the dub (prosody rate)
    before the agent judges."""
    rate_o, samples_o = _read_wav(original_wav)
    rate_d, samples_d = _read_wav(dubbed_wav)
    if rate_o != rate_d:
        raise ValueError(f"sample rate mismatch: {rate_o} vs {rate_d}")
    source_duration_ms = int(len(samples_o) / rate_o * 1000)
    dub_duration_ms = int(len(samples_d) / rate_d * 1000)
    delta = dub_duration_ms - source_duration_ms
    return {
        "source_duration_ms": source_duration_ms,
        "dub_duration_ms": dub_duration_ms,
        "duration_delta_ms": delta,
        "sync_offset_ms": sync_offset_ms(original_wav, dubbed_wav),
        "tolerance_ms": tolerance_ms,
        "verdict": timing_verdict(delta_ms=delta, tolerance_ms=tolerance_ms),
    }
