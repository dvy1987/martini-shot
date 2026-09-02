# Plan: H-0b — Budgeted Autonomy Loop (owner ruling 2026-09-02)
Date: 2026-09-02 | Status: Draft — engineering plan for the owner-approved ruling in `docs/memory/decision-log.md` ("Budgeted autonomy: supervisor acts freely inside a $20 envelope")
Depends on: H-0 (approval→action executor, design locked `docs/specs/2026-09-02-h0-approval-executor-design.md`), AL-1 (alternates model), D-9 (Extend)
Sequencing (tasks file, `docs/plans/2026-08-26-post-command-tasks.md`, Phase 3a-early): H-0 → AL-1 → D-9 → **H-0b** → Dub QC (E-2/E-3) → G3

## Summary
The supervisor gets a nightly spend envelope (default $20) inside which it deliberates on its own — collects candidate actions, ranks them by leverage, and acts down the list until the money runs out. It is **a caller of H-0, not a second brain**: every action it takes goes through the same dispatcher, state machine, and audit trail Spend Control and human approvals already use. This is the demo differentiator: judges can read the ranked reasoning table in Grafana, not just trust that "the AI thought."

## Owner ruling already logged (not re-opened here)
- Default envelope **$20** = `POST_COMMAND_BUDGET_MICROS=20000000`, adjustable in product settings, no redeploy.
- Envelope covers renders, retries, drafts, **and continuity adds** — owner explicitly overrode the recommendation to keep continuity human-approved. Compensating controls: continuity changes are alternates-lane only (never overwrite the locked cut), one-click revert, Grafana alert + annotation on every continuity mutation, full ranked-reasoning trail persisted.
- Daily house cap (Spend Control) sits **above** the envelope. Draft-first is the default reflex. The autonomy toggle can demote the whole loop to propose-only at any moment.
- Deliberation runs as a background job, `gemini-3.7-flash` thinking HIGH, per the project's text-LLM standard (C-6.5 — never inline in an HTTP request).

## Owner rulings on the open engineering questions (2026-09-02, resolved)
- **Self-correction:** confirmed as proposed — the loop may autonomously **supersede its own earlier adds** within the same night, but must **never re-fight a human's revert**. Once a human has acted on a target, that decision stands for the rest of the night; the loop's own later ranking cannot override it. This is enforced by the same order-safety mechanism as the sweeper (see H-0 amendment below) — a human's decision is always "newer" in effect and always wins.
- **No separate action-count cap.** Owner: "all the changes are reversible, and if the agent is within budget, it is ok." The $20 envelope is the **sole** quantity constraint on the loop — no `POST_COMMAND_MAX_AUTONOMOUS_ACTIONS_PER_NIGHT`. Reversibility (one-click revert, alternates-only, never touches the locked cut) plus the dollar bound are the accepted risk model; a count cap would just add friction without changing the actual risk. Removed from Settings round-trip and Definition of Done below.
- **New requirement, not previously in this plan:** the owner wants the supervisor's **judgment** hardened, not its latitude capped — "I would like the prompt and skills of the supervisor to be tuned and hardened so that it makes good decisions." This becomes its own gating task (§Decision-quality hardening) rather than a line in Testing — the leverage of "reversible + budgeted = ok" only holds if the ranking itself is actually good, so this is the real safety investment, not the cap.

## Architecture

### It's a caller, not a new brain
The deliberation job is a new **caller** of H-0's existing dispatcher (`docs/specs/2026-09-02-h0-approval-executor-design.md`). It does not get its own state machine, its own audit-trail writer, or its own annotation code. Concretely:
- Candidate actions are proposed the same shape as any other approval's `command: {name, args}`.
- The loop's own decisions are **self-approving** (`approver: "system:supervisor_budget"` instead of a human uid — additive to the `approver` field H-0 already reserves) — this is the one new concept: an approval that goes `proposed → approved` without a human click, because the deliberation itself *is* the approval decision, made under a pre-authorized budget.
- Dispatch, sweeper, crash recovery, Grafana annotation, SSE — all unchanged, all reused.

