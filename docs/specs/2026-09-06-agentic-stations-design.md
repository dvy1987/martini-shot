# Design: Agentic Stations (Amendment A10)
Date: 2026-09-06 | Status: Approved (owner, 2026-09-06 dialogue, revised after adversarial self-review)

## Summary
Every station with a judgment surface becomes agentic: four QC agents own quality/strategy
calls in Pickups, Extend, Dub, and Spend; four measurement-station agents own the RESPONSE to
deterministic reports (ingest triage, loudness remediation, caption fixes, delivery strategy);
a Batch Orchestrator agent plans the episode×language station sequence. Measurements
themselves (checksum, LUFS, rule verdicts) stay deterministic and machine-checkable.

## Problem
Numeric QC proxies underfit real quality; retry/escalation strategy is policy-shaped rather
than reasoned; measurement-station REMEDIATION (triage, fix, profile routing, batch-level
correlation) is policy-table-shaped; batch sequencing across episodes and languages is
manual. Owner rulings (2026-09-06): "the agent may take the deterministic suggestion under
advisement" — agents hold real judgment authority with full audit; "use LLMs wherever the
product demands it, EDD, real model calls, no canned responses."

## Approach (chosen: Option 2, bespoke agents)
One persona per judgment domain, each with its own tools, schema, prompt tuned against real
model responses, and its own EDD gate. Real Vertex calls only (C-1.1); no canned responses.
Prompts are iterated on actual model outputs (the H-1b hardening loop).

## Architecture
- `backend/supervisor/station_agents/` — shared base: `run_station_call` (wraps
  `otel_ai.run_agent_call`, one metered call site per agent), `StationDecision` schema:
  `{agent, decision, deterministic_advice, overridden: bool, reason, proposal{command, args,
  cost_estimate_micros}}`, schema-validated (fail loud), persisted to the job doc, Grafana-
  annotated. H-0 remains the ONLY executor; agents propose, H-0/queue dispatch.
- Personas (bespoke, 8 + orchestrator):
  - **Pickups Vision QC Agent** (retrofit D-6): sees real frame extracts + flicker metric doc;
    decides accept / retry-with-strengthened-anchors / needs_human; may override the numeric
    gate with stated reason.
  - **Extend QC Agent** (retrofit D-9): accept-as-draft / bounded-revision / escalate.
  - **Dub QC Agent** (E-2, agent-native): listens to flagged audio (Gemini audio input) for
    truncation/artifacts; decides accept / re-render with pacing change / escalate.
  - **Spend Steward** (retrofit D-7): receives deterministic policy trigger as advice; chooses
    among allowed responses (throttle/stop/require-approval) with reason; incident still
    created on every enforcement action (C-4.3).
  - **Ingest Triage Agent** (D-1): consumes the deterministic probe/corruption report; decides
    quarantine disposition — re-ingest / salvage / reject — with BATCH-level correlation
    (recurring identical anomalies across episodes → upstream cause, one escalation, not N
    rejections). Batch state read via Firestore, read-only.
  - **Loudness Strategist Agent** (D-2): consumes the per-stem diagnosis; decides remediation —
    which fix path (stem-targeted, limiter, re-mix escalation) — and profile routing (accept
    for social, block broadcast); season-coherence mode reads sibling-episode measurements.
  - **Caption Remediation Agent** (D-3/D-4): turns deterministic violation reports into concrete
    fixes (re-segmentation, line rewrites preserving meaning, re-timing); every proposed fix is
    RE-VALIDATED by the deterministic rule engine before it can ship (closed loop, C-1.1: the
    validator remains the arbiter).
  - **Delivery Strategist Agent** (D-4): profile selection when multiple destinations qualify,
    accept-with-deviation calls with stated rationale, fix-suggestion generation routed through
    H-0.
- **Batch Orchestrator Agent** (`backend/supervisor/orchestrator.py`, E-3): reads an approved
  episode×language manifest, plans the station chain per item (real station vocabulary only),
  submits through the Firestore lease queue, monitors, re-plans on failure using the H-0b
  signal path. Bounded: only manifest items, only real stations, cost estimate printed before
  any billable run (C-7.2).

## Key Decisions
1. Deterministic verdicts are ADVISORY (owner ruling) — QC agents may override numeric gates;
   every override is an explicit logged event (`overridden: true` + reason) and is scored by
   eval (override precision). No silent gates.
2. For measurement stations (ingest/loudness/captions/delivery) there is nothing to override —
   the number IS the number. The agent owns the RESPONSE to the deterministic report: triage,
   remediation strategy, fixes, profile routing. Measurement stays machine-checkable evidence;
   fixes proposed by agents are re-validated by the deterministic rules they must satisfy.
3. Bespoke personas, not one shared judge (owner choice): each gets tuned prompts and its own
   eval bar; cost is cents per job at flash tier.
4. Batch-level correlation is a first-class agent capability (per-station single-file views
   cannot see "every episode from tape 3 drifts").
5. Amendment A10 to the A4 stage freeze: agentic station layer enters Stage 1 scope
   (owner-approved 2026-09-06); logged in `docs/memory/decision-log.md`. Owner accepted the
   schedule risk to Sep 8 in choosing bespoke per-station agents.

## Edge Cases
- Agent call fails / malformed schema → deterministic verdict used, job marked
  `decision_mode: deterministic_fallback` (visible, never silently).
- Agent unavailable does NOT block the lease worker (same fire-and-forget discipline as H-0b).
- Orchestrator refuses stations not in the manifest and stations that don't exist (fail loud).

## Testing
- TDD: decision schema validation, orchestrator plan/submit/re-plan mechanics, H-0 routing.
- EDD (C-3.4): suites + datasets seeded BEFORE agents: `pickups_qc_judgment`,
  `extend_qc_judgment`, `dub_qc` (6 segments × 3 languages, truncation recall ≥ 0.9),
  `spend_steward_judgment`, `ingest_triage_judgment`, `loudness_strategy_judgment`,
  `caption_remediation_judgment`, `delivery_strategy_judgment`, `orchestrator_planning` —
  mean_case_accuracy ≥ 0.8, override precision scored; 3 independent runs reported verbatim;
  evidence archived under `docs/evidence/`. All runs are real billed model calls; prompts
  iterated against actual responses (the H-1b hardening loop).

## Non-Goals
- No LLM recomputation of measurements (hash/LUFS/rule verdicts stay exact and
  machine-checkable). No new H-0 command vocabulary beyond existing + dub/extend job kinds.
- No autonomous spend beyond the H-0b envelope. No weight fine-tuning.

## Not Doing (and Why)
- Full per-station tool registries: agents read job docs + metric docs via injected readers —
  scope enough for judgment, smaller surface before the deadline.

## Key Assumptions to Validate
- [ ] Flash-tier agents make QC calls consistent enough to clear 0.8 bars — validated by the
      EDD suites before any station uses them in ACT mode.
- [ ] Orchestrator plans stay inside policy spend — validated by orchestrator_planning eval.

## Open Questions
None.
