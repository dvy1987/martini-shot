# Spike Fixtures — Big Buck Bunny shots (G0 quality spike input)

Source: Big Buck Bunny (2008), Blender Foundation, CC-BY 3.0 — public
availability verified via download.blender.org/peach. Downloaded 2026-08-28
as `BigBuckBunny_640x360.m4v.zip` (121,284,117 bytes), extracted, cut with
ffmpeg 9.0.1 (`crop=640:358` to satisfy even-height encoding; source is an
anamorphic 640x359).

These are REAL footage inputs for the G0 generative quality spike
(background-swap + scene-extension). They are INPUT fixtures only (C-1.3):
no generated or simulated output is committed here.

| File | Source offset | Duration | Scene content |
|------|---------------|----------|---------------|
| `shot-01-meadow.mp4`   | 00:00:30 | 12 s | Opening meadow, butterfly flight, camera follow |
| `shot-02-grove.mp4`    | 00:03:00 | 12 s | Grove dialogue scene, two characters, static-ish framing |
| `shot-03-clearing.mp4` | 00:07:30 | 12 s | Clearing action beat, faster motion, background detail |

All three: 640x358, h264 (CRF 18), AAC audio, ~24 fps. Locked-cut rules:
these shots are treated as immutable inputs; every generative output is an
ALTERNATE (never overwrites).