### Spend accounting — reuse, don't reinvent
The supervisor's spending is **real `cost_micros` on real Jobs** created through H-0's slow lane (e.g. a Veo Extend render). Spend Control's existing daily-budget check (`backend/stations/spend/policy.py::project_budgets`, `backend/stations/spend/detect.py::project_spend_micros`) already sums *all* `cost_micros` for the project/day — the supervisor's spend is naturally counted in that same total without any new accounting system. What's new is a **second, narrower counter**: micros spent *by the supervisor* since the night's deliberation job started, checked against the envelope before each candidate is dispatched. **Envelope window (pinned): one envelope per calendar night (UTC 00:00–23:59), shared across all cycles that night** — three signal-fired cycles in one night share the same $20; the counter resets at midnight UTC, and the daily house cap remains the backstop above it. Two counters, one source of truth (`cost_micros` on `pc-jobs`), no parallel ledger.

### Deliberation loop (one cycle)
1. **Trigger:** scheduled (nightly) or **signal-fired — signals are system events, not human actions**: a station emits a condition worth investigating (a stuck-at-`needs_human` job, a quarantine, a QC score crossing threshold), the same machinery as a Grafana alert. A person *may* also request a cycle from the UX, but never has to. Runs as a background job, not inline in any HTTP request (C-6.5).
2. **Collect candidates:** query real telemetry/state — stuck jobs, quarantines, `needs_human` pickups, low-quality QC scores — the same evidence sources H-1's investigation chain uses (PromQL/Loki/Firestore), not invented data.
3. **Score each candidate** — three factors, each computed from real data, not a vibe:
   - **Unblocks:** does this move a stuck delivery forward, or is it cosmetic? (binary or small integer weight, e.g. "blocks delivery" = 3, "improves quality only" = 1)
   - **Cost:** estimated `cost_micros` for the cheapest sufficient variant (draft before master — draft-first reflex).
   - **Reversibility:** an alternate/draft = fully reversible (weight 1.0); anything that would touch a locked cut = not eligible at all (H-0/AL-1 already make this structurally impossible — locked cuts are never a dispatch target).
   - `leverage = unblocks_weight / cost_micros`, reversibility only ever *excludes* (not-reversible candidates never enter the ranked list at all — this is stronger than "weighted down").
4. **Stack-rank, then dispatch down the list** through H-0 (self-approved), decrementing the night's spend counter, until the $20 envelope is spent. No separate action-count limit (owner ruling above) — the envelope is the only quantity bound.
5. **Persist the full ranked table** (candidate, leverage score, cost, decision taken or skipped, one-line why) as both a Grafana annotation/log line **and** a Firestore document (`pc-deliberations/{cycle_id}`) — the annotation is for the demo-visible audit trail; the Firestore doc is what the morning report reads to render leftovers as ranked proposals.
6. **Graceful degradation:** anything not reached before the envelope/cap empties is **not discarded** — it becomes a ranked, evidenced proposal in the morning report (H-2), status `proposed`, exactly like a human-initiated approval, just pre-ranked.

### Settings round-trip (no redeploy)
`POST_COMMAND_BUDGET_MICROS` lives in `Settings` (`backend/core/config.py`) sourced from Firestore (a `pc-control/budget` doc, same pattern as `pc-control/intake`), not only env vars — so the product's own Settings UI (spec §7 "Settings (autonomy toggle)") can write a new value and the *next* deliberation cycle picks it up without a code change or redeploy, matching the ruling's explicit requirement.

