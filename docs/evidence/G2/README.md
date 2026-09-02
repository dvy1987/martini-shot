# Gate G2

Project `g2-6d2d7919`. Ingest, loudness, delivery, pickups, and Spend Control ran through the Firestore lease queue (`scripts/g2_gate.py`).

Spend Control **throttled** a seeded 40× pickups runaway: intake paused for `pickups`, Spend approval opened, Grafana annotation id 35 written. `create_incident` returned a Grafana Cloud FK error (`Counters_orgID_fk`); the hold still landed.

Honest pack results on `fixtures/g1/slate.mp4` (320×240, silent):
- ingest `passed` (checksum + probe)
- loudness `needs_human` (`fail_quiet`, −70 LUFS vs −16)
- delivery `needs_human` (AR 4:3 vs streaming 16:9, plus loudness)
- pickups identity path `passed`
- spend `throttled`
