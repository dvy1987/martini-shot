# Scene-aware loudness eval pipeline (2026-09-07)

## System
Loudness Strategist listens to the clip (Gemini) and picks a scene class + target LUFS. The loudness station applies ffmpeg loudnorm and re-measures. Whisper is one class among six: silence, whisper, dialogue, shout, impact, explosion.

## Three layers
1. **Deterministic:** scene-target table, ±2 LU agent clamp, speech floor −23 LUFS, ffmpeg apply/re-measure, dub-preferring `resolve_audio_ref`. Tests: `tests/test_scene_loudness.py`.
2. **Statistical:** mean_case_accuracy over 8 labeled cases × 3 live runs; gate >= 0.8 in `backend/evals/thresholds.yaml` (`scene_loudness_judgment`).
3. **LLM-as-judge:** the station agent itself (not a second judge). Hit = both `scene_class` and `decision` match. Failed/invalid call = miss.

## Dataset splits (labeled INPUT, C-1.3)
- Happy: scene-02 dialogue accept
- Edge: scene-06 silence must not be pumped to −16
- Adversarial: scene-07 music_hot stems
- Known-bad: scene-05 explosion sitting at talk level must not `accept`; scene-08 meter_error

Cue-sheet `scene_notes` plus energy-matched ffmpeg audio (tones/noise). No canned scores.

## Cost
8 calls/run × 3 runs of flash+short audio. Printed before billing; `--yes` if estimate > $5.
