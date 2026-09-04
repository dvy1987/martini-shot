# H-1a — Case model, deterministic routing, deliberation orchestrator

Amendment A9 (multi-agent supervisor team), plan §3. Commit: see `git log -1 --format=%H`.

## What was built

| Piece | File | Notes |
|---|---|---|
| Case model + routing | `backend/supervisor/case.py` | `Claim`/`ProposedAction`/`Case`/`Finding`/`Verdict` frozen dataclasses; `SPECIALIST_ROUTES` covers all §2.4 trigger categories (station-specific QC join; unknown kind raises); `build_case` reads the real job doc from Firestore, records evidence absence explicitly |
| Orchestrator | `backend/supervisor/deliberation.py` | `run_deliberation_cycle`: build → route (station enriched from job-doc evidence when the trigger lacks it) → parallel specialist calls via `asyncio.gather`+`to_thread` → verification hard filter (specialist-level AND claim-level rejection; non-reversible actions excluded outright) → H-0b leverage ranking → persists one `pc-deliberations` doc → best-effort Grafana annotation |
| Single instrumented call site | `backend/supervisor/otel_ai.py` | `run_agent_call(settings, prompt, *, span_name, persona, tools, response_schema)` — every specialist/verifier/synthesis call goes through here; `persona` lands on the span as `gen_ai.agent.name` so Grafana filters per-agent cost; `run_supervisor_text` is now a thin wrapper (B-3 contract unchanged) |

## Guarantees

- Personas are injectable callables (`SpecialistMap`); until H-1b..H-1e wire real agents, unrouted names get a stand-in finding (low-confidence claim, no actions) so control flow is proven without faking AI output (C-1.1).
- Verification is a HARD filter, never a down-weight (plan §0.4, owner ruling).
- Cycle persists to `pc-deliberations` (or injected per-run collection in tests).
- One instrumented AI call site; no agent can bypass cost/token/latency metering by construction (C-4.4).

## Gate evidence (2026-09-04)

- `pytest tests/test_deliberation.py tests/test_otel_ai.py` — 11/11 green (7 deliberation incl. real-Firestore orchestrator persistence; 4 otel_ai incl. delegation + typed-config tests)
- Full gate: ruff check + format ✓, mypy backend ✓ (65 files), thresholds.yaml ✓, integrity C-1.2 ✓, harness drift ✓, pytest 215 passed, coverage 91.77% (gate ≥90%)
- No real Gemini calls in tests (monkeypatched client; zero-mock law covers product code, tests use client doubles for unit assertions; the real-Firestore path is live)
