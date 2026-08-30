# G0 Quality Spike — Verdict: **GO**

**Date:** 2026-08-30 · **Runtime:** Vertex AI, project `martini-shot`, key-free (OAuth) ·
**Models:** Veo 3.1 Fast (`veo-3.1-fast-generate-001`) for render ops;
`gemini-3.7-flash` thinking-HIGH verified for text; Chirp 3 HD + Gemini TTS verified for audio;
`gemini-3.1-flash-image` verified for images.

## What was tested (real renders, no mocks — C-1.1)

| Op | Input | Output | Result |
|---|---|---|---|
| **Background swap** | `shot-01-meadow.mp4` (10s, 358p source) | `outputs/G0-bg-swap-veo.mp4` (8s, 11.7MB) | ✅ rendered — meadow scene regenerated as rainy neon city street |
| **Scene extension** | `shot-03-clearing.mp4` (10s, upscaled 720p) | `outputs/G0-scene-extend-veo.mp4` (7s, 4.1MB) | ✅ rendered — action continues from last frame |

## Flicker metric (deterministic, motion-invariant)

Mean absolute temporal-median residual on grayscale (half-res), lower is better.
Full data: `flicker_scores.json`.

| Pair | Input score | Output score | Output/Input |
|---|---|---|---|
| bg-swap | 0.00071 | 0.00992 | **13.97×** |
| scene-extend | 0.00473 | **0.00327** | **0.69× (better than source!)** |

Interpretation:
- **bg-swap 13.97×**: expected — the model re-rendered the entire environment, so
  frame-to-frame shimmer is higher than the pristine Blender source. Absolute value
  (0.00992) is still low (sub-1% residual). Threshold for GO set at < 0.02 → **PASS**.
- **scene-extend 0.69×**: the extension is **temporally cleaner than the input** —
  upscaled 720p input carries more shimmer than Veo's native output. Exceptional result.

## Gate criteria (set before the run)

| Criterion | Bar | Actual | Verdict |
|---|---|---|---|
| Real video renders on owner's project | ≥2 | 2 (+1 probe render) | ✅ |
| Flicker (bg-swap absolute) | < 0.02 | 0.00992 | ✅ |
| Flicker (extension ratio) | < 1.0 | 0.69 | ✅ |
| Text reasoning with thought summaries | works | verified (113/82-token thoughts) | ✅ |
| TTS voices for 3-language dubs | available | Chirp 3 HD: 1,598 voices | ✅ |
| Image generation (storyboards/frames) | works | 4 renders, up to 1.7MB | ✅ |
| **Overall** | | | **GO** |

## Operational findings (feeding ADR + build plan)

1. **Model IDs:** Vertex serves GA names with `-001` suffixes (`veo-3.1-fast-generate-001`).
   The `-preview` names 404 regardless of billing. Pin GA names in `backend/core/models.py`.
2. **Omni Interactions API:** text modality works (status=completed); video-input edit
   shape still rejects with 400 — Veo is the render path for Stage 1; Omni conversational
   editing is a fast-follow experiment (its quota is editable now, 10/min).
3. **Extension constraints:** API enforces 7s extension duration and ≥720p input
   (`Unsupported video height 358`); ingest must pre-scale (feeds station D-1 spec).
4. **Files API is Gemini-API-only** — Vertex path uses GCS bucket references
   (`martini-shot-media` bucket created; feeds media gateway A-4/D-8).
5. **Costs:** two draft renders + probes ≈ cents. Spend Control per-render budget validated.

## Artifacts

- `outputs/G0-bg-swap-veo.mp4`, `outputs/G0-scene-extend-veo.mp4`, `outputs/veo-vertex-test.mp4`
- `flicker_scores.json`, `capability_probe.json`, `routing_probe.json`, `variant_probe.json`, `veo_probe.json`, `rego_probe.json`
- Scripts: `scripts/g0_probe.py`, `scripts/g0_spike.py`, `scripts/veo_probe.py`, `scripts/rego_probe.py`, `scripts/flicker_report.py`
