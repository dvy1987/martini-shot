# D-10 — Conversational Corrections (Omni edit, approval-tracked alternates)

## Sequencing

Owner ruling 2026-09-07: finish one Stage 1a feature with live EDD before
starting the next. This is that first feature. E-1 Relight does not start
until this evidence stands.

## Judgment eval: PASS — 1.0 / 1.0 / 1.0 (≥ 0.8)

Live `gemini-3.7-flash` Corrections Agent on 6 labeled briefs × 3 runs.
Hard gates in code (empty intent, locked cut, prompt-injection) coerce
abstention. Gate: `corrections_judgment` mean_case_accuracy ≥ 0.8.

Green artifact: `corrections_judgment_summary_20260907T071558Z.json` (+ matching
JSONL). An earlier unstamped run (0.667 / 1.0 / 0.667) is kept: the model
sometimes emitted `"agent": "Corrections"` and the parser rejected it. The
parser now accepts display-cased agent names; the miss is not hidden.

## Quality eval: PASS — 9/9 Omni edits, mean flicker 0.00303 < 0.02

End-to-end for each of 3 synthetic holdouts × 3 runs (real services, no
mocks): shot doc → H-0 `correct_shot` proposed → approved → worker Omni
`edit` (`gemini-omni-1.1-flash-preview`) → GCS → flicker QC 0.02 → DRAFT
alternate `op=correction` (AL-1; never an overwrite).

Green artifact: `corrections_quality_summary_20260907T075342Z.json`.

| Run | Shot | Flicker | QC | Model |
|---|---|---|---|---|
| 1 | synthetic-drift-01 | 0.00397 | pass | Omni |
| 1 | synthetic-drift-02 | 0.00752 | pass | Omni |
| 1 | synthetic-mark-03 | 0.00013 | pass | Omni |
| 2 | synthetic-drift-01 | 0.00265 | pass | Omni |
| 2 | synthetic-drift-02 | 0.00533 | pass | Omni |
| 2 | synthetic-mark-03 | 0.00016 | pass | Omni |
| 3 | synthetic-drift-01 | 0.00193 | pass | Omni |
| 3 | synthetic-drift-02 | 0.00536 | pass | Omni |
| 3 | synthetic-mark-03 | 0.00019 | pass | Omni |

max flicker 0.00752. Every alternate is `draft` / `correction`.

### What failed honestly (kept in this directory)

- System Python `google-genai` 1.67 rejected `enterprise=True`. Product
  client now uses `vertexai=True` (same as the text path) plus a 900s HTTP
  timeout — the SDK default 120s aborted a live edit write.
- Natural BBB `shot-02-grove` / `shot-03-clearing` Omni `edit` recitation
  refusals (same content-dependent refusal D-9 recorded). No Veo `edit`
  fallback exists; the quality suite moved to labeled synthetic INPUT.
- ffmpeg `testsrc2` also recited. Gradient-family synthetics render.

## Input fixtures (C-1.3)

- `probes720/synthetic-drift-01-720p.mp4` — D-9 gradient scene.
- `probes720/synthetic-drift-02-720p.mp4` — `ffmpeg -f lavfi -i "gradients=s=1280x720:speed=0.05:nb_colors=6:duration=8:rate=30"`.
- `probes720/synthetic-mark-03-720p.mp4` — same family plus a red box
  (`drawbox=x=100:y=400:w=80:h=80`) as a bounded removal target.

## Spend (C-7.2)

Judgment ~$0.07. Green quality batch 9 × 360p drafts ≈ **$2.10**. Earlier
failed/recited attempts billed $0 (refusals) or a couple of extra successful
drift drafts while isolating the holdout set. All batches printed under $5.

## Product path

Manual + agent: Alternates lane Corrections form → `POST /api/v1/shots/{id}/correct`
→ Approvals inbox → `cor-<approval_id>` job → draft alternate with flicker.
Locked cuts blocked in UI, API (409), agent hard gate, and H-0 locked-target guard.
