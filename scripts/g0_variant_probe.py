#!/usr/bin/env python
"""G0 variant probe: bisect the Omni media-request shape that 404s.

Each variant is a real interactions.create with the spike's video inline.
Spacing avoids the per-minute quota. Success = completed interaction with
output video (saved as evidence). Writes docs/evidence/G0/variant_probe.json.
Usage: .venv/Scripts/python.exe scripts/g0_variant_probe.py
"""

from __future__ import annotations

import base64
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "G0"
SHOT = ROOT / "fixtures" / "spike" / "shot-01-meadow.mp4"
PROMPT = "Replace the background environment with a rainy neon-lit city street at night. Keep the subject, its motion, and the camera movement exactly the same. Keep everything else the same."

RESPONSE_FORMAT = {
    "type": "video",
    "resolution": "360p",
    "duration": "8s",
    "delivery": "inline",
}

VARIANTS = [
    {
        "name": "minimal_plus_response_format",
        "kwargs": {
            "model": "gemini-omni-1.1-flash-preview",
            "input": [
                {"type": "text", "text": PROMPT},
                {"type": "video", "data": None, "mime_type": "video/mp4"},
            ],
            "response_modalities": ["video"],
            "response_format": RESPONSE_FORMAT,
            "timeout": 900,
        },
    },
    {
        "name": "pure_minimal",
        "kwargs": {
            "model": "gemini-omni-1.1-flash-preview",
            "input": [
                {"type": "text", "text": PROMPT},
                {"type": "video", "data": None, "mime_type": "video/mp4"},
            ],
            "response_modalities": ["video"],
            "timeout": 900,
        },
    },
]


def main() -> int:
    from google import genai

    video_b64 = base64.b64encode(SHOT.read_bytes()).decode("ascii")
    client = genai.Client(enterprise=True, project="martini-shot", location="global")

    results: dict[str, object] = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "variants": [],
    }
    for index, variant in enumerate(VARIANTS):
        if index > 0:
            print("  spacing 90s for per-minute quota...", flush=True)
            time.sleep(90)
        kwargs = dict(variant["kwargs"])  # type: ignore[arg-type]
        input_parts = kwargs["input"]
        input_parts[1]["data"] = video_b64  # type: ignore[index]
        name = str(variant["name"])
        print(f"[{name}] calling...", flush=True)
        entry: dict[str, object] = {"name": name}
        try:
            create_kwargs = {**kwargs}
            if "api_version" in variant:
                interaction = client.interactions.create(
                    api_version=variant["api_version"], **create_kwargs
                )
            else:
                interaction = client.interactions.create(**create_kwargs)
            entry["status"] = str(getattr(interaction, "status", "unknown"))
            entry["id"] = getattr(interaction, "id", None)
            output_video = getattr(interaction, "output_video", None)
            if output_video is not None:
                entry["has_output_video"] = True
                data = getattr(output_video, "data", None)
                uri = getattr(output_video, "uri", None)
                if isinstance(data, (bytes, bytearray)) and data:
                    out_path = EVIDENCE_DIR / "outputs" / f"variant-{name}.mp4"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(bytes(data))
                    entry["saved_to"] = str(out_path.relative_to(ROOT))
                elif isinstance(data, str) and data:
                    out_path = EVIDENCE_DIR / "outputs" / f"variant-{name}.mp4"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        out_path.write_bytes(base64.b64decode(data))
                        entry["saved_to"] = str(out_path.relative_to(ROOT))
                    except Exception:
                        entry["data_is_string_not_b64"] = True
                elif uri:
                    entry["output_uri"] = str(uri)[:160]
        except Exception as exc:
            entry["error"] = str(exc)[:300]
        results["variants"].append(entry)  # type: ignore[union-attr]
        print(entry, flush=True)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE_DIR / "variant_probe.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
