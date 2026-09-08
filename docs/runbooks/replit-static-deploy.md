# Frontend Development and Hosting Runbook

This runbook describes the current frontend path. It is intentionally separate from backend Cloud Run deployment, which is handled by [`deploy.sh`](../../deploy.sh).

## Current posture

The repository’s `.replit` workflow starts the React/Vite frontend on port 5000 with:

```bash
cd frontend && npm run dev -- --host 0.0.0.0 --port 5000
```

The repository deployment target is static. `.replit` builds from `frontend/` with
`npm run build` and serves `frontend/dist`. The static host must rewrite unknown
paths to `index.html`; otherwise a browser refresh on a client-side route such as
`/approvals` or `/reports` returns a 404 before React can render it.

## Local development

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0 --port 5000
```

The Vite development server defaults to the port configured by the current Vite workflow. Replit exposes port 5000 for the project webview. If the frontend is run directly on the default Vite port, use the port shown by Vite and keep the backend origin configured separately.

## Build and verify

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm run test
npm run build
npm run smoke:static-deploy
```

The build runs TypeScript checking before producing `frontend/dist`.
The smoke check rebuilds the frontend, starts a local static preview from
`frontend/dist`, and verifies that `/`, `/approvals`, and `/reports` each return
the SPA HTML shell. Set `SMOKE_PORT` when the default preview port (`4173`) is
already in use:

```bash
SMOKE_PORT=4174 npm run smoke:static-deploy
```

This is the repeatable local or CI check for the static deployment contract.

## Runtime configuration

The frontend reads these build-time variables:

| Variable | Meaning |
|---|---|
| `VITE_API_BASE_URL` | The backend origin, without a trailing slash. |
| `VITE_API_KEY` | The backend read key sent as `X-API-Key`. |

Because Vite variables are compiled into the browser bundle, changing either value requires a new build. Do not commit them to the repository. Keep them in the host’s secret or environment configuration.

## Backend alignment

The backend must include the exact published frontend origin in
`CORS_ALLOWED_ORIGINS`. Keep the local development origins when developing
locally, then add the published URL as a comma-separated entry before deploying
the backend:

```dotenv
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,https://<published-app>.replit.app
```

Use the browser origin only: include the `https://` scheme and no trailing
slash or path. Do not use `*` or a broad `*.replit.*` pattern. The backend
uses this exact list so an unrelated Replit app cannot make browser API
requests. `REPLIT_DOMAINS` is the development domain and is not a substitute
for the published URL. Because the value is backend runtime configuration,
redeploy the backend after changing it. The backend also needs its own runtime
configuration, Firestore, Cloud Storage, Grafana MCP credentials, and an
enabled worker. A frontend that loads while the backend is unavailable is not
a working demo. The correct UI state is an explicit unreachable or offline
state.

## Judge verification

Before sharing a hosted URL, verify:

1. The root page loads without a JavaScript error.
2. The Timeline can list a project.
3. Uploading a short clip creates a real ingest job.
4. The Finish button creates or resumes a worklist.
5. Run Pulse either displays Grafana-backed evidence or clearly reports that Grafana is unavailable.
6. The worklist shows real job status rather than seeded placeholder rows.
7. The backend health endpoint returns successfully.
8. The browser origin is included in backend CORS configuration.

The public submission must use a hosted URL where the judge can observe the actual running product. A local Replit development preview is useful for rehearsal but is not a substitute for the hosted project URL required by Devpost.
