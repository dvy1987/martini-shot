# Current State

**Where:** 2026-09-06 — G2 GREEN, production deliberation wired, review findings 1–8 closed, and
**Amendment A10 (agentic stations) approved and under way**: A10-1 **Dub QC station DONE and
eval-green** (commits `7abdb5f`, `3ea25b8`; live 3-run evidence `docs/evidence/E-2/` — timing MAE
4.8–9.9 ms ≤ 45, truncation recall 1.0 ≥ 0.9, ~$0.07/run). StationDecision contract +
`run_agent_call` audio/timeout/429-retry shared machinery in place. H-1e hard-filter DoD fixed
(actionless-but-claimed findings survive). Also on main: H-0b budgeted loop, production
specialists + `maybe_deliberate` on job terminal, atomic budget reservations, settings owner gate
(`d89f4c9`), A10 design spec (`f22cef9`).
**In flight:** A10-2 Batch Orchestrator (`backend/supervisor/orchestrator.py` — manifest
validation/chain/cost/id surfaces GREEN so far; agent planner + EDD `orchestrator_planning` +
queue submission next).
**Next queue:** A10-3 strategists → A10-4 retrofits → E-3 batch manifest seed (owner approves
billable run, C-7.2) → G3 gate evidence → FE playable dub pair → H-1h/i/j agents.
**Known wart:** `create_incident` FK error — one-time Grafana Incidents init by owner (browser).
**Open:** F-4 hosted OAuth persistence (parked); sign-in OAuth owner one-timer (5 min, pre-demo);
Stage 1a ops behind G3.
**Full handover:** `docs/memory/agent-handoffs.md` (2026-09-06 entry has the load-bearing
E-2 lessons) + `docs/plans/2026-08-26-post-command-tasks.md` (A10 rows).
