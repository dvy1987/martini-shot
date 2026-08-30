# A-1 Evidence — core spine (plan task A-1, orchestrator-led TDD)

Date: 2026-08-30 · Built by orchestrator after worker lane demotion (A6 protocol; see `docs/memory/session-log.md`).

## DoD verification
| DoD item | Result |
|---|---|
| Config precedence unit tests (env > dotenv > default) | 6 tests in `tests/test_config.py` — GREEN |
| OTel init with REAL exporter classes (no mock exporters) | `tests/test_otel.py` asserts `OTLPSpanExporter`/`OTLPMetricExporter` types; loopback staging endpoint (no network in tests) — GREEN |
| Wired into FastAPI app factory | `backend/api/app.py` (`create_app`); entrypoint `backend/api/main.py` |
| C-5.3 error middleware (A7 clause) | `backend/core/errors.py` + `tests/test_errors.py`: unhandled exception → `{"error":{"code":"internal_error"}}`, no exception text/stack/env leakage — GREEN |
| Model IDs centralized (ADR 0002) | `backend/core/models.py`; `tests/test_models.py` greps the whole backend tree for stray IDs — GREEN |
| Structured logging (C-4.2 fields) | `backend/core/logging.py`; JSON lines, UTC `ts`, `job_id`/`station`/`project_id` surface — GREEN |
| Auth C-5.2 | ASGI key gate, health exempt; unset key fails closed (tested); CORS allowlist exact-match (tested) |
| RED observed (not claimed) | `red-pytest.txt`: all 5 new test modules failed collection (`ModuleNotFoundError`) before implementation existed |

## Full gate (orchestrator run, final state)
```
ruff check         All checks passed!
ruff format        28 files already formatted
mypy backend       Success: no issues found in 11 source files
pytest tests       27 passed (RED→GREEN)
eval-check         OK (no suites yet — Phase 2)
integrity          no mocks/stubs in product code (C-1.2 clean)
harness-check      no drift across 8 components
```

## Notes
- Test-driven bug catch: CSV CORS parsing initially didn't strip spaces — caught by RED-first test, fixed in `config.py`.
- `tests/test_smoke.py::test_no_env_file_committed` (pre-existing F-3 test) checked the filesystem and failed on the owner's local gitignored `.env`; corrected to check the git index with `*.example` templates exempted.
- OTel logs exporter wrapped in ImportError guard (SDK layout shifted across OTel 1.39–1.42); traces/metrics always init.
- Known test-run noise: BatchSpan/Log processors retry the loopback staging endpoint (`127.0.0.1:4318`) after the test process ends — stderr noise only, zero failures.
- Coverage tooling not yet wired (C-3.2 ≥90% enforcement): tracked for A-3 followup, `pytest-cov` to be added with the queue slice.
