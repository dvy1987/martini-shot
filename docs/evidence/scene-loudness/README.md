# Scene-aware loudness — live EDD

Gate `scene_loudness_judgment` mean_case_accuracy >= 0.8.

| Run | Accuracy | Hits | Pass |
|-----|----------|------|------|
| 1 | 1.000 | 8/8 | yes |
| 2 | 0.875 | 7/8 | yes |
| 3 | 0.875 | 7/8 | yes |

**Pass.** Real Gemini listen, cost **$0.13**. No canned scores.

Honest miss: `scene-05` on runs 2 and 3 classified **explosion** correctly but said `accept` because integrated −16 matched the old TV target. A bang at talk level must be mixed **louder**. Hard gate added in `parse_strategy_decision` (`_coerce_event_at_talk_level`). The station already mixes toward the scene target even if the agent says accept — the meter vs scene target wins.
