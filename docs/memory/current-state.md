# Current State

**Where:** 2026-09-02 — Everything through **Gate G2 GREEN** is on `origin/main` (clean tree):
Track A, B-1/B-2(+B-2b live MCP on the supervisor registry, propose-only act gate), G1 gate run,
Replit UX Steps 3–6, **P1b live /api/v1 contract tests**, **B-3 real Vertex call** (cost_micros=400,
evidence `docs/evidence/B-3/`), D-1 quarantine, loudness, delivery+captions, **Spend Control
(adversarial money tests)**, pickups identity-QC + EDD, **G2 gate run** (`docs/evidence/G2/`).
**G2 highlights:** Spend Control throttled a seeded 40× pickups runaway (intake paused, Spend
approval opened, annotation id 35). Honest pack results (needs_human on silent/wrong-AR fixture —
truthful, not faked). All gates green at each commit.
**Known wart:** `create_incident` returns Grafana Cloud FK error (`Counters_orgID_fk`) — the
throttle hold still landed; needs investigation before H-* (incident-driven) work.
**Next queue:** G3 (generative gates: Veo/Omni quality bars), demo batch seed (E-3, 3 langs, billable),
H-* supervisor chains, J-3 Replit hosting rehearsal, J-4/J-5 README + video, J-6 submission ≥24 h early.
**Full handover:** `docs/plans/2026-09-01-post-command-handover.md` (rev 2) + latest `agent-handoffs.md` entry.
**Open:** F-4 hosted OAuth persistence; sign-in-to-approve (no firebase dep yet); Stage 1a behind G3.
