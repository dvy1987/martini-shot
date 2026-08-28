# Cost Guardrails — martini-shot (owner directive 2026-08-28)

The owner's budget is $50–75 of GCP credits on project `martini-shot`
(billing account `018612-D2E1A2-DBDBF3`). This document is the binding
deploy contract; every deployment/deletion cited here is enforced at
gate G3 (infra review) and re-checked before submission.

| # | Directive | Implementation | Status |
|---|-----------|----------------|--------|
| 1 | Flash first, Pro only for final reasoning | ADR 0002: `gemini-3.7-flash` (thinking HIGH) for ALL text tasks. No Pro model anywhere in the pinning table. Video gen uses Omni/Veo only for actual media renders; draft-first low-res QC loops before any master render (Spend Control throttles). | ✅ ADR 0002 |
| 2 | Scale to zero | Cloud Run services deploy with `--min-instances=0`. Idle = $0. Note: SSE connections hold one instance while a client is connected; bounded by the max-instance cap. | Deploy flags below (G3) |
| 3 | Small + capped instances | Backend deploys with `--cpu=1 --memory=512Mi --max-instances=3`. Frontend is Replit-hosted (not Cloud Run). Media gateway streams/proxies; it does NOT transcode, so 512Mi suffices. | Deploy flags below (G3) |
| 4 | No dedicated/always-on databases | Firestore (serverless, per-op pricing) only. No vector search cluster, no memorystore, no GKE. Vertex endpoints are serverless pay-per-use. | ✅ architecture |
| 5 | Light storage footprint | GCS lifecycle rules at bucket creation (A-4): `tmp/` delete after 1 day; `renders/drafts/` delete after 7 days; `renders/masters/` kept until teardown. Temp artifacts cleaned per-job by the media gateway. | A-4 DoD |
| 6 | Budget alerts | Budget `martini-shot-hackathon-cap` (ID `365d8249-9281-4103-93ed-02c39657a1ad`): $50, alerts at 50/90/100% emailed to billing account admins. Plus app-level Spend Control (C-7): per-job cost ledger in integer micros; eval batches > $5 require explicit `--yes`. | ✅ created 2026-08-28 |
| 7 | Secure endpoints | Spec §7.2: public reads require API key (app-level check); decision writes require Firebase sign-in token; secrets in Secret Manager. No unauthenticated write path exists. | ✅ §7.2 |
| 8 | Turn it off after demo | `docs/runbooks/teardown.md` — full shutdown checklist; demo video recorded BEFORE teardown (G5 rule). | ✅ runbook |

## Deploy contract (applied at G3, verified at G5)

```
gcloud run deploy martini-shot-backend \
  --project martini-shot --region us-central1 \
  --min-instances=0 --max-instances=3 \
  --cpu=1 --memory=512Mi --timeout=300 --concurrency=40 \
  --no-session-affinity
```

Any deviation (more CPU for a render-heavy job, higher cap) is a documented
exception with an owner sign-off — never a silent default.
