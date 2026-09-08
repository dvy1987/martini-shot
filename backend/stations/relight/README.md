# Relight Studio (E-1)

**Walk-away finishing:** `finish_relight` watches the clip and picks one
bucket: **must** (unreadable faces or lighting that jumps → defect),
**nice** (prettier lamp when faces are already readable → low improvement),
or **leave** (lighting already matches → `status=ok`, no job). Must/nice
name a preset (`practical_lamp`, `ambient_daylight`, `overhead_ceiling`,
`noir`) and a 360p **draft** alternate. Leave-it never reaches the
orchestrator. The looker names the preset from the picture — a filled brief
is not the intelligence.

**Capability:** Omni `edit` through H-0 `relight_shot` (job id
`rlt-<approval_id>`) → lease-queue → flicker QC 0.02 → DRAFT alternate.
Locked cuts refuse. Unknown presets abstain in the H-0 agent.

**Model:** `gemini-omni-1.1-flash-preview` via `omni_edit`. There is no Veo
edit fallback. If Omni cannot be called during eval, stop and tell the
owner. Product jobs still record `render_model`.

**Manual UX:** Season Timeline → Alternates lane → Relight Studio presets.

**Eval:** `scripts/finishing_inspect_eval.py --stations relight` (must / nice
/ leave on original tape) and
`scripts/stage1a_quality_eval.py --station relight` (Omni drafts).
