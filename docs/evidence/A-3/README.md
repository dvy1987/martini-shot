# A-3 Evidence — Job model + Firestore lease queue (plan A-3, orchestrator-led TDD)

Date: 2026-08-30 · RED observed (`ModuleNotFoundError: backend.jobs.models` across all three new test modules) → GREEN against real Firestore (C-6.2, zero mocks).

## DoD verification — AC-S0.1
| Requirement | Proof |
|---|---|
| N jobs submitted concurrently execute once each | 3 jobs, 2 live workers draining concurrently — passed; exactly-once proven by a REAL execution ledger (`integration-test-executions` collection, one doc per execution; count == 1 per job) |
| Despite worker crash mid-job | `tests/chaos_worker.py --mode die` spawns a real subprocess that leases then `os._exit(1)` — no complete, no heartbeat |
| Lease expiry reassignment verified | crashed job reassigned after visibility timeout (4 s in test); `attempts == 2` asserted on the reassigned job; dead worker's late `complete()` correctly rejected (owner guard) |
| Real subprocess kill | subprocess spawn + hard exit, no mocks (C-1.2) |

Run logs: `lease_tests_run.txt` (11 passed — models 4 + queue semantics 7) · `chaos_ac_s0_1_run.txt` (1 passed, 65 s).

## Queue semantics verified (real Firestore transactions)
- submit idempotent per job_id (`create()`-based, duplicate submit is a no-op)
- lease claims once; live lease blocks second worker; station filter respected; oldest-first (created_at)
- **complete/fail/heartbeat are owner-guarded inside Firestore transactions** (`@transactional`, re-read + conditional write → no double-lease under contention)
- fail: requeue until max_attempts (2), then `failed` (dead) with error retained
- expired-lease reassignment folded into `lease()` (queued ∪ expired-leased candidates)

## Operational notes
- `Transaction.run()` does not exist in google-cloud-firestore 2.29 — the documented `@firestore.transactional` decorator is used (diag confirmed).
- Tests run in isolated per-run collections (`it-jobs-<uuid>`) with fixture cleanup — the production `pc-jobs` collection stays untouched.
- `conftest.py` added at repo root: makes `backend.*` importable for any pytest invocation.
- Coverage gate wired (C-3.2): `make test` now runs `pytest --cov=backend --cov-fail-under=90`; entrypoint `api/main.py` omitted (uvicorn-only).
