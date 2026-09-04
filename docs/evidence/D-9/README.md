# D-9 — Extend (Omni scene-extend through the audited pipeline)

## Status 2026-09-04 (evening): pipeline COMPLETE, EDD render eval BLOCKED service-side

## What is built and verified (all green)

- **Thin adapter** `backend/core/generative.py` — Omni on the Vertex Agent
  Platform Interactions API (proven shape: gs:// media + `video_config.task`,
  no `response_format`), docs-simple prompt builder, real price-table cost
  estimator (integer micros, C-6.4). TDD: `tests/test_extend.py`.
- **Station** `backend/stations/extend/` — real worker path (claim → execute
  → persist → Grafana annotation), GCS store, deterministic flicker gate
  (0.02), renders recorded as DRAFT alternates (AL-1), breaching drafts
  flagged `needs_human` with scores attached. Dispatch-registered.
- **Executor command** `extend_shot` (fast lane, fail-closed idempotent:
  deterministic job id `ext-<approval_id>`; queue.submit swallows
  duplicates) — registered on the H-0 default registry and in the
  specialists' allowed command vocabulary.
- **API**: `POST /shots/{id}/extend` (propose), `GET /alternates/{id}/media`
  (real GCS V4 signed URLs, no public buckets).
- **Integration proof (real Firestore + GCS + H-0)**: propose → approve →
  deterministic `extend` job enqueued (5/5 in tests/test_extend.py incl. the
  re-drive idempotency path).
- **thresholds.yaml**: `extend_quality` suite (mean_output_flicker < 0.02;
  9 suites valid).

## The blocker (recorded, not hidden)

Omni video on Vertex began refusing at ~20:30 with `code: recitation` on
**inputs and prompts that had completed at 13:35 the same day** (evidence:
`docs/evidence/G0/outputs/G0-scene-extend-omni-01.mp4` from 13:35 vs the
20:29 probe re-run failing). The exact proven probe path fails too, and a
rephrased prompt fails identically → service-side refusal wave, not a
pipeline defect. Veo fallback attempted: the Interactions API does not serve
`veo-3.1-fast-generate-001` ("Unsupported model interaction") — a Veo path
needs its own API surface, unproven for extend.

**Cost of the failed attempts:** 3 eval renders + 2 probes refused before
billing (400s do not render) — $0 spent on the refusals.

## Next

Re-run `scripts/extend_eval.py` (proposal→approval→render→QC→annotate on 3
fresh shots, ~$2.10) when Omni recovers; then the FE alternates lane.
