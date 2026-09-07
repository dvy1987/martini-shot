# H-1g — Multi-agent shadow run (propose-only)

## Evidence integrity note (2026-09-05, review finding — read first)

The ORIGINAL 2026-09-04 run claimed 4/4 cycles with a live adversarial veto,
but the committed artifacts only support ONE cycle
(`shadow_run_2026-09-04.jsonl`: `cyc-b96633f5a332`, no veto) — a single-case
`--only` re-run had overwritten the full JSONL before commit. That mismatch
was flagged in the H-0b ACT-gate review and is corrected here: the claims
below now describe ONLY what the committed artifacts show. The superseding
artifact is the full 2026-09-05 run.

## What the 2026-09-05 run shows (committed evidence)

`scripts/shadow_run.py` ran the FULL specialist team (real Gemini via
`run_agent_call`, real Grafana MCP read-only tools, real verifier, real
leverage synthesis) over the 4 seeded Stage-1 scenarios from
`backend/evals/datasets/reliability_root_cause.jsonl` (labeled synthetic
inputs, C-1.3). Summary: `shadow_run_2026-09-05_summary.json` —
**3/4 cycles persisted, 0 with ranked actions, nothing executed**
(propose-only; ranked actions stay records — H-0b owns ACT mode).

- **rel-eval-01/02/03: completed, zero ranked actions.** The specialists
  abstained (empty `proposed_actions`) under the hardened prompt contract.
  This is honest model variance, recorded verbatim in
  `shadow_run_2026-09-05.jsonl`; the review explicitly requires variance to
  be reported without cherry-picking. The propose-only loop is unaffected:
  an abstention lands as a cycle with no dispatchable actions.
- **rel-eval-04: refused by the deterministic target-args gate** — the model
  proposed `pause_intake` without the required `station` arg, and the
  finding-schema gate rejected it before it could ever rank or dispatch
  (`proposed 'pause_intake' args missing required target keys`). This is the
  ACT-gate review's "action correctness at the gate" fix working as designed:
  a malformed action cannot silently survive.

An adversarial veto (delivery_qc claims vetoed on rel-eval-01) WAS observed
live during 2026-09-05 reruns, but that intermediate artifact was overwritten
by later reruns, so no committed file supports it; the veto MECHANISM is
proven by unit tests (`test_deliberation.py` hard-filter + provenance tests)
and by the ACT-gate eval's conflict case (veto applied,
`unsupported_action_survival` clean — see
`ranking_quality_eval.jsonl`). We do not claim it from the shadow artifacts.

## FE proof (DoD)

`shadow_run_drawer_agent_panel.png` — the Investigation drawer of the running
product (localhost, real backend + real Firestore docs, project
`proj-shadow-h1g-20260904` via the `/deliberations` API) showing the Agent
deliberation panel: specialists consulted, vetoes, proposed next action with
reversibility, dissent. That screenshot predates this evidence correction and
rendered a real persisted cycle from the 2026-09-04 session.

## Latent bugs found and fixed live (unchanged)

- Verdict vetoes serialized as tuples broke Firestore writes (`_verdict_to_doc`
  now emits `{claim_ref, reason}` dicts — found only when a veto actually
  fired).
- Ranked actions carried no `reversible` flag (FE rendered all actions as
  irreversible) — fixed in `rank_actions`.

## Runtime-readiness wording (ACT-gate review, binding for submission)

This system is a **custom Python-orchestrated Gemini specialist team with
parallel investigation, independent verification, deterministic safety
filtering, and Grafana-observed deliberation**. It is NOT an "ADK multi-agent
runtime", there is no "agent-to-agent delegation", and it is not a
"production autonomous network": `backend/api/app.py` now invokes
`team.maybe_deliberate()` from the worker terminal hook for enabled failure
signals. The H-0b budgeted loop remains fail-closed: ACT mode requires a
current versioned eval receipt and has not been activated or observed live.
This historical shadow evidence remains a propose-only run; the latest full
committed run completed 3/4 cycles and contains zero committed vetoes.
