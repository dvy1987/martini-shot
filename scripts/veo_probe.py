#!/usr/bin/env python
"""Probe which Veo model + location combo is callable on martini-shot.

Tries each (model, location) pair with a minimal 4s text-to-video request.
A 404/403 fails fast and costs nothing; the first ACCEPTED combo starts a
real render (owner-approved). Writes docs/evidence/G0/veo_probe.json.
Usage: .venv/Scripts/python.exe scripts/veo_probe.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "G0"
COMBOS = [
    ("veo-3.1-generate-preview", "global"),
    ("veo-3.1-generate-preview", "us-central1"),
    ("veo-3.1-fast-generate-preview", "us-central1"),
    ("veo-3.1-fast-generate-preview", "global"),
    ("veo-3.0-generate-001", "us-central1"),
    ("veo-2.0-generate-001", "us-central1"),
]


def main() -> int:
    from google import genai

    results: dict[str, object] = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "combos": [],
    }
    accepted = None
    for model, location in COMBOS:
        client = genai.Client(
            enterprise=True, project="martini-shot", location=location
        )
        entry: dict[str, object] = {"model": model, "location": location}
        try:
            op = client.models.generate_videos(
                model=model,
                prompt="A red balloon floating upward against a plain white sky, static camera, 4 seconds.",
                config={"number_of_videos": 1, "duration_seconds": 4},
            )
            entry["status"] = "accepted"
            entry["operation_name"] = str(getattr(op, "name", ""))[:120]
            accepted = (client, model, location, op)
        except Exception as exc:  # noqa: BLE001 - probe records failures verbatim
            err = str(exc)
            entry["error_code"] = next(
                (c for c in ["404", "403", "429", "400"] if c in err[:200]), "other"
            )
            entry["error"] = err[:220]
        results["combos"].append(entry)  # type: ignore[union-attr]
        print(entry, flush=True)
        if accepted:
            break

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "veo_probe.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    if accepted:
        client, model, location, op = accepted
        print(f"POLLING {model} @ {location}...", flush=True)
        deadline = datetime.now(tz=timezone.utc).timestamp() + 600
        while not getattr(op, "done", False):
            if datetime.now(tz=timezone.utc).timestamp() > deadline:
                print("TIMEOUT waiting for Veo operation", flush=True)
                return 2
            time.sleep(10)
            op = client.operations.get(op)
        samples = op.response.generate_video_response.generated_samples
        out_dir = EVIDENCE_DIR / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for sample in samples:
            uri = getattr(sample.video, "uri", None)
            if uri:
                import urllib.request

                data = urllib.request.urlopen(uri, timeout=120).read()
                name = f"veo-probe-{len(saved)}.mp4"
                (out_dir / name).write_bytes(data)
                saved.append(name)
        print(f"SAVED OUTPUTS: {saved}", flush=True)
        return 0
    print("NO VEO COMBO ACCEPTED", flush=True)
    return 1


if __name__ == "__main__":
    import time

    sys.exit(main())
