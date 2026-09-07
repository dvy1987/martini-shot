# Corrections station (D-10)

**Capability:** Bounded Omni conversational edits (signage/text/element
replacement) through the audited pipeline — Corrections Agent judges the
brief → H-0 `correct_shot` (deterministic job id `cor-<approval_id>`) →
lease-queue Omni `edit` render → flicker QC gate (0.02) → DRAFT **alternate**
(AL-1). Locked cuts, empty briefs, and prompt-injection text abstain in code.

**Model:** `gemini-omni-1.1-flash-preview` via `omni_edit` (`video_config.task`
= `edit`). The Corrections Agent (`gemini-3.7-flash`, thinking HIGH) proposes
or abstains; it never executes.

**Manual UX:** Season Timeline → Alternates lane → Corrections form (brief,
protected subjects, continuity constraints, source URI) → Approvals inbox.

**Cost:** draft-first integer micros (360p table unless `tier=master`).

**Watch items:**
- Natural-content BBB fixtures (`shot-02-grove`, `shot-03-clearing`) recitation-
  refuse Omni `edit` (same content-dependent refusal D-9 recorded). There is
  no Veo edit fallback. Quality EDD uses labeled synthetic INPUT.
- Omni HTTP timeout must be 900s; the SDK default 120s aborts long edits.

**Eval:** `scripts/corrections_judgment_eval.py` and
`scripts/corrections_quality_eval.py`; evidence in `docs/evidence/D-10/`.
Judgment **1.0/1.0/1.0**; quality **9/9**, mean flicker **0.00303** < 0.02.
