# A-5 Evidence — Handoff Validator, silent mode (plan A-5, AC-S0b.1)

Date: 2026-08-30 · RED observed (ImportError) → GREEN, 8/8.

## DoD verification — AC-S0b.1
| Requirement | Proof |
|---|---|
| manifest-missing-file fixture → transition blocked with reason code | `test_missing_file_blocks_with_reason_code`: `MISSING_FILE` + blocked ref named; also `COUNT_MISMATCH`, `CHECKSUM_MISMATCH`, `MANIFEST_INVALID` codes table-tested |
| complete manifest passes | `test_complete_manifest_passes` (pure) + `test_passing_transition_writes_no_annotation` (real Firestore) |
| annotation written | `test_blocked_transition_writes_annotation_with_job_id` (integration, REAL Firestore `pc-annotations`): doc carries `job_id`, codes, stations, UTC `at`; deleted after verify |
| silent / no UI | pure library module under `backend/jobs/`; no route, no screen |

## Design notes
- Manifest schema v1: `{version, project_id, from_station, to_station, files:[{ref, sha256, bytes}]}` — `sha256_file()` helper matches hashlib (tested on a real fixture).
- Fail-closed: unreadable manifest = `MANIFEST_INVALID` block, never a skip.
- Annotation sink is the real Firestore store (C-4.3 spine record). The Grafana MCP mirror of these annotations lands with B-2 (round-trip evidence there).
- Pure gate usable without a store (`HandoffValidator.without_store()`) for deterministic unit tests — no mocks of GCP anywhere.
