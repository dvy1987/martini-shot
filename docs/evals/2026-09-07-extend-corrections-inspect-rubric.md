# Evaluation Rubric: D-9 / D-10 inspect looker (must / nice / leave)

## Purpose
Score whether Gemini, watching real frames, stamps the same finishing
bucket a post supervisor would: required work, optional craft, or leave
the shot alone. Supports prompt iteration for `finish_extend` and
`finish_corrections`. Live billed looks only — no vignette that names the
answer.

## Applicable to
LLM inspect agent (`run_inspect` / ADK `look_{station}`). Human labels
the clip before the run. The judge here is **deterministic match** to
those labels (not a second LLM).

## Hard Gates (pass/fail)
| Gate | Pass condition | Fail condition |
|---|---|---|
| Live watch | Frames extracted from original Omni tape (or ffmpeg-carried deficit) | Vignette text, gradients, color bars |
| Schema | `ok` / `needs_work` with legal impact/kind | `empty` on a clip that had frames (attendance hole) |
| Leave-it | `status=ok`, no proposal | Proposing work on a complete/clean clip |
| Known-bad | Unwired coverage stays `empty` | Fake all-good on a missing agent |

## Quality Dimensions
### Bucket: Did it pick must vs nice vs leave?
| Score | Description |
|---|---|
| Pass | `status` + `kind` match the labeled bucket (defect=must, improvement=nice, ok=leave) |
| Fail | Wrong bucket (e.g. mid-cut called taste; complete shot called must) |

### Impact band: Is required work in high/medium and taste in low?
| Score | Description |
|---|---|
| Pass | Exact impact match on the labeled row |
| Fail | Must-extend scored as low; extra air scored as high |

**Edge cases:** A sitting two-shot is leave-it for Extend even if a dolly
would be nice (that is Camera Language). A florist with no bad graphic is
leave-it for Corrections even if lighting could be richer (that is Relight).
A cup on the table is nice, not must, unless it blocks a face.

## Scoring Rules
Each JSONL row is 0 or 1. Suite mean ≥ 0.8 over 3 consecutive live runs.
A gate failure on a row is 0. Do not average impact “close enough.”

## Calibration Notes
2026-09-07 first live inspect run scored 0.75: mid-cut was labeled
`improvement` while Gemini called `defect`. Product truth is **must =
defect**. Extra-air vs complete uses two different originals (full kitchen
vs sitting two-shot), not a one-second trim of the same file.
