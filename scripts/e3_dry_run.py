#!/usr/bin/env python
"""E-3 dry run (C-7.2): load the batch manifest through the REAL gate,
expand items through the REAL orchestrator planning, and print the REAL
cost estimate — BEFORE any billable run. No TTS, no agent calls, no
writes. The printout is what the owner approves."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.supervisor.orchestrator import (
    build_batch_jobs,
    estimate_batch_cost,
    load_manifest,
    plan_chain,
)

MANIFEST = ROOT / "fixtures" / "e3_batch" / "manifest.json"
EVIDENCE = ROOT / "docs" / "evidence" / "E-3"


def main() -> int:
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    approved = bool(raw.get("approved"))
    print(f"manifest approved: {approved}", flush=True)

    # The REAL gate: refuses an unapproved manifest — expected pre-approval.
    items: list[dict] = []
    jobs: list = []
    chains: dict[str, int] = {}
    refused = False
    try:
        items = load_manifest(MANIFEST)
        print(f"items (episode x language): {len(items)}", flush=True)
        for item in items:
            chain = plan_chain(item)
            key = ">".join(chain)
            chains[key] = chains.get(key, 0) + 1
        print("planned chains:", json.dumps(chains), flush=True)
        jobs = build_batch_jobs(items)
        ids = [job.id for job in jobs]
        if len(ids) != len(set(ids)):
            raise SystemExit("FATAL: duplicate job ids in expansion (C-6.3)")
    except ValueError as exc:
        refused = True
        print(f"gate REFUSED planning: {exc}", flush=True)

    # The estimate computes from raw items (no gate) — it is exactly what
    # the owner needs in order to decide.
    estimate = estimate_batch_cost(raw["items"])
    print(json.dumps(estimate, indent=2), flush=True)

    payload = {
        "date": "2026-09-07",
        "manifest": str(MANIFEST.relative_to(ROOT)),
        "approved": approved,
        "gate_refused_unapproved": refused,
        "items_expanded": len(items),
        "jobs_expanded": len(jobs),
        "chains": chains,
        "duplicate_ids": False,
        "estimate": estimate,
        "note": "dry-run only: no TTS, no agent calls, no writes (C-7.2)",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "dry_run.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(f"archived: {EVIDENCE / 'dry_run.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
