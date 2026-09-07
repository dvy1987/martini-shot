# D-9 — Extend (Omni primary / Veo product fallback)

**Product:** Omni first. If Omni fails, Veo finishes the job. That is
correct. Jobs record `render_model` / `omni_fallback` / `omni_error`.

**Eval:** generating a new original clip is a **dev-only** way to get a fair
tape when Omni refuses public-domain footage. A Veo-finished eval row is not
an Omni pass.

## Owner EDD 2026-09-07 — 3 original shots, Omni draft then Omni master: PASS

Fair tapes (kitchen cooks, florist tulips, café sign). Each shot: H-0
`extend_shot` (360p draft, job `ext-<id>`) then `render_master` `op=extend`
(720p, job `mst-ext-<id>`). All six renders were Omni. No Veo fallback.
Mean flicker 0.0052 &lt; 0.02. `omni_render_rate` 1.0.

Evidence: `extend_omni_station_20260907T091031Z.json`, `extend_eval.jsonl`,
`extend_eval_summary.json`. Cost ≈ **$2.80** (C-7.2, under $5).

| Shot | Draft flicker | Master flicker | Draft cost | Master cost |
|---|---|---|---|---|
| Kitchen cooks | 0.01039 | 0.01185 | $0.23 | $0.70 |
| Florist tulips | 0.00369 | 0.00386 | $0.23 | $0.70 |
| Café sign | 0.00071 | 0.00069 | $0.23 | $0.70 |

Florist source frames (hands arranging yellow tulips; shears on the bench
then mid-snip) are in `frames/florist-first.jpg` and `frames/florist-mid.jpg`.

## Owner live-action eval 2026-09-07 — Omni extend of cooks at work: PASS

Omni wrote an 8s kitchen scene (two cooks chopping and stirring). First two
D-9 extend attempts died on a 120s Google HTTP write timeout (not recitation;
told to owner; not a Veo pass). After the client timeout fix, the real D-9
station extended that same clip on Omni: 18.0s output, flicker 0.01049,
`omni_fallback=false`. Evidence: `omni_live_action_20260907T085341Z.json`.

| Scene | Omni made the start | Station extend | Flicker | QC |
|---|---|---|---|---|
| Kitchen cooks | yes | Omni | 0.01049 | pass |

## Owner station eval 2026-09-07 — Omni on a new original clip: PASS

Omni wrote a new florist scene, then the real D-9 station (H-0 → worker →
flicker → draft alternate) extended it on Omni. No Veo fallback.

Evidence: `extend_omni_station_20260907T081720Z.json`.

| Scene | Omni made the start | Station extend model | Flicker | QC |
|---|---|---|---|---|
| Florist tulips | yes | Omni | 0.0034 | pass |

## Owner probe 2026-09-07 — Omni extend on original clips: PASS (2/2)

We did **not** use Big Buck Bunny or color-bar clips. Omni wrote two new
café scenes from a short script, then Omni **extended** both. No Veo
backup on the extend step.

Evidence: `omni_original_extend_20260907T080221Z.json`.

| Scene | Omni made the start clip | Omni extended it |
|---|---|---|
| Cafe sign | yes | yes |
| Table with cup | yes | yes |

The older eval below still mixed a fake gradient (Omni) with rabbit-movie
shots that Omni refused and Veo finished. That older table is not the
owner's accepted proof.

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
