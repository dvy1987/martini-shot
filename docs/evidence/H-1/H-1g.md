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

## Remaining DoD item

`deliberation_ranking_quality` eval (extended per plan §6 step 8:
delegation/disagreement/abstention + stale-evidence veto cases) — separate
run, gated H-0b ACT mode; tracked as the next task.
