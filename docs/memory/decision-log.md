# Decision Log

## 2026-09-02 - Hosted MCP OAuth deferred to post-sprint; hackathon ships OSS + SA token
Status: active
Scope: project
Confidence: high
Tags: mcp, oauth, f4, auth, deferral

### Decision
The hackathon submission ships **OSS mcp-grafana + service-account token only** (`MCP_MODE=oss`, live-proven at B-2/B-2b). Hosted Grafana MCP OAuth (browser login + saved token persistence, plan F-4) is deferred to **post-hackathon work, ordered LAST** in the parked backlog (tasks file, "PARKED — post-sprint backlog").

### Context
Owner ruling 2026-09-02. F-4 rated a one-way door in the handover model plan (implementing auth wrong is the danger; deferring it is safe). OSS path is the demo-critical route with live round-trip evidence; hosted OAuth adds nothing judge-visible. Six days to deadline; G3/demo-batch/rehearsal take priority.

### Consequences
- Before J-3 (hosting rehearsal): add an honest "OSS-only MCP auth" line to README limitations (J-4).
- SA token is a demo single point of failure: keep the regeneration runbook (`docs/plans/2026-09-01-post-command-handover.md` §2) handy through J-6.
- Deferral does not burn the door: F-4 remains implementable post-sprint unchanged.

### Revisit When
- Post-hackathon (or if Grafana-track judging requires hosted-MCP usage — verify track rules before assuming so).
- SA token rotation becomes operationally painful.

## 2026-09-02 - Spend Control is live queue action, not a BigQuery billing warehouse
Status: active
Scope: project
Confidence: high
Tags: spend, s5b, c-7, bigquery, grafana, product

### Decision
Stage 1 money control is the **Spend Control station** (S5b): it reads integer `cost_micros` on Firestore job documents and **acts** (pause intake, Approvals inbox, Grafana annotation). GCP **BigQuery billing export is not** the live spend brain. A later BQ reconcile may be added as audit, not as a replacement.

### Context
2026-09-02, after Gate G2. Owner asked whether building Spend Control instead of “leveraging BigQuery” was a product/feature difference. A stale agent handover (M8) had listed “ledger reconcile vs BQ export.” Approved spec S5b and constitution C-6.4 / C-7 never named BigQuery as the control plane. Hackathon rules mention BigQuery ML only as an allowed Google AI tool.

### Rationale
A runaway station can re-queue in seconds. The brake has to sit on the same Firestore lease queue the worker uses. Billing export into BigQuery is delayed warehouse data: good for “did our micros match the invoice?”, useless for pausing intake in time. Grafana-track demo also needs the act + annotation on the job, not a warehouse query.

### Alternatives Considered
- **Live control via BigQuery / Billing export:** rejected for Stage 1. Latency and the wrong system of record (invoice vs job).
- **Spend Control on `pc-jobs.cost_micros` (spec S5b):** accepted. Already implemented (`backend/stations/spend/`, Gate G2 throttled a 40× runaway).
- **BQ billing export as a later reconcile layer:** deferred. Optional audit after billable Dub/TTS exists; does not replace the station.
- **JSONL-only ledger (`docs/evidence/spend/ledger.jsonl`):** rejected as the product. That file is G0 spike cost evidence, not runtime control.
- **Cue-sheet “ledger matching” (spec S6):** not this decision. Stage 2 music licenses.

### Revisit When
- Owner wants invoice-truth vs `cost_micros` (add BQ export **on top**, do not rip out S5b).
- GCP Billing export lag is proven short enough for a control loop (unlikely; still ask before swapping systems of record).
- Daily spend Grafana alert at 80% of budget (C-7.1 / task H-4) is implemented — that is metric+alert, still not BQ.
- Spec/plan amendment names BigQuery as a Stage 1 requirement.

### Consequences
- Next agents must not treat handover M8 as an open product gap.
- `cost_micros` on jobs remains the system of record for throttle/stop/approve.
- C-7.1 80% Grafana alert is still owed at H-4; that does not reopen BigQuery as the live brain.
- ADR: `docs/adr/0003-spend-control-not-bigquery.md`.
