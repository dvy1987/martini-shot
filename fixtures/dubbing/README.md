# Dub-eval source fixtures (E-2 / AC-S4.1) — labeled synthetic INPUT (C-1.3)

Real Chirp 3 HD TTS renders (2026-09-06, `scripts/make_dub_fixtures.py`,
$0.012 total). Each file is the SOURCE-language segment the dub eval measures
against — committed INPUT media, never a faked QC output.

| File | Content | Duration |
|---|---|---|
| seg-01-source.wav | "Welcome to Martini Shot, the post-production cockpit." | 3000ms |
| seg-02-source.wav | "Spend control watched the retry loop all night long." | 3480ms |
| seg-03-source.wav | "Take three, episode one." | 2680ms |
| seg-04-source.wav | "The morning report cites the spend control lines with the corresponding evidence." | 4600ms |
| seg-05-source.wav | "Intake paused at the dubbing station." | 2200ms |
| seg-06-source.wav | "The continuity agent approved adding the dub to continuity." | 4360ms |

Dataset: `backend/evals/datasets/dub_qc.jsonl` (6 segments × 3 languages,
es-ES / fr-FR / de-DE, incl. 4 labeled truncation probes). Gates:
`thresholds.yaml` → `dub_timing` (duration-delta MAE ≤ 45 ms, spec S4),
`dub_truncation_recall` ≥ 0.9.
