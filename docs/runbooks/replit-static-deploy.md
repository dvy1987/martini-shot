# Replit static deploy — Martini Shot frontend

Present these settings to the owner. **Do not deploy until they approve.** Deployment is an owner action.

This is the same `frontend/` app they already fine-tune on Replit. Static hosting only changes how the built files are served — not the product.

## What to set

| Setting | Value |
|---|---|
| Build command | `cd frontend && npm ci && npm run build` |
| Publish / serve folder | `frontend/dist` |
| SPA / rewrites | On — unknown paths (`/approvals`, `/reports`, deep links) must serve `index.html` |
| Node | 20 (matches `.replit`) |

## Environment (baked at build time)

Replit must inject these **before** `npm run build`. They are compiled into the JS bundle (`VITE_*`). Changing them later requires a rebuild.

- `VITE_API_BASE_URL` — Cloud Run backend origin, no trailing slash (example: `https://….run.app`)
- `VITE_API_KEY` — the same read key the backend expects as `X-API-Key`

Do not paste secrets into the repo. Keep them in Replit Secrets.

## CORS

The backend allow-list must include the Replit URL that will serve this build (the `replit.app` / `repl.co` origin). If the SPA origin is missing, the board will truthfully show unreachable/empty — that is correct, not a reason to add fake data.

## After owner approval

1. Set the two `VITE_*` secrets.
2. Enable static deployment with the table above.
3. Confirm `/`, `/approvals`, and `/reports` load without a 404 on refresh.
4. Confirm the connection pill goes Live when the backend is up, and Offline when it is not.

Until that approval, keep using the existing Replit **dev** workflow (`npm run dev` on port 5000) for visual fine-tuning.
