# Eval Pipeline: Ingest scene understanding

## System Overview
After ingest proves the file opens and is not corrupt, Gemini watches the original clip and writes two fields onto the shot: `spoken_words` and `scene`. The orchestrator and later stations read that shot metadata. Maturity: Stage 2 → 3 (labeled suite + live agent + known-bad).

## Evaluator Stack
### Layer 1 — Deterministic
- Quarantine path never calls Gemini (`tests/test_ingest_understand.py`).
- `has_speech=false` coerces `spoken_words` to empty.
- Shot document stores both fields; API returns them; orchestrator prompt carries them.
- Pass/fail: pytest.

### Layer 2 — Statistical
- `ingest_transcript_judgment` mean_case_accuracy >= 0.8
- `ingest_scene_judgment` mean_case_accuracy >= 0.8
- 8 labeled cases × 3 live runs (`backend/evals/thresholds.yaml`).

### Layer 3 — LLM-as-Judge
The ingest agent is the model under test. Hits are label-sheet checks (expected words / scene keywords), not a second judge inventing scores.

## Checkpoints
1. File classify pass → else halt, no understand.
2. Agent JSON parse + hard gates.
3. Stamp `pc-shots.scene_understanding` only after gates.

## Dataset
| Split | Size | Description | Source |
|---|---|---|---|
| Happy | 2 | Known Chirp lines on a color field | Eval-time TTS + ffmpeg (C-1.3) |
| Edge | 2 | Tone-only / silent picture; no words | ffmpeg lavfi |
| Adversarial | 1 | Speech on a blue field — must not drop the picture | TTS + color |
| Known-bad | 2 | Silent/testsrc must not invent dialogue; empty scene fails keywords | slate.mp4 + silent mux |
| Visual | 1 | testsrc slate: scene mentions test/pattern/color | `fixtures/g1/slate.mp4` |

## CI/CD Integration
- Pre-merge: Layer 1 pytest + `make eval-check` (threshold structure).
- Nightly / task DoD: `python scripts/ingest_understand_eval.py` (print cost; `--yes` over $5).
- Production: sample ingest watches via existing OTEL agent spans.

## Baselines and Alerts
First live run is the baseline. Regression: either suite mean drops below 0.8 or >10% from that baseline.

## Cost Estimate
8 multimodal flash calls/run × 3, plus Chirp on speech rows. Printed before billing.

## Recommended Tools
Project eval JSONL + pytest + `run_agent_call` (no parallel eval framework).
