# Current State

**Where:** 2026-09-01 — Track A (A-1..A-5), B-1, B-2 on `main`. Gate **G1 RUN GREEN** (real MP4 →
ingest → Grafana signals → annotation → SSE; evidence `docs/evidence/G1/`). D-1 core (ingest
checksum + lease worker + API spine) and Replit UX Steps 3–6 verified and committed.
**Blocking:** nothing — all gates green at handover (backend 95 tests, FE 63 tests, lint/mypy clean).
**Next queue:** D-1 completion (probe/corruption/quarantine) → sign-in-to-approve (spec §7.2, no
firebase dep yet) → B-3 AI observability → F-4 hosted OAuth (one-way door) → D-2..D-7 + G2 → H-* → J-*.
**Worker lane (A6):** read-only research only; orchestrator builds everything.
**Full handover:** `docs/plans/2026-09-01-post-command-handover.md` (rev 2 — env facts, gotchas, contracts).
**Open:** F-4 OAuth persistence; sparse OTLP counters need range PromQL; FIFO tie-break in queue if
strict ordering is ever needed (ask first); Stage 1a parked behind G3.
