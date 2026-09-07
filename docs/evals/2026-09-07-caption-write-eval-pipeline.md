# Caption writer + editor eval pipeline (2026-09-07)

## System
Delivery writes missing captions from the dubbed script (deterministic wrap/time),
calls Caption Remediation when an SRT exists but fails D-3, and calls Caption
Writer (Gemini) only when there is audio and no script. The D-3 rule engine
re-validates every proposal before it can ship.

## Three layers
1. **Deterministic:** wrap ≤42 chars, ≤20 cps, min duration, gaps. Tests: `tests/test_caption_write.py`, `tests/test_captions.py`.
2. **Statistical:** `caption_write_judgment` mean_case_accuracy >= 0.8, 8 cases × 3 live runs.
3. **LLM-as-judge:** the writer agent itself. Hit = expected decision + clean re-validation + every script word present. Empty-script case is the known-bad (must not invent).

Editor suite `caption_remediation_judgment` is unchanged (already green).

## Cost
8 flash calls/run × 3. Printed before billing; `--yes` if estimate > $5.
