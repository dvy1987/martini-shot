# Extend station (D-9)

**Capability:** Omni scene-extend through the full audited pipeline —
H-0 proposal→approval (`extend_shot`, deterministic job id `ext-<approval_id>`)
→ lease-queue render (async, C-6.5) → GCS store → deterministic flicker QC
gate (0.02) → the render is recorded as a DRAFT **alternate** (AL-1) — never
an overwrite of any cut. Breaching drafts land as `needs_human` with their
scores attached, so the evidence trail shows what was spent on them.

**Model:** `gemini-omni-1.1-flash-preview` (Omni primary; `veo-3.1-fast-generate-001`
fallback — see `backend/core/models.py`). Proven call shape: gs:// media URI +
`generation_config.video_config.task`, no `response_format` (the G0/Omni-probe
finding). Prompts follow the docs' simple style (elaborate prompts cause
generation refusals).

**Real services:** Vertex Agent Platform (Omni), GCS, Firestore, Grafana
annotations (via the H-0 approval transition + the worker's `annotate_job`).

**Cost:** draft-first, integer micros (`estimate_extend_cost_micros`: ~$0.10/s
at 720p, ~1/3 at 360p, ceil per second — Vertex bills per output second).

**Watch items:**
- 2026-09-04 ~20:30 Vertex began refusing Omni video ops with `recitation`
  on inputs+prompts that had completed at 13:35 the same day (service-side;
  the exact proven probe path fails too). The pipeline is unaffected; the
  D-9 EDD eval (`scripts/extend_eval.py`) re-runs when Omni recovers. Veo
  fallback note: the Interactions API does not serve `veo-3.1-fast-generate-001`
  — a Veo fallback needs the `generate_videos`/predictLongRunning surface,
  whose extend (video-input) support is unproven for the pinned -001 ID.
- Specialists (H-1) may propose `extend_shot`; the central locked-target
  guard (AL-1) refuses it on LOCKED shots — unlock first (approval-tracked).
