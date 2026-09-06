# ADR-0004: Dub time-fit via deterministic ffmpeg atempo; agentic QC with reference-script awareness

Date: 2026-09-06 | Status: Accepted | Amends: — | Supersedes: —
Task: E-2 (Dub QC station) under Amendment A10 | Evidence: `docs/evidence/E-2/`

## Context

The dub station (E-2) must deliver dubs whose duration matches the source line
within ±45 ms (S4 tolerance, `dub_timing` EDD gate), and judge them for
truncation/artifacts. Three candidate approaches for the timing fit were
evaluated against REAL Chirp 3 HD behavior:

1. **Re-render at an adjusted speakingRate / SSML prosody rate.** Measured
   probe (`scripts/probe_tts_rate.py`, 2026-09-06): the rate→duration response
   is nonlinear — rate 0.8 yields 1.34× duration, not 1.25× — and render
   lengths vary run-to-run (generative voice). A single re-render leaves ~10%
   residual (hundreds of ms); an iterative residual-correction loop needs 3+
   billable renders and still oscillates.
2. **Single deterministic ffmpeg `atempo` stretch of the actual waveform.**
   Exact (duration scales by 1/tempo), free, local, pitch-preserving, immune to
   render noise. Limited to tempo ∈ [0.5, 2.0] — outside that band the dub is
   not a pacing problem and must not be mangled.
3. **Post-render sample trimming/padding.** Exact but only fixes sub-tolerance
   residuals; cannot bridge 10–30% mismatches without audible gaps.

## Decision

- **Time-fit:** ONE TTS render, then `qc.atempo_wav` stretches the actual
  waveform to the source window (tempo = dub/source). Keep the stretch only if
  it closes the gap; refuse out-of-band tempos, fail loud.
- **Agent judgment:** the Dub QC Agent listens to the FITTED dub (never a
  pacing draft) via one metered Gemini call with the dub as an inline audio
  part, and receives the REFERENCE LINE (target-language script) in the
  prompt. Without the script, missing content is undetectable — a truncated
  "Prise trois." is a complete sentence in isolation (verified twice by
  transcription probes, `scripts/probe_fr03_hear.py`).
- **Eval defect mutation:** truncation probes are a hard EOF mid-speech
  (`truncate_speech_wav`, 10%-of-loudest-50ms-RMS floor). Tail cuts remove
  TTS trailing silence and are inaudible — the agent was RIGHT to pass them;
  the dataset was the defect until fixed.
- **WAV hygiene:** ffmpeg piped WAVs carry streaming headers
  (nframes=0xFFFFFFFF); readers read to EOF and never copy nframes.

## Consequences

- `dub_timing` gate is achievable and green: MAE 4.8 / 8.0 / 9.9 ms over 3
  live runs (gate ≤45). `dub_truncation_recall` 1.0 (gate ≥0.9).
- The station pays for ONE TTS render per dub (plus one re-render only when
  the agent rejects for artifacts), not a render loop — cost ~$0.07/eval-run
  of 18 cases.
- The floor constants (10% of loudest window) are calibrated for Chirp 3 HD
  output at 24 kHz; if another voice family is adopted, re-probe before
  trusting the mutation.

## Alternatives rejected

- Re-render loop (nonlinear response, 3× cost, still oscillatory).
- Silence-trim-only fit (cannot compress oversize speech).
- Trusting the TTS service's pacing fields (measured non-compliant).
