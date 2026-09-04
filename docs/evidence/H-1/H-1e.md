# H-1e — Verification agent + hard-filter wiring

TDD + EDD per plan §6 step 3. Commit: see `git log -1 --format=%H`.

## What was built

- `backend/supervisor/agents/verification.py`
  - `verify(case, findings, settings)` — one real Gemini pass over every specialist finding; signature matches the deliberation cycle's `verifier` injection point exactly (`deliberation.py` has accepted it since H-1a).
  - `validate_verdict_payload` — deterministic gate: decision/confidence enums, non-empty reasons, and the **phantom-veto guard** (a rejected evidence_ref must exist among the findings' claims — the model cannot veto claims that don't exist). Specialist approval is computed DETERMINISTICALLY from the rejected set (a specialist survives iff it keeps at least one claim) — never model discretion.
  - Veto contract: veto requires an actual CONTRADICTION with the case evidence; sound inference from consistent evidence is approval. (This rule was sharpened after the first eval run — see below.)
- `run_deliberation_cycle(verifier=...)` wiring unchanged since H-1a; production use of the real verifier lands with the H-0b ACT-mode gate.

## TDD evidence

`tests/test_verification.py` — 9 tests, including the **DoD grep-test as an executable test**: through the REAL `apply_verdict` + `rank_actions` path, a vetoed finding's actions never reach the ranked list (asserted), while the surviving specialist's claims stay intact. Plus: happy path (rejected refs preserved, deterministic specialist approval), phantom-veto rejection, 2 bad-enum rejections, empty-reason rejection, foreign-case rejection, prompt carries all claims + case evidence, wiring (persona `verification_agent`, span `specialist.verification`, schema).

## EDD evidence (live run, real Gemini, real cost — C-1.1)

`verification_veto_eval.jsonl` + `verification_veto_summary.json` (this directory):

- **mean_veto_accuracy = 1.0 (4/4), threshold 0.8 → PASS** on real `gemini-3.7-flash` (thinking HIGH) via the single instrumented site.
- Adversarial catches (the DoD case): verdict 01 vetoes "retry will fix it" when the cited error shows checksum corruption; verdict 03 vetoes a 16:9 claim whose own cited field says 4:3. Correct approvals: the loudness diagnosis (02) and the transient-429 diagnosis (04).
- **Eval-driven prompt refinement (recorded honestly):** the first live run scored 0.75 — the verifier over-vetoed case 02 (rejected a sound re-render inference because its single cited field alone didn't prove it, though the case evidence did). The veto contract was sharpened to "veto on contradiction with case evidence, not on incomplete single-ref proof" — the same standard a human verifier applies. Second run: 4/4. No dataset labels were changed.

## Gate at commit

ruff ✓, mypy ✓ (71 files), thresholds.yaml ✓ (7 suites), integrity C-1.2 ✓, harness drift ✓, H-1 specialist suites 40/40 green.
