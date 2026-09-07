# Corrections station (D-10)

**Walk-away finishing:** `finish_corrections` watches the clip and picks
one bucket: **must** (wrong signage/graphic → defect), **nice**
(unmotivated prop → improvement), or **leave** (nothing to fix →
`status=ok`, no job). Must/nice name a bounded intent and a 360p **draft**
alternate. Leave-it never reaches the orchestrator bag.

**Capability:** Omni conversational `edit` through the audited pipeline —
Corrections Agent judges the brief (or the looker names the intent) → H-0
`correct_shot` (job id `cor-<approval_id>`) → lease-queue Omni `edit` →
flicker QC 0.02 → DRAFT **alternate** (AL-1). Locked cuts, empty briefs,
and prompt-injection text abstain in code.

**Diverse correction kinds (eval tape):**
- **signage** — original café wooden sign → rewrite to OPEN
- **prop_removal** — original table two-shot → remove the paper cup
- **on_set_graphic** — original chalkboard misspelled OPNN → rewrite to OPEN

Gradient / color-bar / BBB holdouts are **not** a quality pass (owner
2026-09-07). Earlier `synthetic-drift-*` JSONL in this folder is rejected
tape, kept for honesty.

**Model:** `gemini-omni-1.1-flash-preview` via `omni_edit`. There is no Veo
`edit` fallback. If Omni cannot be called, stop and tell the owner. The
job records `render_model`, `omni_fallback`, `omni_error`.

**Manual UX:** Season Timeline → Alternates lane → Corrections form →
Approvals inbox.

**Eval:** `scripts/corrections_judgment_eval.py` (8 labeled briefs: signage,
prop removal, on-set graphic, lettering replace, plus hard-gate abstentions)
and `scripts/corrections_quality_eval.py` (original GCS clips, Omni-only).

Live 2026-09-07 (this thread, original tape, not gradients):
- Judgment **1.0 / 1.0 / 1.0** on 8 briefs × 3 runs
  (`corrections_judgment_summary_20260907T142002Z.json`).
- Quality **3/3 Omni** on one run of three kinds, mean flicker **0.00153**,
  `omni_render_rate` **1.0** (`corrections_quality_summary_20260907T142125Z.json`).
  Signage café-sign 0.00064; prop table-cup 0.00187; chalkboard OPNN 0.00207.
  A 3-consecutive-run quality batch is the remaining DoD bar.

