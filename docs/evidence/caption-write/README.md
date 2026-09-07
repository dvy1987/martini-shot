# Caption writer — live EDD

Gate `caption_write_judgment` mean_case_accuracy >= 0.8.

| Run | Accuracy | Hits | Pass |
|-----|----------|------|------|
| 1 | 0.875 | 7/8 | yes |
| 2 | 0.875 | 7/8 | yes |
| 3 | 0.875 | 7/8 | yes |

**Pass.** Real Gemini, cost **$0.11**. No canned scores.

Honest miss: `write-06` (empty script, no audio) — the model still said `write`. Hard gate added: no script and no audio → `needs_human`, no Gemini call. Delivery never invents lines.
