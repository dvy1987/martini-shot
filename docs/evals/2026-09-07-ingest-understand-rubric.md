# Evaluation Rubric: Ingest scene understanding

## Purpose
Score the ingest watch: spoken words from the original soundtrack, and a short description of what is happening. Supports shipping the ingest agent and catching regressions. Decisions: keep / revise prompt / do not stamp shot metadata.

## Applicable to
LLM judge is the ingest agent itself (one Gemini watch). Deterministic scorers apply the hit rules below. Humans may audit evidence JSONL.

## Hard Gates (pass/fail)
| Gate | Pass condition | Fail condition |
|---|---|---|
| File-first | Understanding runs only after the file opens, decodes, and has an audio track | Gemini called on a quarantined / corrupt / mute-container file |
| No invented speech | When the clip has no spoken words, `has_speech` is false and `spoken_words` is empty | Any transcribed sentence on a silent / tone-only clip |
| Format | JSON with `spoken_words`, `has_speech`, `scene` | Missing fields or non-string scene |
| Grounding | Words claimed must be hearable on the soundtrack | Dialogue invented from the picture alone |

## Quality Dimensions
### Transcript fidelity: Did it write down what was said?
| Score | Description |
|---|---|
| 5 | Every expected content word is present; no extra invented clauses |
| 3 | Core line is recognizable; minor function-word drift |
| 1 | Wrong language, dropped half the line, or a different sentence |
**Fail condition:** Silent clip with any spoken_words. Live hit rule: all expected `words` appear in the transcript (case-insensitive).

**Edge cases:** A test tone is not speech. Whispered real words still count as speech. On-screen text that is not spoken must not become `spoken_words`.

### Scene grounding: Does the description match what is on camera?
| Score | Description |
|---|---|
| 5 | Names the visible situation (color field, test pattern, people, place) without a conflicting story |
| 3 | Mostly right; extra atmosphere that does not contradict the picture |
| 1 | Describes a different scene (e.g. “two people in a cafe” on a solid blue frame) |
**Fail condition:** Empty scene string. Live hit rule: every `scene_keywords` token appears in the description.

**Edge cases:** A color-bar / testsrc clip should mention a test pattern, bars, or synthetic/color field — not a dramatic narrative. A speech-on-blue clip must still describe the picture, not only quote the line.

### Completeness: Both fields, one watch
| Score | Description |
|---|---|
| 5 | Both transcript decision and scene description are usable as shot metadata |
| 3 | One field is weak but both are present |
| 1 | One field missing or refused without `needs_human` |
**Edge cases:** No spoken words is complete if `has_speech` is false and scene is still filled.

## Scoring Rules
Dimensions are independent. Any hard-gate failure is a miss (score 0) for that case. Live suite hit = transcript rule AND scene-keyword rule AND has_speech match. Do not average a fluent wrong transcript with a pretty description.

## Calibration Notes
Pilot: 8 labeled INPUT clips (speech via real Chirp, silence/tone, testsrc/blue pictures). Known-bad is the silent clip: the agent must not invent a line. Judge model is the same Gemini 3.7 Flash watch used in production (multimodal audio + frames); scoring is deterministic against the label sheet, not a second LLM.
