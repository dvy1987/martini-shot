#!/usr/bin/env python
"""Scene-aware loudness eval: real Gemini LISTENS and classifies scene
energy (whisper / talk / shout / crash / explosion / silence), then
chooses the mix path.

Gate (thresholds.yaml): scene_loudness_judgment mean_case_accuracy >= 0.8.
A hit requires BOTH scene_class AND decision. A failed call is a miss
(C-3.5 honest accounting).

Cost: 8 flash+audio calls/run × 3 runs. Printed before billing; --yes if
the estimate exceeds $5 (C-7.2).

Evidence: docs/evidence/scene-loudness/scene_loudness_eval.jsonl + _summary.json.

Labeled synthetic INPUT (C-1.3): ffmpeg tones/noise matching the energy of
each class, plus the cue-sheet scene_notes on the report. Not canned scores.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.core.media import FFmpeg
from backend.supervisor.station_agents.loudness_strategy import (
    decide_loudness_strategy,
)

DATASET = ROOT / "backend" / "evals" / "datasets" / "scene_loudness_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "scene-loudness"
THRESHOLD = 0.8
# Flash + short audio: ~3k micros/call upper bound used only for the C-7.2 print.
ESTIMATE_MICROS_PER_CALL = 4_000


def _energy_wav(media: FFmpeg, scene_class: str) -> tuple[bytes, str] | None:
    """Labeled synthetic INPUT whose energy matches the class (C-1.3)."""
    volume = {
        "silence": -50.0,
        "whisper": -40.0,
        "dialogue": -20.0,
        "shout": -8.0,
        "impact": -4.0,
        "explosion": 0.0,
    }.get(scene_class)
    if volume is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "clip.wav"
        src = (
            "anoisesrc=duration=2.5:color=white"
            if scene_class in {"impact", "explosion"}
            else "sine=frequency=1000:duration=2.5"
        )
        result = media._run(
            [
                media.ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                src,
                "-af",
                f"volume={volume}dB",
                str(path),
            ],
            timeout=30,
        )
        if result.returncode != 0 or not path.exists():
            return None
        return path.read_bytes(), "audio/wav"


def run_suite(run_index: int, media: FFmpeg) -> tuple[list[dict], dict]:
    settings = get_settings()
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records: list[dict] = []
    hits = 0
    cost_micros = 0
    for row in rows:
        score = 0.0
        decision = ""
        scene_class = ""
        reason = "agent call failed"
        expected = row["expected"]
        audio = None
        if expected.get("decision") != "needs_human":
            audio = _energy_wav(media, str(expected.get("scene_class") or "dialogue"))
        try:
            doc, call_cost = decide_loudness_strategy(
                settings,
                report=row["report"],
                season_state=row["season_state"],
                audio=audio,
            )
            decision = doc.decision
            scene_class = str(doc.raw.get("scene_class") or "")
            reason = doc.reason
            cost_micros += int(call_cost)
            score = (
                1.0
                if decision == expected["decision"]
                and scene_class == expected["scene_class"]
                else 0.0
            )
        except Exception as exc:  # honest miss
            reason = f"ERROR {type(exc).__name__}: {exc}"[:200]
        hits += int(score)
        records.append(
            {
                "run": run_index,
                "id": row["id"],
                "expected_decision": expected["decision"],
                "expected_scene_class": expected["scene_class"],
                "decision": decision,
                "scene_class": scene_class,
                "reason": reason[:200],
                "score": score,
            }
        )
        print(
            json.dumps(
                {
                    k: records[-1][k]
                    for k in ("run", "id", "decision", "scene_class", "score")
                }
            ),
            flush=True,
        )
    accuracy = hits / len(rows) if rows else 0.0
    summary = {
        "run": run_index,
        "mean_case_accuracy": round(accuracy, 3),
        "hits": hits,
        "n": len(rows),
        "cost_micros": cost_micros,
        "pass": accuracy >= THRESHOLD,
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    n_lines = sum(
        1 for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    estimate = n_lines * args.runs * ESTIMATE_MICROS_PER_CALL
    estimate_usd = round(estimate / 1_000_000, 4)
    print(
        json.dumps(
            {
                "estimate_micros": estimate,
                "estimate_usd": estimate_usd,
                "cases": n_lines,
                "runs": args.runs,
            }
        ),
        flush=True,
    )
    if estimate_usd > 5 and not args.yes:
        print("batch over $5 requires --yes (C-7.2)", file=sys.stderr)
        return 2

    settings = get_settings()
    media = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
    all_records: list[dict] = []
    summaries: list[dict] = []
    for i in range(1, args.runs + 1):
        print(f"=== scene_loudness_judgment run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i, media)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    billed = sum(int(s.get("cost_micros") or 0) for s in summaries)
    payload = {
        "suite": "scene_loudness_judgment",
        "runs": args.runs,
        "gate": {"threshold": THRESHOLD, "comparison": ">="},
        "per_run": summaries,
        "cost_micros": billed,
        "cost_usd": round(billed / 1_000_000, 4),
        "pass": all(s["pass"] for s in summaries),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "scene_loudness_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "scene_loudness_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
