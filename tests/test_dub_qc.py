"""E-2 dub timing QC — deterministic measurements (TDD, RED-first).

Duration delta and sync-offset estimation via energy-envelope cross-
correlation (spec S4). Tests synthesize small deterministic WAVs in-memory
(labeled synthetic input, C-1.3) — the real TTS audio is exercised by the
live eval (`scripts/dub_qc_eval.py`).
"""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest

from backend.stations.dubbing.qc import (
    duration_delta_ms,
    energy_envelope,
    measure_timing,
    sync_offset_ms,
    timing_verdict,
    truncate_wav,
)

SAMPLE_RATE = 24000


def _tone_wav(seconds: float, freq: float = 440.0, phase: float = 0.0) -> bytes:
    """Deterministic amplitude-modulated sine WAV (labeled synthetic input
    for tests, C-1.3). The envelope combines incommensurate rates + a decay
    ramp — structured like speech and NON-periodic, so the correlator has a
    unique lock (a pure periodic envelope would self-correlate at every
    period, which no real dub does)."""
    buf = io.BytesIO()
    n = int(SAMPLE_RATE * seconds)
    frames = b"".join(
        struct.pack(
            "<h",
            int(
                12000
                * (
                    0.45
                    + 0.25 * math.sin(2 * math.pi * 3.1 * i / SAMPLE_RATE)
                    + 0.20 * math.sin(2 * math.pi * 7.3 * i / SAMPLE_RATE + 1.3)
                )
                * (1.0 - 0.2 * i / n)
                * math.sin(2 * math.pi * freq * i / SAMPLE_RATE + phase)
            ),
        )
        for i in range(n)
    )
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(frames)
    return buf.getvalue()


