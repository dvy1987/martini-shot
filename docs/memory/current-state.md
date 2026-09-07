# Current State

**Where:** 2026-09-07 — Stage 1 batch plus Stage 1a stations are in the tree. **Ingest now watches the original clip** after the file check and writes `scene_understanding` (spoken words + scene) onto the shot. Live ingest eval: transcript 0.958 / scene 1.00 ($0.08). Scene-aware loudness mixes; captions format the line or ingest words; quiet speech can retry loudness, silence does not.
**In flight:** owner asked to commit and push the full dirty tree. `make check` coverage still below 90%.
**Next queue:** coverage on untested Stage 1a modules; do not treat Veo-finished eval rows as Omni passes.
**Full handover:** `docs/memory/agent-handoffs.md` (2026-09-07 17:40).
