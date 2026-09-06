#!/usr/bin/env python
"""Dub QC eval (E-2, C-3.3/.4): the REAL pipeline against the REAL model.

For each seeded case in dub_qc.jsonl: load the labeled source fixture, run
REAL Chirp 3 HD TTS for the target language, apply the labeled truncation
mutation (labeled INPUT mutation, C-1.3), measure timing deterministically,
then the REAL Dub QC agent listens (billed Gemini call) and classifies.

Gates (thresholds.yaml):
  dub_timing            mean |duration delta| over full dubs <= 45 ms
  dub_truncation_recall truncation cases classified 'truncated' >= 0.9

Evidence: docs/evidence/E-2/dub_qc_eval.jsonl + dub_qc_summary.json.
Estimated cost per run: 18 TTS lines (~$0.01) + 18 flash audio judgments
(~$0.03) — well under the $5 owner-approval bar (C-7.2).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.core.generative import tts_synthesize
from backend.stations.dubbing.qc import measure_timing, truncate_speech_wav
from backend.stations.dubbing.run import DUB_TOLERANCE_MS as TOLERANCE_MS
from backend.stations.dubbing.run import time_fit_dub
from backend.supervisor.station_agents.dub_qc import decide_dub

DATASET = ROOT / "backend" / "evals" / "datasets" / "dub_qc.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "E-2"
TIMING_GATE_MS = 45.0
RECALL_GATE = 0.9


def run_suite(run_index: int) -> tuple[list[dict], dict]:
    settings = get_settings()
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records: list[dict] = []
    deltas: list[float] = []
    truncation_hits = 0
    truncation_total = 0
    total_cost_micros = 0
    for row in rows:
        original_wav = (ROOT / row["original_ref"]).read_bytes()
        ssml = f"<speak>{row['script_target']}</speak>"
        render = tts_synthesize(
            settings,
            ssml=ssml,
            language_code=str(row["lang"]),
            voice_name=str(row["voice"]),
        )
        dub_wav = bytes(render["audio_bytes"])
        total_cost_micros += int(render["cost_estimate_micros"])

        # Same pipeline as the station: deterministic atempo fit pass first
        # (a translated line's natural length rarely matches the source —
        # the studio time-fits it), THEN the labeled truncation mutation
        # (the defect the agent must catch), then measure + judge.
        fit = time_fit_dub(
            settings,
            ssml=ssml,
            language=str(row["lang"]),
            original_wav=original_wav,
            first_wav=dub_wav,
            voice_name=str(row["voice"]),
        )
        dub_wav = fit["wav"]
        measurements = fit["measurements"]

        truncate_ms = int(row.get("truncate_ms") or 0)
        if truncate_ms:
            # Speech-aware mutation: cuts into words, not the TTS trailing
            # silence (a silent-tail cut is inaudible — the agent is RIGHT
            # to call it clean).
            dub_wav = truncate_speech_wav(dub_wav, truncate_ms)
            measurements = measure_timing(
                original_wav, dub_wav, tolerance_ms=TOLERANCE_MS
            )

        record: dict = {
            "run": run_index,
            "id": row["id"],
            "truncate_ms": truncate_ms,
            "fit_applied": fit["fit_applied"],
            "fit_tempo": round(fit["tempo"], 4),
            "duration_delta_ms": measurements["duration_delta_ms"],
            "sync_offset_ms": measurements["sync_offset_ms"],
            "deterministic_verdict": measurements["verdict"],
        }
        try:
            decision, agent_cost = decide_dub(
                settings,
                measurements=measurements,
                dubbed_wav=dub_wav,
                script=str(row["script_target"]),
            )
            record.update(
                {
                    "ok": True,
                    "classification": decision.raw.get("classification"),
                    "decision": decision.decision,
                    "overridden": decision.overridden,
                    "confidence": decision.confidence,
                    "reason": decision.reason[:200],
                    "cost_micros": agent_cost,
                }
            )
            total_cost_micros += agent_cost
        except Exception as exc:
            record.update(
                {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            )
        # Accounting INDEPENDENT of agent success: a failed judgment is a
        # miss, never a silent exclusion (honest evidence, C-3.5).
        if truncate_ms:
            truncation_total += 1
            if record.get("classification") == "truncated":
                truncation_hits += 1
        else:
            deltas.append(abs(float(measurements["duration_delta_ms"])))
        records.append(record)
        print(
            json.dumps(
                {
                    k: record.get(k)
                    for k in (
                        "run",
                        "id",
                        "duration_delta_ms",
                        "classification",
                        "decision",
                        "error",
                    )
                }
            ),
            flush=True,
        )

    mae = statistics.fmean(deltas) if deltas else float("inf")
    recall = truncation_hits / truncation_total if truncation_total else 0.0
    summary = {
        "run": run_index,
        "mean_duration_delta_mae_ms": round(mae, 1),
        "timing_pass": mae <= TIMING_GATE_MS,
        "truncation_recall": round(recall, 3),
        "truncation_hits": truncation_hits,
        "truncation_total": truncation_total,
        "recall_pass": recall >= RECALL_GATE,
        "cost_micros": total_cost_micros,
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3, help="number of live runs")
    args = parser.parse_args()

    all_records: list[dict] = []
    summaries: list[dict] = []
    for i in range(1, args.runs + 1):
        print(f"=== dub_qc live run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    timing_pass = all(s["timing_pass"] for s in summaries)
    recall_pass = all(s["recall_pass"] for s in summaries)
    payload = {
        "suite": "dub_qc",
        "runs": args.runs,
        "gates": {
            "dub_timing": {"threshold": TIMING_GATE_MS, "comparison": "<="},
            "dub_truncation_recall": {"threshold": RECALL_GATE, "comparison": ">="},
        },
        "per_run": summaries,
        "timing_pass": timing_pass,
        "recall_pass": recall_pass,
        "pass": timing_pass and recall_pass,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "dub_qc_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "dub_qc_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