def _pad_wav(wav: bytes, pad_ms: int, *, at_start: bool = False) -> bytes:
    """Pad a WAV with silence (start or end) by exactly pad_ms."""
    with wave.open(io.BytesIO(wav), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    pad = b"\x00\x00" * int(SAMPLE_RATE * pad_ms / 1000)
    new_frames = (pad + frames) if at_start else (frames + pad)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(new_frames)
    return out.getvalue()


def test_duration_delta_zero_for_identical_audio():
    wav = _tone_wav(1.0)
    assert duration_delta_ms(wav, wav) == 0


def test_duration_delta_detects_tail_padding():
    original = _tone_wav(1.0)
    dubbed = _pad_wav(original, pad_ms=250)
    assert duration_delta_ms(original, dubbed) == pytest.approx(250, abs=2)


def test_duration_delta_negative_for_truncated_dub():
    original = _tone_wav(1.0)
    with wave.open(io.BytesIO(original), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    cut = io.BytesIO()
    with wave.open(cut, "wb") as w:
        w.setparams(params)
        w.writeframes(frames[: len(frames) // 2])
    assert duration_delta_ms(original, cut.getvalue()) == pytest.approx(-500, abs=2)


def test_energy_envelope_size_and_nonnegativity():
    env = energy_envelope(_tone_wav(1.0), window_ms=50)
    assert len(env) == 20  # 1000ms / 50ms
    assert all(v >= 0.0 for v in env)


def test_sync_offset_finds_shifted_dub():
    original = _tone_wav(1.0)
    dubbed = _pad_wav(_tone_wav(1.0), pad_ms=150, at_start=True)
    offset = sync_offset_ms(original, dubbed)
    assert offset == pytest.approx(150, abs=25)


def test_sync_offset_zero_for_aligned_audio():
    wav = _tone_wav(1.0)
    assert sync_offset_ms(wav, wav) == pytest.approx(0, abs=10)


def test_timing_verdict_table():
    assert timing_verdict(delta_ms=40, tolerance_ms=45) == "pass"
    assert timing_verdict(delta_ms=-44, tolerance_ms=45) == "pass"
    assert timing_verdict(delta_ms=46, tolerance_ms=45) == "flagged"
    assert timing_verdict(delta_ms=-600, tolerance_ms=45) == "flagged"


def test_truncate_wav_cuts_tail_and_measurement_sees_it():
    original = _tone_wav(1.0)
    cut = truncate_wav(original, 600)
    measurements = measure_timing(original, cut, tolerance_ms=45)
    assert measurements["duration_delta_ms"] == pytest.approx(-600, abs=40)
    assert measurements["verdict"] == "flagged"
    # Zero truncation is an identity (defensive, C-1.1).
    assert truncate_wav(original, 0) == original


def test_atempo_stretch_scales_duration_exactly():
    """ffmpeg atempo is the studio's time-compression: scales duration by
    1/tempo without re-rendering — exact, no TTS noise (C-1.1 real work)."""
    from backend.stations.dubbing.qc import atempo_wav

    original = _tone_wav(1.0)
    stretched = atempo_wav(original, 0.8)  # slower → 1.25x longer
    measurements = measure_timing(original, stretched, tolerance_ms=45)
    assert measurements["dub_duration_ms"] == pytest.approx(1250, abs=25)
    # Speed-up direction: a 1.3x-too-long dub fits at tempo 1.3.
    long_dub = _tone_wav(1.3)
    fitted = atempo_wav(long_dub, 1.3)
    m = measure_timing(original, fitted, tolerance_ms=45)
    assert abs(m["duration_delta_ms"]) <= 45


def test_atempo_wav_rejects_out_of_band_tempo():
    from backend.stations.dubbing.qc import atempo_wav

    with pytest.raises(ValueError, match="tempo"):
        atempo_wav(_tone_wav(1.0), 3.0)


def test_truncate_speech_cuts_into_words_not_trailing_silence():
    """A plain tail cut on TTS output often removes only trailing silence —
    inaudible, and the agent is RIGHT to call it clean. The eval's mutation
    must be a real truncation defect: the FILE ends mid-speech."""
    from backend.stations.dubbing.qc import energy_envelope, truncate_speech_wav

    speech = _tone_wav(0.8)  # audible content
    with_silence = _pad_wav(speech, pad_ms=400)  # 400ms trailing silence
    cut = truncate_speech_wav(with_silence, 300)
    m = measure_timing(with_silence, cut, tolerance_ms=45)
    assert m["duration_delta_ms"] <= -300
    # The file ends LOUD — mid-word EOF, not a fade into silence.
    env = energy_envelope(cut, window_ms=50)
    assert env[-1] > 0.1 * max(env)


def test_truncate_speech_ignores_faint_tts_tail_noise():
    """TTS tails carry low-level breath/noise; a naive amplitude floor counts
    it as speech and the cut lands in the quiet tail (the agent rightly
    judged fr-03 clean twice). The floor must be relative to the LOUDEST
    50ms window, and the cut must be a hard EOF mid-loud-speech."""
    import struct
    import wave

    from backend.stations.dubbing.qc import energy_envelope, truncate_speech_wav

    speech = _tone_wav(0.8)  # loud content
    n_noise = int(SAMPLE_RATE * 0.4)
    noise_frames = struct.pack(f"<{n_noise}h", *([300] * n_noise))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(_raw_frames(speech) + noise_frames)
    combined = buf.getvalue()
    cut = truncate_speech_wav(combined, 300)
    m = measure_timing(combined, cut, tolerance_ms=45)
    # 500ms of loud speech survive (0.8s loud - 0.3s cut); the faint tail is
    # GONE — the file ends mid-word instead of trailing off.
    assert m["dub_duration_ms"] == pytest.approx(500, abs=40)
    env = energy_envelope(cut, window_ms=50)
    assert env[-1] > 0.1 * max(env)


def _raw_frames(wav: bytes) -> bytes:
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.readframes(w.getnframes())


def test_truncate_works_on_streaming_header_wav():
    """ffmpeg's piped WAV writes a streaming header (nframes=0xFFFFFFFF);
    the eval truncates atempo output, so truncate must not propagate that
    header into its own WAV."""
    from backend.stations.dubbing.qc import atempo_wav

    original = _tone_wav(1.0)
    stretched = atempo_wav(original, 0.8)
    cut = truncate_wav(stretched, 600)
    m = measure_timing(original, cut, tolerance_ms=45)
    assert m["verdict"] == "flagged"
