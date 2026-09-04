# D-9 — Extend (Omni primary / Veo fallback, approval-tracked alternates)

## EDD eval: PASS — 3/3 renders, mean_output_flicker 0.00465 < 0.02 (2026-09-04 evening)

End-to-end for each of 3 shots (real services, no mocks): shot doc → H-0
approval proposed → approved (`extend_shot`, deterministic job id
`ext-<approval_id>`) → real worker path (claim → execute → persist → Grafana
annotation) → GCS store → deterministic flicker QC gate → recorded as a
DRAFT alternate (AL-1; never an overwrite). Evidence:
`extend_eval.jsonl` + `extend_eval_summary.json` (suite `extend_quality`,
thresholds.yaml). Renders in `docs/evidence/G0/outputs/…`/pc-alternates via
signed-media API.

| Shot | Render model | Flicker | QC |
|---|---|---|---|
| synthetic-drift-01 | **Omni** `gemini-omni-1.1-flash-preview` | 0.00048 | pass |
| shot-02-grove | **Veo** `veo-3.1-fast-generate-001` | 0.00712 | pass |
| shot-03-clearing | **Veo** `veo-3.1-fast-generate-001` | 0.00634 | pass |

`render_model` is recorded on every job doc and proves the fallback lived:
Omni's evening `recitation` refusals turned out to be CONTENT-dependent —
the synthetic gradient scene still rendered on Omni while the natural-content
fixtures were refused; the station degraded to real Veo renders rather than
failing the job (A5 model-fallback rule, decision log 2026-09-04).

## Veo fallback contract (proven 2026-09-04, probe JSON in this dir)

- Surface: `predictLongRunning` + `fetchPredictOperation` on
  `veo-3.1-fast-generate-001` @ global (the Interactions API does not serve
  Veo).
- `video_extension` feature: input video MUST be ≥720p, duration exactly 7s,
  `video.mimeType` required. Output returns inline base64 (or GCS URI).
- Cost metering unchanged (integer micros; 7s → 700_000 micros at the 720p
  table).

## Input fixtures (C-1.3: labeled synthetic INPUT)

- `fixtures/tmp/shot-02-grove-720p.mp4`, `shot-03-clearing-720p.mp4` — real
  ffmpeg lanczos upscales (1280x720) of the `fixtures/spike` inputs; Veo
  rejects sub-720p extension sources ("Unsupported video height 358").
- `fixtures/tmp/synthetic-drift-01-720p.mp4` — fully synthetic scene:
  `ffmpeg -f lavfi -i "gradients=s=1280x720:speed=0.02:nb_colors=4:duration=8:rate=30" -c:v libx264 -crf 18 -pix_fmt yuv420p`.
  Replaces shot-01-meadow, which trips Veo's third-party content filter
  ("interests of third-party content providers") — recorded, not hidden.

## Spent on this eval (C-7.2, all ≤$5 envelope)

3 Veo extension renders + 1 Omni render (7s drafts) ≈ **$2.80**; earlier
refused attempts (Omni recitation ×5, Veo validation errors ×3) rendered
nothing and cost $0.
