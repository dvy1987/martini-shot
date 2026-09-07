# fixtures/e3_batch — E-3 batch demo seed (C-1.3 labeled INPUT)

The batch manifest for the E-3 demo run: 8 episodes x 3 target languages
(es-ES, fr-FR, de-DE) = 24 dub items, each expanded by the Batch
Orchestrator (A10-2) into the deterministic chain ingest → dub → loudness →
delivery (or an agent-trimmed subsequence, validated as a subsequence only).

## Manifest semantics
- `approved: false` — flipping it to true is the OWNER's C-7.2 sign-off on
  the billable run. The orchestrator refuses to plan an unapproved manifest.
- `source_ref` objects are uploaded to the project GCS bucket from
  `source/` at seed time (real objects, real bucket — C-1.1).
- Scripts are short demo lines per language: the cockpit dubs the line, not
  the whole episode (draft-first, C-7.1).

## Dry-run
`python scripts/e3_dry_run.py` loads the manifest through the REAL
`load_manifest` gate, expands items, and prints the REAL
`estimate_batch_cost` (TTS per-char + agent judgments) BEFORE any billable
run. The printout is archived to `docs/evidence/E-3/`.
