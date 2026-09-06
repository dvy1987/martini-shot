"""Dubbing station runner (E-2) — deterministic surface, TDD.

The station: TTS synthesize → deterministic timing measurement → Dub QC
Agent judgment (real Gemini listen) → optional one-shot pace-adjusted
re-render → ALTERNATE attached to the shot. The pure helpers are tested
here; the real calls are gated by the live eval."""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest

from backend.stations.dubbing.run import (
    DUB_TOLERANCE_MS,
    final_status,
    time_fit_dub,
)

SAMPLE_RATE = 24000


def _tone_wav(seconds: float) -> bytes:
    """Deterministic non-periodic AM tone (labeled synthetic input, C-1.3)."""
    buf = io.BytesIO()
    n = int(SAMPLE_RATE * seconds)
    frames = b"".join(
        struct.pack(
            "<h",
            int(
                12000
                * (0.5 + 0.3 * math.sin(2 * math.pi * 3.1 * i / SAMPLE_RATE))
                * math.sin(2 * math.pi * 440.0 * i / SAMPLE_RATE)
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


def _fake_synth(duration_s: float, k: float = 1.4):
    """Injectable synthesizer with a realistic nonlinear rate response:
    duration = base * rate^-k. Asserts the loop's calls, nothing more."""

    calls: list[float] = []

    def synthesize(
        _settings, *, ssml: str, language_code: str, speaking_rate: float = 1.0
    ):
        calls.append(round(speaking_rate, 4))
        return {
            "audio_bytes": _tone_wav(duration_s * speaking_rate ** (-k)),
            "cost_estimate_micros": 500,
        }

    return synthesize, calls


def test_time_fit_stretches_to_tolerance():
    """Studio technique: ONE render, then ffmpeg atempo time-compresses the
    actual waveform to the source window — exact, immune to TTS noise."""
    original = _tone_wav(2.0)
    synth, calls = _fake_synth(2.0)  # rate response irrelevant now
    fit = time_fit_dub(
        object(),
        ssml="<speak>hola</speak>",
        language="es",
        original_wav=original,
        first_wav=_tone_wav(2.6),  # dub naturally runs 1.3x long
        synthesize=synth,
        ffmpeg_bin="ffmpeg",
    )
    assert fit["fit_applied"] is True
    assert fit["tempo"] == pytest.approx(1.3, abs=0.01)
    assert calls == []  # no re-render: the fit is local waveform work
    assert abs(fit["measurements"]["duration_delta_ms"]) <= DUB_TOLERANCE_MS
    assert fit["measurements"]["verdict"] == "pass"


def test_time_fit_refuses_out_of_band_tempo():
    original = _tone_wav(2.0)
    synth, _ = _fake_synth(2.0)
    fit = time_fit_dub(
        object(),
        ssml="<speak>hola</speak>",
        language="es",
        original_wav=original,
        first_wav=_tone_wav(4.4),  # needs tempo 2.2 — outside ffmpeg range
        synthesize=synth,
        ffmpeg_bin="ffmpeg",
    )
    assert fit["fit_applied"] is False
    assert fit["measurements"]["duration_delta_ms"] == 2400


def test_time_fit_noop_when_already_in_tolerance():
    original = _tone_wav(2.0)
    synth, calls = _fake_synth(2.0)
    fit = time_fit_dub(
        object(),
        ssml="<speak>hola</speak>",
        language="es",
        original_wav=original,
        first_wav=_tone_wav(2.01),
        synthesize=synth,
        ffmpeg_bin="ffmpeg",
    )
    assert fit["fit_applied"] is False
    assert calls == []


def test_final_status_maps_decisions():
    assert final_status("accept") == "pass"
    assert final_status("re_render") == "needs_human"
    assert final_status("needs_human") == "needs_human"


def test_dub_tolerance_matches_threshold_gate():
    # The station's default tolerance and the EDD gate (dub_timing MAE
    # ≤45 ms) must tell the same story.
    assert DUB_TOLERANCE_MS == 45
