#!/usr/bin/env python
"""Finishing inspect judgment: live Gemini WATCHES labeled clips.

Same path as the product: extract frames + wav, then billed run_inspect.
No vignette that tells the model the answer. Gate >= 0.8, 3 runs.

Owner 2026-09-07: this exam may spend up to $20.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.core.media import get_media
from backend.evals.finish_inspect_media import ensure_inspect_clips
from backend.supervisor.clip_preview import (
    AUDIO_STATIONS,
    VISUAL_STATIONS,
    preview_from_bytes,
)
from backend.supervisor.inspect import empty_note
from backend.supervisor.inspect_impl import run_inspect

DATASET = ROOT / "backend" / "evals" / "datasets" / "finishing_inspect_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "finish-loop"
THRESHOLD = 0.8
OWNER_CAP_MICROS = 20_000_000


def _hit(row: dict, note) -> bool:
    exp = row["expected"]
    if note.status != exp["status"]:
        return False
    if exp.get("impact") and note.impact != exp["impact"]:
        return False
    if exp.get("kind") and note.kind != exp["kind"]:
        return False
    return True


def _parts_for(station: str, payload: bytes, media) -> tuple:
    images, audio, err = preview_from_bytes(media, payload)
    if station == "spend":
        return None, None, ""
    if station not in AUDIO_STATIONS:
        audio = None
    if station not in VISUAL_STATIONS:
        images = []
    return (images or None), audio, err


def run_suite(run_index: int, clips: dict, media, settings) -> tuple[list[dict], dict]:
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records: list[dict] = []
    hits = 0
    cost_micros = 0
    for row in rows:
        station = row["station"]
        note = None
        score = 0.0
        status = ""
        reason = ""
        try:
            if row.get("hard_gate") == "no_agent":
                note = empty_note(station)
            else:
                clip_name = str(row.get("clip") or "")
                path = clips[clip_name]
                payload = path.read_bytes()
                images, audio, err = _parts_for(station, payload, media)
                if station in VISUAL_STATIONS and not images:
                    raise RuntimeError(f"no frames for {clip_name}: {err}")
                if station == "loudness" and audio is None:
                    raise RuntimeError(f"no wav for {clip_name}: {err}")
                note = run_inspect(
                    station,
                    settings=settings,
                    context={
                        "clip_uri": str(path),
                        "eval_id": row["id"],
                        "shot_id": f"eval-{row['id']}",
                        "budget_micros": 50_000_000,
                    },
                    images=images,
                    audio=audio,
                )
                cost_micros += int(note.cost_estimate_micros or 0)
            status = note.status
            reason = note.summary or note.reason
            score = 1.0 if _hit(row, note) else 0.0
        except Exception as exc:
            reason = f"ERROR {type(exc).__name__}: {exc}"[:240]
        hits += int(score)
        records.append(
            {
                "run": run_index,
                "id": row["id"],
                "station": station,
                "expected": row["expected"],
                "status": status,
                "impact": note.impact if note is not None else "",
                "kind": note.kind if note is not None else "",
                "reason": reason[:240],
                "score": score,
            }
        )
        print(
            json.dumps(
                {
                    "run": run_index,
                    "id": row["id"],
                    "score": score,
                    "status": status,
                    "reason": reason[:160],
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
    n_calls = 7 * args.runs
    estimate = 250_000 * n_calls + 50_000
    print(
        f"finishing_inspect_eval estimate {estimate} micros "
        f"(${estimate / 1_000_000:.2f}) live Gemini on real clips; "
        f"owner cap ${OWNER_CAP_MICROS / 1_000_000:.0f}"
    )
    if estimate > OWNER_CAP_MICROS and not args.yes:
        print(
            f"above ${OWNER_CAP_MICROS / 1_000_000:.0f} owner cap — pass --yes",
            file=sys.stderr,
        )
        return 2
    settings = get_settings()
    media = get_media(settings)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    clips = ensure_inspect_clips(settings, media, EVIDENCE / "clips")
    all_records: list[dict] = []
    summaries: list[dict] = []
    for run in range(1, args.runs + 1):
        recs, summary = run_suite(run, clips, media, settings)
        all_records.extend(recs)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    out = EVIDENCE / "inspect_eval.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for rec in all_records:
            handle.write(json.dumps(rec) + "\n")
    (EVIDENCE / "inspect_eval_summary.json").write_text(
        json.dumps({"summaries": summaries}, indent=2), encoding="utf-8"
    )
    return 0 if all(s["pass"] for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
