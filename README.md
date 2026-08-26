# Agentic Cinema — Grafana Track Idea Lab

Workspace for generating, comparing, and selecting a hackathon idea for the
**Grafana Labs track** of the [Agentic Cinema hackathon](https://agentic-cinema.devpost.com/)
(Google Cloud + partner ecosystem, powered by Gemini).

## Clock

- Contest window: **Jul 27 → Sep 9, 2026 (2:00 PM PT)**
- Today: **Aug 25, 2026** → roughly **15 days left**
- Google Cloud credit request form closes **Aug 31** (worth doing even if you may not need it)

## How this folder works

| Path | Purpose |
|---|---|
| `docs/agentic-cinema.md` | Original hackathon brief (source of truth) |
| `docs/grafana-track-notes.md` | Distilled constraints, Grafana MCP capability map, demo-data recipes, timeline |
| `ideas/IDEAS.md` | Full idea catalog: 51 ideas across 13 batches with scoreboard |
| `ideas/AO-STATION-MAP.md` | **START HERE** — complete mission briefing: chosen direction (AO "Post Command"), full journey context, all stations, three sequencings, demo plan, Amendments A1–A3 (AO-Full lock, Integrity Charter) |
| `docs/constitution.md` | Engineering constitution v1 — binding invariants every spec/plan cites |
| `docs/specs/2026-08-26-post-command-feature-spec.md` | Approved feature spec: architecture, station ACs, Grafana wiring inventory, frontend plan |
| `docs/plans/2026-08-26-post-command-plan.md` | Execution plan: Phases -1→6, TDD/EDD task tags, gates G0–G5, agent parallelization map, budget guardrails |
| `docs/skill-outputs/SKILL-OUTPUTS.md` | SDD artifact log + next-phase pointers |

Workflow: browse candidates → pick one (record why in SHORTLIST decision log) →
turn it into an implementation plan → build. When a new idea strikes, clone
TEMPLATE and add it; re-score in SHORTLIST if it competes with the leaders.

## Non-negotiables baked into every idea here

1. Runtime use of **Grafana Cloud MCP** (or OSS `grafana/mcp-grafana`) — queried/acted on by the agent, not just mentioned.
2. Built on **Gemini + Google Cloud** (ADK / Agent Engine / Vertex AI). No third-party AI models or agent APIs.
3. Solves a problem for **filmmakers, screenwriters, studio crews, or fans** — the theme is locked.
4. Runs on the **web** (easiest of the allowed platforms), hosted at a public URL.
5. Public repo, OSI license detectable at repo top, ≤3-min English demo video, brand-new project.
