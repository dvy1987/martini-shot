#!/usr/bin/env python
"""Finishing inspect judgment: live Gemini WATCHES labeled clips.

Same path as the product: extract frames + wav, then billed run_inspect.
No vignette that tells the model the answer. Gate >= 0.8, 3 runs.

Owner 2026-09-07: this exam may spend up to $20. C-7.2: print; --yes over $5.
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
FIVE_DOLLAR_MICROS = 5_000_000
# Multimodal flash look (frames + JSON). Not the Omni job estimate.
LOOK_ESTIMATE_MICROS = 150_000


def _load_rows() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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


def run_suite(
    run_index: int, clips: dict, media, settings, rows: list[dict]
) -> tuple[list[dict], dict]:
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
                        **dict(row.get("context") or {}),
                    },
                    images=images,
                    audio=audio,
                )
                cost_micros += LOOK_ESTIMATE_MICROS
            status = note.status
            reason = note.summary or note.reason
            score = 1.0 if _hit(row, note) else 0.0
        except Exception as exec_err:
            reason = f"ERROR {type(exec_err).__name__}: {exec_err}"[:240]
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
                    "impact": note.impact if note is not None else "",
                    "kind": note.kind if note is not None else "",
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
    parser.add_argument(
        "--stations",
        default="",
        help="Comma roster filter (e.g. extend,corrections). Default: all rows.",
    )
    args = parser.parse_args()
    rows = _load_rows()
    wanted = {item.strip() for item in args.stations.split(",") if item.strip()}
    if wanted:
        rows = [row for row in rows if row.get("station") in wanted]
        if not rows:
            print(f"no dataset rows for stations={sorted(wanted)}", file=sys.stderr)
            return 2
    billed = [row for row in rows if row.get("hard_gate") != "no_agent"]
    n_calls = len(billed) * args.runs
    estimate = LOOK_ESTIMATE_MICROS * n_calls
    print(
        f"finishing_inspect_eval estimate {estimate} micros "
        f"(${estimate / 1_000_000:.2f}) live Gemini on real clips; "
        f"{len(billed)} billed rows × {args.runs} runs; "
        f"C-7.2 --yes over $5; owner cap ${OWNER_CAP_MICROS / 1_000_000:.0f}"
    )
    if estimate > FIVE_DOLLAR_MICROS and not args.yes:
        print("batch over $5 requires --yes (C-7.2)", file=sys.stderr)
        return 2
    if estimate > OWNER_CAP_MICROS and not args.yes:
        print(
            f"above ${OWNER_CAP_MICROS / 1_000_000:.0f} owner cap — pass --yes",
            file=sys.stderr,
        )
        return 2
    settings = get_settings()
    media = get_media(settings)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    needed = {str(row.get("clip") or "") for row in billed if row.get("clip")}
    clips = ensure_inspect_clips(settings, media, EVIDENCE / "clips", needed=needed)
    all_records: list[dict] = []
    summaries: list[dict] = []
    for run in range(1, args.runs + 1):
        recs, summary = run_suite(run, clips, media, settings, rows)
        all_records.extend(recs)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    stem = "inspect_eval"
    if wanted:
        stem = "inspect_eval_" + "_".join(sorted(wanted))
    out = EVIDENCE / f"{stem}.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for rec in all_records:
            handle.write(json.dumps(rec) + "\n")
    (EVIDENCE / f"{stem}_summary.json").write_text(
        json.dumps(
            {
                "summaries": summaries,
                "stations": sorted(wanted) if wanted else "all",
                "estimate_micros": estimate,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if all(s["pass"] for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
