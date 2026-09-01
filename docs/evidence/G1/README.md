# G1 Evidence — spine truth-check (2026-09-01)

Gate G1 is **GREEN**. Real MP4 → ingest API → Firestore lease worker → SHA-256 → Grafana traces/metrics/logs via MCP → investigation annotation with `job_id` → SSE `queued → running → pass`. The proof path is the API + worker, not a UI intake control.

Artifacts: `gate.json`, `sse.ndjson`. Fixture: `fixtures/g1/slate.mp4` (1s labeled INPUT, C-1.3).

## This run

| Piece | Proof |
|---|---|
| Job | `job-12f1bb8f8b98` · project `g1` · status **pass** |
| Object | GCS `projects/g1/ingest/job-12f1bb8f8b98/slate.mp4` (9509 bytes) |
| Checksum | `202459a82f3c557e08563a5a7d7bfbeecbe024ebfc1d23c3fa15160d14636bb2` |
| Trace ID | `1558b20e2f5b0e99fd29d2dd40627bfd` — Tempo `station.ingest.run`, attribute `pc.job_id` |
| PromQL (range `now-1h`, step 15s) | `pc_job_duration_seconds_count`, `pc_job_cost_micros_count`, `pc_job_outcome_total` — all have samples; outcome series includes `pass=1` after this job |
| Loki | `{service_name="martini-shot-backend"} \|= \`ingest checksum done\`` — one line; labels include `job_id=job-12f1bb8f8b98` and the same `trace_id` |
| Annotation | Grafana id 4, text contains `job_id=job-12f1bb8f8b98`, tags `martini-shot`,`g1`,`ingest`,`job:job-12f1bb8f8b98` |
| SSE | `sse.ndjson`: `job.updated` queued → running → pass, then `annotation.created` |

TraceQL used (MCP `tempo_traceql-search`, not a `search_traces` alias that v1.3.0 does not expose):

```
{ span.pc.job_id = "job-12f1bb8f8b98" }
```

Loki note: `|= \`job-12f1bb8f8b98\`` on the line body returned empty — `job_id` is a **label**, not in the message text. The checksum-done query is the real line.

## How to re-run

API on `:8000` (no `--reload`, so the worker and SSE share one process). Then:

```
python scripts/g1_gate.py
```

That script posts `fixtures/g1/slate.mp4` to `/api/v1/projects/g1/ingest` and records SSE + Grafana evidence. The timeline board shows the job after the fact; it does not invent a “Log a clip” control.

## Pre-flight (2026-08-30)

OTLP write-path only (`scripts/otel_smoke.py`): traces/metrics/logs 2xx. That was transport, not Gate G1. Kept below as history.

| Signal | Outcome |
|---|---|
| traces / metrics / logs | 2xx after signal-path + Basic-auth fixes in `core/otel.py` |

## Security

Browser EventSource cannot send `X-API-Key`, so `/events` accepts `?api_key=`. Uvicorn access logs recorded that query string during this run. Access-log redaction is in `backend/core/logging.py`. **Rotate `POST_COMMAND_API_KEY` and the matching `VITE_API_KEY`** before the next shared session.
