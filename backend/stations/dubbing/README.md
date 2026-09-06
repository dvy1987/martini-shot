# Station: Dubbing (E-2, A10)

One line in, one dubbed line out, judged by an agent that actually listens.

## What it does

1. **Synthesize** — real Google Cloud TTS (Chirp 3 HD) renders the
   target-language SSML line for the shot.
2. **Time-fit** (deterministic, `qc.py`) — a translated line's natural
   length rarely matches the source, so the dub is time-fitted to the
   source window with ONE `ffmpeg atempo` pass (studio time-compression:
   exact, pitch-preserving, immune to TTS render noise; measured probe
   2026-09-06: Chirp's speakingRate/prosody response is nonlinear, 0.8 →
   1.34x, so re-render fitting can't hit a 45 ms bar). Tempos outside
   ffmpeg's [0.5, 2.0] band are refused, never mangled.
3. **Measure** (deterministic, `qc.py`) — duration delta and sync offset
   between the source line and the fitted dub, via normalized
   cross-correlation of 20 ms energy envelopes. Tolerance ±45 ms (mirrors
   the `dub_timing` EDD gate in `backend/evals/thresholds.yaml`).
4. **Judge** (`backend/supervisor/station_agents/dub_qc.py`) — the Dub QC
   Agent receives the fitted dub as an inline audio part in ONE metered
   Gemini call (through `run_agent_call`, the single instrumented call
   site, C-4.4) and classifies it:
   `clean | truncated | artifact | pacing_mismatch`.
   **The deterministic verdict is advice, not the gate** — the agent may
   override it, but an override is always explicit (`overridden: true`)
   with a mandatory reason, validated by the `StationDecision` contract.
5. **Re-render** — on `re_render`, the station synthesizes ONCE more (voice
   renders are nondeterministic), re-fits, re-measures, and the agent
   decides again; the second verdict is final.
6. **Attach** — the dub is an ALTERNATE on its shot (AL-1, `op=dub_<lang>`)
   with the measurements as eval scores. Flagged verdicts are still
   recorded so the spend is visible in the audit trail.

## Job contract

- `job.input_refs[0]` — `gs://` URI of the source WAV line
- `job.result.shot_id`, `job.result.language` (`es`/`fr`/`de`),
  `job.result.ssml` — the target-language line
- Output: `job.result.measurements`, `job.result.agent` (full decision doc),
  `job.result.artifact_ref`; `job.status` ∈ `pass`/`needs_human`
- Cost (C-6.4): billed TTS characters + metered agent tokens, integer micros

## Files

| File | Role |
|---|---|
| `qc.py` | Deterministic measurement (no LLM): `measure_timing` |
| `run.py` | Station runner: synthesize → measure → agent → re-render → attach |
| `../supervisor/station_agents/dub_qc.py` | The agent: prompt, schema, `decide_dub` |
| `backend/evals/datasets/dub_qc.jsonl` | 18-case EDD dataset (6 lines × 3 langs, 4 truncation probes) |
| `scripts/dub_qc_eval.py` | Live eval vs `dub_timing` / `dub_truncation_recall` gates |

## Fixtures

`fixtures/dubbing/` holds six real TTS-rendered source lines (see its README,
C-1.3 — labeled synthetic INPUT media only).

## Telemetry

Span `station.dub.run` (job_span) + agent child span
`station.dub_qc.agent` (`gen_ai.agent.name=dub_qc`), `record_job` metrics
(duration/cost/outcome), structured logs with `job_id`/`station`/`project_id`.
