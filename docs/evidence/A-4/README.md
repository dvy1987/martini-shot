# A-4 Evidence — ffmpeg/ffprobe wrapper (plan A-4, orchestrator-led TDD)

Date: 2026-08-30 · RED observed (`ModuleNotFoundError: backend.core.media`) → GREEN on real binaries + real fixture media (C-1.1: no shims, no fallback engines).

## DoD verification
| DoD item | Result |
|---|---|
| probe: duration / fps / codec | `tests/test_media.py::test_probe_reports_duration_fps_codec` — real ffprobe JSON parse on `fixtures/spike/shot-01-meadow.mp4` (10 s recut, h264 — bound corrected to match the G0 10-s recuts after live measurement) |
| Round-trip on fixtures | extract @2fps (≥20 PNGs) → reassemble → probe: duration within ±1 frame (0.5 s + 0.05 s tolerance) — **AC-S2.2 part 1** |
| Loudness filter invocation | `ebur128` filter run on real fixture; integrated LUFS parsed (sanity band −70..0) — foundation for D-2 |
| Config wiring | `FFMPEG_BIN`/`FFPROBE_BIN` read through `core/config.py` (fields + env map + constructor) |

## Notes
- All subprocess args are fixed lists from config (no shell interpolation).
- `get_media(settings)` factory mirrors `get_gcs`/`get_firestore` style.
- Full-suite run (44+ tests incl. real-service integration + chaos) green in the A-4 commit's gate; coverage gate stays at `--cov-fail-under=90` (C-3.2).
