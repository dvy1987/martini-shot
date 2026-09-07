# Current State

**Where:** 2026-09-07 — Ingest **job** is file check only. Scene understanding is the **ingest ADK agent** (first after a healthy upload): `ingested` + `spoken_words` + `scene` on the shot, every later agent, and the handoff. Handoff validator restores lost metadata or runs the look, then writes `handoff_orchestrator_note`. Other stations are not kicked off together.
**In flight:** owner asked to commit and push the dirty tree (this ingest work plus D-10/loudness/inspect from the parallel thread). `make check` coverage still below 90%.
**Next queue:** coverage on untested Stage 1a modules; do not treat Veo-finished eval rows as Omni passes.
**Full handover:** `docs/memory/agent-handoffs.md` (2026-09-07 20:41).
