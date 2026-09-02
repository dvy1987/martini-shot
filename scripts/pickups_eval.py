#!/usr/bin/env python
"""Pickups flicker eval on labeled INPUT (D-5, C-3.3). No Veo calls.

Prints aggregate cost (always $0 on this path) so C-7.2 is vacuously satisfied.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.core.media import FFmpeg
from backend.stations.pickups.flicker import flicker_score

DATASET = ROOT / "backend" / "evals" / "datasets" / "pickups.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "D-5"
THRESHOLD = 0.18


def _clip_path(row: dict, media: FFmpeg, derived: Path) -> Path | None:
    path = row.get("path")
    if path:
        full = ROOT / str(path)
        return full if full.is_file() else None
    source = ROOT / str(row.get("source") or "")
    if not source.is_file():
        return None
    start = float(row.get("start_s") or 0)
    duration = float(row.get("duration_s") or 2)
    out = derived / f"{row['id']}.mp4"
    if out.is_file():
        return out
    import subprocess

    result = subprocess.run(
        [
            media.ffmpeg_bin,
            "-v",
            "error",
            "-y",
            "-ss",
            str(start),
            "-i",
            str(source),
            "-t",
            str(duration),
            "-c",
            "copy",
            str(out),
        ],
        capture_output=True,
        check=False,
    )
    return out if result.returncode == 0 and out.is_file() else None


def main() -> int:
    settings = get_settings()
    media = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
    derived = ROOT / "fixtures" / "pickups" / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print("pickups eval estimated cost: $0.00 (identity flicker, no generate)")
    records = []
    scores = []
    for row in rows:
        clip = _clip_path(row, media, derived)
        if clip is None:
            records.append({"id": row.get("id"), "ok": False, "error": "missing input"})
            continue
        score = flicker_score(clip, media.ffmpeg_bin)
        records.append(
            {"id": row.get("id"), "path": str(clip.relative_to(ROOT)), **score}
        )
        if score.get("ok"):
            scores.append(float(score["flicker_score"]))
    mean = sum(scores) / len(scores) if scores else None
    payload = {
        "suite": "pickups_flicker",
        "threshold": THRESHOLD,
        "mean_flicker_score": mean,
        "n": len(scores),
        "pass": mean is not None and mean < THRESHOLD,
        "records": records,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: payload[k] for k in ("mean_flicker_score", "n", "pass")}, indent=2
        )
    )
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
