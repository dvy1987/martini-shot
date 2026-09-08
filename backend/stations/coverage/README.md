# Coverage (D-12)

**Walk-away finishing:** `finish_coverage` watches the clip (and neighbor
shots) and picks one bucket: **must** (audience cannot tell where we are →
defect), **nice** (extra insert/OTS/reverse for a two-shot or hands-at-work),
or **leave** (a wide that already tells us where we are → `status=ok`,
no job). Must/nice name an angle
(`reverse_angle`, `close_up`, `wide_establishing`, `over_the_shoulder`,
`insert`) and use **this clip as the subject reference**. Do not wait for a
human to pre-fill stills.

**Capability:** Omni `edit` through H-0 `generate_coverage` (job id
`cov-<approval_id>`) → draft alternate, flicker 0.02. Omni edit takes
**exactly one input video** — the source clip is the subject reference.
Neighbor stills may attach as images; extra mp4s are not sent.

**Model:** Omni primary. No Veo edit fallback. Eval must not pass on
gradients or Veo-as-Omni.

**Manual UX:** Alternates lane → Coverage form (clip is the reference).

**Eval:** `scripts/finishing_inspect_eval.py --stations coverage` and
`scripts/stage1a_quality_eval.py --station coverage`.
