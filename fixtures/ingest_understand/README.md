# fixtures/ingest_understand — labeled INPUT for ingest watch evals (C-1.3)

Clips are **built at eval time**, not committed as generated QC:

- Speech rows: real Chirp 3 HD speaks a known line, ffmpeg muxes it onto a
  color field / black frame.
- Silent / tone rows: color bars, solid color, or a sine beep — no spoken
  words.
- `fixtures/g1/slate.mp4` is reused as a testsrc picture (not a spoken line).

Do not treat eval muxes as locked cuts or station output.
