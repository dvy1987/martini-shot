# Eval Interface (harness v0 — stub)

Regression interface for agent harness evolution. v0 = minimal; components earn their place via measured rollouts (route improvements via `harness-evolution`).

## Regression command
`make check` — lint + typecheck + tests + eval-check + integrity + harness-check. Must pass (exit 0) before any harness change is promoted.

## Task splits
- Held-in: `docs/harness/tasks.json` `split: held-in` — harness may be tuned against these.
- Held-out: `split: held-out` — never tune on these; edited only by owner-approved amendment.

## Pass metric & thresholds
- Primary: pass@1 per task (0/1), reported as aggregate %.
- Rollouts per task: k=2 minimum once `harness-evolution` runs (v0: k=1 smoke).
- Promotion threshold: a harness change promotes only if held-in 100% pass AND held-out does not regress vs previous manifest version.

## Environment bootstrap (for meta-agents)
```
Stack: Python 3.12 target (dev 3.13), FastAPI/ADK backend; React+Vite+TS frontend (scaffold pending)
Commands: test=[python -m pytest tests -q] lint=[make lint] gate=[make check]
Git: branch=main (confirm clean state at session start)
Skills: 123 in .agents/skills + global install yes
Platforms: Droid (AGENTS.md), Cursor (.cursor/rules/*.mdc)
```

## Product evals (distinct from harness evals)
Product EDD suites live in `backend/evals/` (datasets, metrics, `thresholds.yaml`) per constitution C-3.3/.4 — those gate FEATURES; this interface gates the AGENT HARNESS. Do not conflate the two.
