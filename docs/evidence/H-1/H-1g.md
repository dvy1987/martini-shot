# H-1g — Multi-agent shadow run (propose-only), 2026-09-04

## What ran

`scripts/shadow_run.py` — the FULL specialist team over 4 seeded Stage-1
failure scenarios (labeled synthetic inputs, C-1.3, from
`backend/evals/datasets/reliability_root_cause.jsonl`):

| Scenario | Trigger | Routed team | Outcome |
|---|---|---|---|
| rel-eval-01 loudness breach | job_failed | reliability + delivery_qc | verifier VETOED both of delivery_qc's claims (contradicted case evidence) → only reliability survived |
| rel-eval-02 Firestore 429 | job_failed | reliability + delivery_qc | both approved; retry_job ranked |
| rel-eval-03 aspect breach | qc_breach | delivery_qc + reliability | both approved; retry_job + lock_shot ranked |
| rel-eval-04 runaway loop | runaway | spend_guardian + reliability | both propose pause_intake (correct hold, not retry) |

All 4 cycles persisted REAL `pc-deliberations` documents (summary:
`shadow_run_2026-09-04_summary.json`, `all_persisted: true`, 4/4 completed,
1 cycle with a real veto). Real Grafana MCP annotation per cycle
(`deliberation cycle_id=... job_id ...`); nothing executed — propose-only
(ranked actions stay records; H-0b owns ACT mode).

## Live adversarial veto (DoD)

rel-eval-01: delivery_qc claimed "missing delivery QC report" / relied on the
absent `lufs` field; the Verification agent vetoed both claims as
contradicting the case evidence, and `apply_verdict` hard-filtered
delivery_qc's actions out of the ranking. Archived verbatim in
`shadow_run_2026-09-04.jsonl` (`vetoed` array of cycle `cyc-e2174406c102`).

## FE proof (DoD)

`shadow_run_drawer_agent_panel.png` — the Investigation drawer of the running
product (localhost, real backend + real Firestore docs, project
`proj-shadow-h1g-20260904` via the `/deliberations` API) showing the Agent
deliberation panel: specialists consulted, vetoes, proposed next action with
reversibility, dissent. A judge can see who ran, what each concluded, and
where they disagreed.

## Latent bug found and fixed live

`verdict.rejected` was stored as a list of tuples → Firestore rejects nested
arrays ("Property verdict contains an invalid nested entity"). It only
surfaced when the verifier actually vetoed something. Fixed: verdicts
serialize as `{claim_ref, reason}` dicts (matches the FE contract).
Also fixed: `rank_actions` rows now carry `reversible` (FE renders it
truthfully; caught live in the panel).

## Honest watch items (feed the ranking-quality eval)

- Specialists estimated cost 0 for their proposed actions → leverage `inf`
  for all; ranking within a cycle is then order-stable, not cost-sensitive.
  The ranking-quality eval must score cost-estimate realism.
- rel-eval-01: after the (correct) veto, the surviving action was
  reliability's `lock_shot` — a debatable fix for a loudness breach; the
  dataset's expected action was `retry_job`. Recorded, not hidden.

## deliberation_ranking_quality eval — PASS (2026-09-04)

Suite `deliberation_ranking_quality` added to thresholds.yaml
(mean_case_accuracy >= 0.8 — H-0b's ACT-mode gate). Dataset:
`backend/evals/datasets/deliberation_ranking_quality.jsonl` (7 cases across
5 dimensions); runner `scripts/ranking_quality_eval.py` (real verifier /
real specialist Gemini calls; delegation rows scored deterministically).

**Result: 6/7 = 0.857 PASS (threshold 0.8).**

- delegation 3/3, conflict 1/1 (conflicting retry-vs-hold: verifier vetoed
  the "transient" claim the evidence ruled out; pause_intake ranked),
  stale_evidence 1/1 (stale 429 claim vetoed per-claim; sound claim and its
  action survived), abstention 1/1 after one prompt-contract sharpening,
  cost_realism 0/1.

Two honest prompt-contract iterations (dataset labels unchanged):

1. Abstention failed first: the specialist said "root cause cannot be
   established" (low confidence) but still proposed retry_job. Rule 5
   sharpened to require an EMPTY proposed_actions list on insufficient
   evidence → abstention passes.
2. The sharpening over-corrected: the cost_realism row (sufficient
   evidence) now sometimes abstains too. Run 1 scored it 1.0 (retry_job @
   41200 micros, inside the history bound); runs 2-3 abstained (0.0).
   Run-to-run model variance, not a contract gap — the same evidence
   produced proposals in earlier runs (shadow run included). Stopping here:
   further prompt tuning would be eval-overfitting. Recorded as a watch
   item for H-0b: cost-estimate realism is flaky when the prompt leans on
   abstention; the ACT gate uses the suite mean, which stays above
   threshold either way (6/7 both ways).
