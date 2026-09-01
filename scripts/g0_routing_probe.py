#!/usr/bin/env python
"""G0 routing probe: find where gemini-omni-1.1-flash-preview serves interactions.

Text-only minimal interactions per candidate location (no media, near-zero
cost). Records which (location, model) pairs return 200 vs 404/400.
Writes docs/evidence/G0/routing_probe.json.
Usage: .venv/Scripts/python.exe scripts/g0_routing_probe.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "G0"
CANDIDATE_LOCATIONS = ["global", "us-central1", "us", "europe-west1", "asia-southeast1"]
MODELS = ["gemini-omni-1.1-flash-preview", "gemini-3.7-flash"]


def main() -> int:
    from google import genai

    results: dict[str, object] = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "matrix": [],
    }
    any_ok = False
    for location in CANDIDATE_LOCATIONS:
        for model in MODELS:
            entry: dict[str, object] = {"location": location, "model": model}
            try:
                client = genai.Client(
                    enterprise=True, project="martini-shot", location=location
                )
                interaction = client.interactions.create(
                    model=model,
                    input="Reply with exactly: routing OK",
                    timeout=60,
                )
                entry["status"] = str(getattr(interaction, "status", "unknown"))
                entry["reply"] = str(getattr(interaction, "output_text", ""))[:60]
                if entry["status"] == "completed":
                    any_ok = True
            except Exception as exc:
                entry["error"] = str(exc)[:220]
            results["matrix"].append(entry)  # type: ignore[union-attr]
            print(entry, flush=True)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE_DIR / "routing_probe.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
