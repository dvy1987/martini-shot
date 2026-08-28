# frontend/AGENTS.md — scoped agent rules

See root `AGENTS.md` for project-wide context (constitution, boundaries, Session Lifecycle, Orchestration Map). This file adds frontend-only rules.

## What this is
React + Vite + TypeScript SPA in `frontend/`. Interim deploy: Firebase Hosting; final: Replit (static deployment serving `frontend/dist`) — identical build, only base-URL/CORS change (spec §7, task J-3). The SPA talks ONLY to the backend `/api/v1` API, never directly to Google AI or Grafana.

## Key Commands (after scaffold task C-1 creates package.json)
```
Install:  npm ci              (in frontend/)
Dev:      npm run dev
Build:    npm run build       (output frontend/dist — the exact folder Replit serves)
Test:     npm run test        (vitest; client logic is TDD per plan C-1)
Lint:     npm run lint
```

## Non-Obvious Patterns
- Env vars MUST be `VITE_`-prefixed and are baked at BUILD time from `frontend/.env.local` (gitignored; see `.env.example`). Two hosts = two build-time base URLs; never resolve the host at runtime.
- ALL backend calls go through ONE typed API client module (`src/api/`), contract-tested against the backend OpenAPI schema. Components never call fetch directly.
- SSE (`/api/v1/projects/{id}/events`) is the only live channel; reconnect with backoff; no polling unless the plan adds it.
- Design is DECIDED: `docs/design/DESIGN.md` (owner-approved 2026-08-28, evidence-first / exception-first / film-native grammar) is the binding direction — read it before any component work. Future visual changes still run the `frontend-design` chain (root Agent-Led Design block) and amend DESIGN.md. No lorem ipsum, no placeholder data — the UI renders only real API state.
- The Approvals inbox renders Spend Control escalations (S5b) — same inbox component, distinct badge.
- Replit static hosting: SPA routing needs the platform's SPA/rewrite option enabled (verify at task J-3); `.replit` lives at repo root and only points build/serve commands at `frontend/`.

## Boundaries (frontend-scoped)

### Allowed without asking
- Components, styles, client logic, and their tests under `frontend/src/`
- Contract-test updates that track the backend OpenAPI schema

### Ask first
- Build/deploy config: `vite.config`, `.replit`, `firebase.json`
- New npm dependencies; design-token changes after direction approval

### Never
- Direct Gemini/GCP/Grafana calls from the browser (C-2.1, C-6.1)
- Mock backends or fake data in components (C-1.*) — real backend plus labeled fixtures only
- Commit `.env.local` or any baked secret
