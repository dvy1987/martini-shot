# Teardown Runbook — post-demo shutdown

Run ONLY after: demo video recorded from the live product (G5 rule),
submission confirmed ≥24 h before deadline, and owner says go.

Order matters: record proof first, then delete.

## 1. Freeze evidence
- [ ] Demo video recorded + saved locally (NOT only in cloud storage).
- [ ] Grafana dashboards/screenshots exported to `docs/evidence/`.
- [ ] `docs/evidence/` fully committed and pushed.

## 2. Delete billable compute
```
gcloud run services delete martini-shot-backend --project martini-shot --region us-central1 --quiet
```

## 3. Empty and delete storage bucket(s)
```
gcloud storage rm --recursive gs://martini-shot-media --project martini-shot
```
(Firestore data below first if you want a local export of job history.)

## 4. Firestore (free tier, but clean anyway)
- [ ] Delete `martini-shot` Firestore data via console (jobs/, projects/).

## 5. Secrets
- [ ] Delete Secret Manager entries: `gcloud secrets delete <name> --project martini-shot`

## 6. Disable paid APIs (leaves the project inert)
```
gcloud services disable texttospeech.googleapis.com aiplatform.googleapis.com run.googleapis.com --project martini-shot
```

## 7. Keep (free, harmless)
- Billing account + budget alert (needed if anything re-deploys).
- ADC credentials on the dev machine (delete via
  `gcloud auth application-default revoke` if desired).
- The `martini-shot` project itself.

## Owner sign-off
- [ ] Owner confirms teardown complete and budget shows ~$0 sustained.
