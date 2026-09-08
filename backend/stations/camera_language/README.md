# Camera Language (D-16)

**Walk-away finishing:** `finish_camera_language` watches the clip and
picks one bucket: **must** (operator typed a move the picture ignores →
defect), **nice** (action the camera should follow → low improvement),
or **leave** (dialogue two-shots and still lifes stay still → `status=ok`,
no job). Must/nice
name a vocabulary move (`dolly_tracking`, `dolly_zoom`, `handheld_shaky`,
`steadicam`, `whip_pan`, `crash_zoom`, `snorricam`, `locked_off`).

**Capability:** Omni `edit` through H-0 `apply_camera_language` (job id
`cam-<approval_id>`) → draft alternate, flicker 0.02. Reference-style
influence is disclosed when present.

**Model:** Omni primary. No Veo edit fallback. Suggestions on the UI are
model output and say so.

**Manual UX:** Alternates lane → Camera Language chips.

**Eval:** `scripts/finishing_inspect_eval.py --stations camera_language` and
`scripts/stage1a_quality_eval.py --station camera_language`.
