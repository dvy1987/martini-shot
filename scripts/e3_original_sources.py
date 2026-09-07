#!/usr/bin/env python
"""Replace the E-3 320x180 ffmpeg stubs with one REAL Omni original clip.

The eight episode objects stay at gs://…/e3/ep-0N.mp4 so the already-queued
jobs keep working. If Omni refuses a prompt as ownership/infringement, try
the next original prompt. Never silent Veo. Never color bars.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings, reset_settings
from backend.core.footage import (
    OwnershipRefusal,
    estimate_original_clip_cost_micros,
    generate_original_clip_with_retries,
)
from backend.core.gcs import get_gcs

EVIDENCE = ROOT / "docs" / "evidence" / "E-3"


def main() -> int:
    reset_settings()
    settings = get_settings()
    estimate = estimate_original_clip_cost_micros()
    print(
        f"estimated_cost_micros={estimate} (~${estimate / 1_000_000:.2f}) "
        "for 1 Omni original clip copied to e3/ep-01..ep-08",
        flush=True,
    )
    try:
        made = generate_original_clip_with_retries(settings)
    except OwnershipRefusal as exc:
        print(
            "STOPPED. Omni treated every original prompt as copied material.",
            flush=True,
        )
        print(str(exc)[:500], flush=True)
        print("Not switching to Veo. Not using the ffmpeg stub clips.", flush=True)
        return 1
    gcs = get_gcs(settings)
    keys = [f"e3/ep-{i:02d}.mp4" for i in range(1, 9)]
    for key in keys:
        gcs.upload_bytes(key, made["video_bytes"], content_type="video/mp4")
        print(f"uploaded gs://{settings.gcs_bucket}/{key}", flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record = {
        "pass": True,
        "model": made["model"],
        "prompt": made["prompt"],
        "interaction_id": made["interaction_id"],
        "bytes": len(made["video_bytes"]),
        "cost_estimate_micros": made["cost_estimate_micros"],
        "keys": keys,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / f"original_source_{stamp}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("pass", "model", "bytes")}, indent=2))
    print(f"evidence {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
