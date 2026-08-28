# Current State

**Where:** Frontend skeleton buildable and committed (2026-08-28): React 18 + Vite 5 + Tailwind v4 tokens, router, app shell, designed empty states, typed `/api/v1` client + SSE/health hooks, 19 vitest tests. Backend not started. SDD position unchanged: `/tasks` → `/analyze` → `/implement`.
**Blocking:** owner Phase -1 accounts (F-1 Grafana stack, F-2 GCP + credits form before Aug 31); then G0 spike is the first build action. Replit execution: owner feeds step prompts 1–6 into Replit agent.
**Gate:** CI-lite green (ruff/mypy/pytest/integrity/eval-check/harness-check); frontend green (`tsc --noEmit`, eslint, vitest 19/19, `vite build`). Harness v0 seeded: `docs/harness/manifest.json` (8 components), drift gate `make harness-check`.
**Key files:** AGENTS.md (root), frontend/AGENTS.md, backend/AGENTS.md, docs/design/DESIGN.md (v3, binding), frontend/src/ (shell, lib, api, hooks), .cursor/rules/*.mdc, docs/knowledge-graph/GRAPH_INDEX.md, docs/constitution.md, docs/specs/, docs/plans/.
**Open:** AUTH RULED (2026-08-28): sign-in only when approving — visitors browse freely, decisions require Google login, identity in audit trail. Spec §7 amendment (SSE envelope, FE auth, Replit mechanics) drafted for that ruling; awaiting owner approval before spec edit. SSE url intentionally `null` until G1 — no mock API ever (C-1.2/A2).
