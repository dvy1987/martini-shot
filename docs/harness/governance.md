# Governance (harness v0)

## Forbidden paths (never write/commit)
- `.env`, `.env.*` (except `.env.example` files), any secret, token, service-account JSON
- Secret-scan exclusions are limited to `docs/harness/manifest.json` + `docs/knowledge-graph/` (generated artifacts containing sha256 file hashes only — reviewed, no credentials); any other exclusion needs owner approval
- `docs/evidence/` — append-only audit trail (C-3.5); never rewrite gate evidence
- `fixtures/` — inputs only with per-file README (C-1.3); never hold product logic there
- destructive git ops without explicit ask; force-push to main

## Allowed write scopes (per executing agent)
- `backend/**`, `frontend/src/**`, `scripts/**`, `tests/**`, station + eval dirs per plan task
- `docs/adr/`, `docs/harness/runs/` (new run dirs), `docs/memory/**`, `docs/skill-outputs/`
- `docs/harness/` only via harness skills, manifest drift rules apply

## Verifier sandbox rules (for any harness-evolution agent)
- May NOT disable or weaken: `make check`, integrity grep, eval thresholds, pre-commit hooks
- May NOT swap AI vendors (C-2.1), add mock layers (C-1.*), or raise spend budgets (C-7.*)
- May NOT edit: task definitions, eval oracles, held-out sets, this governance file, `docs/harness/manifest.json` statuses
- `docs/harness/runs/` is analysis-only during evolution; new run dirs are the only write

## Constitution precedence
Any conflict: `docs/constitution.md` > spec > plan > AGENTS.md convenience. Violations are CRITICAL findings (Integrity Charter A2 protocol).
