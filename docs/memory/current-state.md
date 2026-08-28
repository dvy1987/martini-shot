# Current State

**Where:** Repo scaffolded and agent-wired (2026-08-28). No product code yet. SDD position: constitution + spec + plan APPROVED → next SDD phases are `/tasks` → `/analyze` → `/implement`.
**Blocking:** owner Phase -1 accounts (F-1 Grafana stack, F-2 GCP + credits form before Aug 31); then G0 spike is the first build action.
**Gate:** CI-lite green (ruff/mypy/pytest/integrity/eval-check/harness-check); pre-commit installed. Harness v0 seeded: `docs/harness/manifest.json` (8 components), drift gate `make harness-check`.
**Key files:** AGENTS.md (root), frontend/AGENTS.md, backend/AGENTS.md, .cursor/rules/*.mdc, docs/knowledge-graph/GRAPH_INDEX.md, docs/constitution.md, docs/specs/, docs/plans/.
**Open:** spec §7 amendment proposal (SSE envelope, FE auth, Replit mechanics) awaits owner approval.
