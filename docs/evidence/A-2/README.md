# A-2 Evidence — GCS + Firestore wrappers (plan task A-2, orchestrator-led TDD)

Date: 2026-08-30 · RED observed (both test modules failed collection with `ModuleNotFoundError` after moving implementations aside), then GREEN against REAL services (C-6.2, zero mocks).

## DoD verification
| DoD item | Result |
|---|---|
| Integration test: create/upload/download/delete REAL objects in dev bucket | `tests/test_gcs_integration.py::test_upload_download_delete_roundtrip` — PASS against `gs://martini-shot-media` (US) |
| REAL signed download URL | V4 GET URL via IAM signBlob impersonation (`GCS_SIGNING_SA` = default compute SA); user-account ADC has no private key, so dev signing is remote — no key files anywhere (C-5.1). Cloud Run signs with its attached SA automatically. |
| Integration test: temp doc create/read/delete in REAL Firestore | `tests/test_firestore_integration.py::test_set_get_delete_temp_doc` — PASS on default Native DB (created this session: nam5, firestore-native) |
| Missing doc → None (typed absence) | PASS |

## Infrastructure created this session (all owner-account, free tier)
- Firestore database `(default)`, type Native, location nam5 (queue backbone for A-3).
- `iamcredentials.googleapis.com` enabled (signBlob).
- IAM: `roles/iam.serviceAccountTokenCreator` for dvy1126@gmail.com on `175691725802-compute@developer.gserviceaccount.com` (V4 URL signing via impersonation).
- Local `.env` additions (gitignored): `GCS_BUCKET=martini-shot-media`, `GCS_SIGNING_SA=…compute@developer.gserviceaccount.com`. `.env.example` got the name-only entry.

## Notes
- Config now accepts `GOOGLE_CLOUD_PROJECT` as an alias for `GCP_PROJECT_ID` (first name wins) — matches the owner's existing dev env.
- `pytest.ini` registers the `integration` marker; unit runs can skip real-service tests with `-m "not integration"` once suites grow.