### Decision-quality hardening (owner requirement, gates ACT mode)
"Reversible + within budget = ok" only holds if the ranking is actually good — this is where the real safety investment goes, not a cap. Before the loop is allowed to run in ACT mode (autonomy toggle) with real money, it must clear an eval gate, built EDD-first per this project's own discipline (C-3.3):
1. **Rubric first** (`eval-rubric-design`): score each ranked decision on — (a) "unblocks delivery" is grounded in real evidence, not asserted; (b) cost estimate within the same ±20% tolerance already used for pickups (AC-S2.2 pattern); (c) non-reversible/locked-target candidates are correctly excluded, never merely down-ranked; (d) draft-first respected — never proposes a master when a draft would inform; (e) evidence citation discipline matches the existing PERSONA rule ("every claim must cite evidence").
2. **Adversarial dataset** (`adversarial-hat`): seeded candidate sets designed to tempt bad judgment, not easy cases — a cheap-looking but low-value action ranked artificially high by a naive cost-only heuristic; a costly-but-critical action a lazy heuristic would skip; a candidate whose supporting evidence is stale or already resolved by the time of ranking.
3. **Iterate the PERSONA prompt** (`backend/supervisor/agent.py`) and tool/evidence requirements against the rubric until threshold clears — this is the actual "tuning and hardening," not a one-time prompt write.
4. **Go-live gate:** the deliberation loop may run in propose-only mode for dispatch-mechanics testing before this clears. It does **not** run in ACT mode (spending real money autonomously) until the rubric eval passes threshold in `backend/evals/thresholds.yaml` (new suite `deliberation_ranking_quality`).

## Testing (TDD + EDD, RED-first)
- **TDD — dispatch mechanics:** self-approved candidates flow through the exact same `ApprovalStateMachine` as human approvals (grep-test: no second write path, same single-writer rule H-0 already enforces). Envelope/cap decrement is atomic and can't be double-spent by a concurrent cycle (reuse the transactional pattern, not a new one).
- **TDD — graceful degradation:** envelope exhausted mid-list → remaining candidates land in `pc-deliberations` as `proposed`, not silently dropped; a second real cycle later that same night is refused (or queued to next night) rather than double-spending.
- **TDD — floors hold:** a candidate whose cost would breach the *daily house cap* (not just the nightly envelope) is refused even with envelope room left — Spend Control's existing breach check is the source of truth, not a duplicate one.
- **EDD — decision-quality rubric** (see §Decision-quality hardening): dataset of seeded, deliberately-tricky candidate sets with a known correct ranking; threshold in `backend/evals/thresholds.yaml` (new suite `deliberation_ranking_quality`); mirrors the existing EDD-first discipline already used for D-5 pickups and E-2 Dub QC. This is the real gate for ACT mode, not a nice-to-have.
- **Adversarial (money, per constitution C-7 discipline already applied to Spend Control):** a candidate with a garbage/negative cost estimate must not be dispatchable (reuse `coerce_cost_micros` from `backend/stations/spend/detect.py`, don't reinvent).
- **TDD — human-wins rule:** a human revert followed by the loop's own stale re-ranking of the same target on the same night → loop's action is skipped, not replayed (same order-safety mechanism as H-0's sweeper).

## Definition of Done
- [ ] `pc-deliberations/{cycle_id}` documents exist from a real cycle (no mocked candidates — real stuck/quarantined jobs or a seeded-but-real fixture, per C-1).
- [ ] Ranked table appears as a Grafana annotation a judge can read, citing leverage/cost/decision per candidate.
- [ ] Envelope exhaustion observed end-to-end: cycle stops, morning report shows ranked leftovers.
- [ ] Daily house cap still halts spend even with envelope room left (integration test, not just unit).
- [ ] Settings round-trip proven: change the envelope value in Firestore, next cycle uses the new number, no redeploy.
- [ ] Autonomy toggle demotes the loop to propose-only with one flip — verified, not assumed (reuses the existing `Autonomy` class).
- [ ] Human-wins rule proven: a human revert cannot be re-fought by the loop's own stale ranking that same night.
- [ ] `deliberation_ranking_quality` eval clears threshold **before** the loop is allowed to run in ACT mode with real spend — propose-only testing of dispatch mechanics does not require this gate; autonomous spending does.

## Non-Goals (this slice)
- Building H-1's full investigation-chain playbooks — the deliberation loop *consumes* the same evidence sources H-1 will formalize, but H-1's rubric/playbook work is separate and can land in either order.
- A UI for editing the ranked table before it's dispatched — V1 is autonomous-then-reportable, not autonomous-with-a-preview-step (that would reintroduce the "pager with extra steps" pattern the owner explicitly rejected).
- Cross-night budget rollover (unused envelope does not carry to the next night) — unless the owner asks for it later.
