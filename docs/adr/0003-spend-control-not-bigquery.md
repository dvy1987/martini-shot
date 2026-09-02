# ADR 0003: Spend Control acts on Firestore job micros, not BigQuery billing export

Date: 2026-09-02 | Status: Accepted | Deciders: owner (product ruling) + agent (architecture)

## Context

Stage 1 must stop runaway station jobs and budget breaches **while the lease
queue is running**. Money is stored as integer micro-units on job documents
(C-6.4). Spec S5b defines Spend Control as a station that **acts** on
`cost_micros` (throttle / stop / approve) and writes Grafana annotations via
MCP.

A stale handover listed “ledger reconcile vs BigQuery export” (M8) as if that
were the money product. The approved spec, plan task D-7, and constitution C-7
do not name BigQuery as the control plane. Owner confirmed 2026-09-02: this is
a product decision, not an accidental omission of BQ.

## Decision

- **System of record for live spend enforcement:** Firestore `pc-jobs.cost_micros`
  plus YAML policies in `backend/stations/spend/`.
- **Act path:** pause intake (`pc-control`), open a Spend approval, annotate
  Grafana through MCP. Incidents are best-effort (this Grafana Cloud org has
  returned FK errors on `create_incident`; do not fake them).
- **BigQuery:** not used for live throttle. A Billing-export → BQ reconcile
  may be added later as **audit**, never as a replacement for S5b.

## Alternatives Considered

- **GCP Billing export into BigQuery as the live brain.** Rejected: export lag;
  invoice grain ≠ job/station grain; cannot pause the lease queue in seconds;
  not on the Grafana-track demo path.
- **Local JSONL ledger only** (`docs/evidence/spend/ledger.jsonl`). Rejected as
  the product: that file is G0 spike evidence, not runtime control.
- **Prometheus/Grafana as sole enforcer** (alert only, no station). Rejected:
  C-4 alerts are the audit trail and the 80% budget warning (H-4); they do not
  pause Firestore intake. Spend Control still has to act.

## Consequences

- Agents must not open a “build BQ spend” task from the stale M8 handover.
- H-4 still owes `pc_*` daily spend metric + Grafana alert at 80% of budget
  (C-7.1). That is dashboards-as-code, not a warehouse cutover.
- Cue-sheet ledger matching (spec S6) remains Stage 2 and is a different
  “ledger.”
- Revisit: owner asks for invoice-truth, or a spec amendment names BQ as Stage 1.

## References

- Spec S5b · constitution C-6.4, C-7.1/.2 · plan D-7 · `backend/stations/spend/`
- Product decision: `docs/memory/decision-log.md` (2026-09-02)
- Gate G2: `docs/evidence/G2/` (40× runaway throttled)
