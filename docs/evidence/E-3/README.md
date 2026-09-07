# E-3 demo batch — live run 2026-09-07

96 jobs (8 episodes × 3 languages × ingest/dub/loudness/delivery). All terminal.

| Station | Passed | Needs human |
|---------|--------|-------------|
| ingest | 24 | 0 |
| dub | 23 | 1 |
| loudness | 0 | 24 |
| delivery | 0 | 24 |

**Billed:** $0.12 (`119908` micros). Real Chirp TTS + Gemini Dub QC. Raw job JSON: `docs/evidence/E-3/raw/jobs/`. Summary: `docs/evidence/E-3/raw/batch_summary.json`.

## Honest outcomes

- **Ingest:** all 24 passed (checksum of the Omni original café clip copied to `gs://martini-shot-media/e3/ep-01.mp4` … `ep-08.mp4`).
- **Dub:** 23/24 passed. Flagged: `cyc-e3-demo-ep-05-fr-FR-dub` — Gemini heard a truncated last word; timing also 5s short of the 8s picture. WAV still stored as an alternate.
- **Loudness:** all 24 `fail_quiet` (~−25 LUFS vs −16). This worker used the **old** measure-only station and metered the **picture** soundtrack, not the dub. Scene-aware mix (hear the dub, pick a fitting level, apply, re-measure) landed after this process started; it did not apply here.
- **Delivery:** all 24 `needs_human` because loudness failed and captions were missing.

First all-failed run (no dub station / GCS key bug) is archived separately as `docs/evidence/E-3/raw/batch_summary_first_run_all_failed.json`.
