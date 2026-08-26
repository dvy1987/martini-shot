# Skill Outputs Log

| Date | Skill | Output | Notes |
|---|---|---|---|
| 2026-08-26 | project-constitution | docs/constitution.md | v1 — 8 categories, integrity-first rules derived from owner rulings |
| 2026-08-26 | feature-spec (specify) | docs/specs/2026-08-26-post-command-feature-spec.md | Status: Approved (owner rulings 2026-08-26). Slug: post-command |
| 2026-08-26 | implementation-plan | docs/plans/2026-08-26-post-command-plan.md | Phases -1→6, tasks TDD/EDD-tagged, gates G0–G5 mapped, parallelization map included |

## Next SDD phases for slug `post-command`
1. `/tasks` — derive agent-pickable task list from the plan (implementation-plan tasks-only mode) when ready to start execution
2. `/analyze` — spec-crosscheck readiness gate (required before `/implement`)
3. `/implement` — incremental-implementation + test-driven-development pairing, red-green per slice, EDD suites per generative capability

## Standing context pointers for any executing agent
- Mission briefing: `ideas/AO-STATION-MAP.md` (read FIRST; Amendments A1–A3 binding)
- Idea catalog: `ideas/IDEAS.md` · Track notes: `docs/grafana-track-notes.md`
- Constitution: `docs/constitution.md@1` — specs/plans cite this version; violations reject work
