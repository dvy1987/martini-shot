# ADR-0005: Temporal video perception for QC agents; stabilize-then-regenerate repair ladder

Date: 2026-09-09 | Status: Accepted | Amends: — | Supersedes: —
Evidence: owner planted-defect run on `show-0370ff6800d6` (shaky-cam shot 4, shot-a715b15e1559), 2026-09-09

## Context

The owner uploaded a deliberately shaky handheld clip (shot 4 of the diner
project) to test whether the finishing agents would notice camera work that
does not belong with the rest of the film and repair or regenerate it. The
pipeline failed the test:

- **Perception gap.** Every inspect/vision agent sees at most 3 still PNG
  frames extracted by `clip_preview.py` (plus WAV audio for audio stations).
  Camera shake is motion BETWEEN frames; 3 stills of a seated diner dialogue
  are identical whether the camera is locked-off or being juggled. The
  `camera_language` agent even evaluated the shot and reported "locked-off
  framing… stable composition." It was not deceived — it was blind.
- **Naming gap.** The only instrument that actually watches the video (the
  deterministic flicker meter) tripped twice (`flicker_spike_breach`,
  `coverage_flicker_breach`), but reported "flicker", not "unmotivated
  instability / wrong camera language" — so no repair branch the house knows
  how to run was proposed, and a human accepted the clip without the system
  ever stating the real defect.
- **Ladder gap.** Even a correctly named camera defect has no rung: the
  retry state machine (`stations/pickups/retry.py`, MAX_RETRIES = 2) only
  knows "strengthen anchors and re-repair", then give up to needs_human.
  Whole-clip regeneration is not a nameable outcome anywhere.

Plumbing fact: `run_agent_call` (H-1a, the single instrumented call site)
already attaches media as inline `Part.from_bytes(data, mime_type)` — video
bytes are one mime type away, and the pinned reasoning model
(`gemini-3.7-flash`, ADR-0002) understands video natively. The 3-frame cap
was a cost choice, not a model limitation.

## Decision

1. **Temporal judges watch real video.** `camera_language`, pickups QC
   (`pickups_vision_qc`), and `extend` receive the clip's actual mp4 bytes
   as an inline video part instead of 3 stills. Frame-level stations
   (corrections, relight, delivery, coverage look) keep stills. Draft-tier
   clips are 360p, so the inline bytes stay small.
2. **Repair ladder (stabilize first, regenerate on failure):**
   - Retries 0–1: stabilize/strengthen (existing pickups repair).
   - After the 2nd failed stabilize: regenerate the WHOLE clip (Omni, using
     the accepted references/stills as subject references), draft-tier,
     alternate-only per house law.
   - Up to **5** total attempts (MAX_RETRIES 2 → 5): 2 stabilize + 3
     regenerate; only then `needs_human`.
3. **Camera defect bucket.** The `camera_language` finishing prompt gains a
   defect outcome: unstable/unmotivated camera relative to house style →
   `needs_work`, `kind=defect`, proposing stabilization (pickups) — so the
   shake is NAMED, not merely measured.

## Alternatives Considered

- **Give ALL visual agents full video.** Strongest perception, but ~8
  specialists × full-video tokens per shot multiplies the bill for agents
  whose judgments (signage, lighting, framing) are frame-level anyway.
  Rejected: cost without perceptual benefit (owner chose temporal-only).
- **Regenerate immediately on camera defect, skip stabilization.** Faster to
  a clean clip, but discards an accepted performance and burns a generative
  render on what a deterministic/cheap stabilize might fix. Rejected:
  draft-first + spend discipline (C-6.4, A5) — owner chose stabilize first.
- **Keep stills, add a numeric shake meter only.** Cheap, but the meter
  repeats the flicker lesson: a number without a named defect still produces
  no repair branch, and agents remain unable to judge "appropriate camera
  work" — the owner's actual test. Rejected.

## Consequences

- ✓ Motion defects (shake, jitter, unstable handheld) become visible AND
  nameable; the owner's planted-defect test becomes a catchable case.
- ✓ Repair ladder is bounded (5 attempts) but no longer gives up after 2.
- ✓ Cost rises only where temporality matters (3 stations); token metering
  and C-4.4 cost spans already cover the larger media parts unchanged.
- Tradeoff: inline video raises per-call latency/size for those agents;
  the 300 s call bound stays.
- Tradeoff: the flicker/spike gates may re-flag regenerated takes — the QC
  loop, not the agent, adjudicates; needs_human remains the honest floor.
- Eval obligation (C-3): the planted shaky clip becomes the stability
  dataset row with a numeric bar BEFORE the agent change is trusted;
  JSONL evidence under `docs/evidence/`.
