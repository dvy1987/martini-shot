# Extend station (D-9)

**Capability:** Omni scene-extend through the full audited pipeline —
H-0 proposal→approval (`extend_shot`, deterministic job id `ext-<approval_id>`)
→ lease-queue render (async, C-6.5) → GCS store → deterministic flicker QC
gate (0.02) → the render is recorded as a DRAFT **alternate** (AL-1) — never
an overwrite of any cut. Breaching drafts land as `needs_human` with their
scores attached, so the evidence trail shows what was spent on them.

**Model:** `gemini-omni-1.1-flash-preview` primary, `veo-3.1-fast-generate-001`
automatic fallback (`backend/core/models.py`; `render_model` is recorded on
every job doc and the eval table in `docs/evidence/D-9/README.md` proves both
paths live). Omni proven call shape: gs:// media URI +
`generation_config.video_config.task`, no `response_format` (the G0/Omni-probe
finding). Prompts follow the docs' simple style (elaborate prompts cause
generation refusals). Veo fallback contract (proven 2026-09-04): the
Interactions API does not serve Veo — use `predictLongRunning` +
`fetchPredictOperation`; `video_extension` requires a ≥720p source, exactly 7s
duration, and `video.mimeType`; output is inline base64 (or GCS URI).

**Real services:** Vertex Agent Platform (Omni), GCS, Firestore, Grafana
annotations (via the H-0 approval transition + the worker's `annotate_job`).

**Cost:** draft-first, integer micros (`estimate_extend_cost_micros`: ~$0.10/s
at 720p, ~1/3 at 360p, ceil per second — Vertex bills per output second).

**Watch items:**
- 2026-09-04 ~20:30 Vertex began refusing Omni video ops with `recitation` on
  natural-content inputs that had completed at 13:35 the same day. The
  refusals are CONTENT-dependent, not a full outage: a fully synthetic
  gradient scene still rendered on Omni during the same window, while the
  natural fixtures degraded to the Veo fallback (both recorded in the 3/3
  eval). `shot-01-meadow` additionally trips Veo's third-party content filter
  and was replaced in the eval by the labeled synthetic fixture (C-1.3).
- Specialists (H-1) may propose `extend_shot`; the central locked-target
  guard (AL-1) refuses it on LOCKED shots — unlock first (approval-tracked).
