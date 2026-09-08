#!/usr/bin/env python
"""Omni quality eval for Relight, Coverage, or Camera Language.

Original GCS tapes. Omni only. If Omni cannot render, stop and tell the owner.
Usage:
  .venv\\Scripts\\python.exe scripts\\stage1a_quality_eval.py --station relight
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.approvals.machine import ApprovalStateMachine, propose_approval
from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.core.gcs import get_gcs
from backend.core.generative import estimate_extend_cost_micros
from backend.core.models import OMNI_MODEL
from backend.evals.stage1a_quality import STATIONS, summarize_quality
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id
from backend.shots import lifecycle as shots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--station",
        required=True,
        choices=sorted(STATIONS),
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    spec = STATIONS[args.station]
    n = len(spec["sources"]) * args.runs
    estimate = n * estimate_extend_cost_micros(7.0, resolution="360p")
    print(
        f"estimated_cost_micros={estimate} (~${estimate / 1_000_000:.2f}) "
        f"for {n} Omni {args.station} drafts on original clips",
        flush=True,
    )
    if estimate > 5_000_000 and not args.yes:
        print("batch over $5 requires --yes (C-7.2)", file=sys.stderr)
        return 2

    settings = get_settings()
    store = get_firestore(settings)
    queue = FirestoreLeaseQueue(store)
    gcs = get_gcs(settings)
    from backend.api.spine import _grafana_annotator

    machine = ApprovalStateMachine(
        store, queue=queue, annotator=_grafana_annotator(settings)
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    project_id = f"proj-{args.station}-omni-{stamp.lower()}"
    store.set_doc(
        "pc-projects",
        project_id,
        {
            "project_id": project_id,
            "title": f"{args.station} Omni original-clip eval",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        },
    )

    records: list[dict] = []
    stopped = ""
    for run_index in range(1, args.runs + 1):
        for row in spec["sources"]:
            shot_id = shots.ensure_shot(
                store, project_id=project_id, title=row["title"]
            )
            record: dict = {
                "run": run_index,
                "kind": row["kind"],
                "scene_id": row["id"],
                "shot_id": shot_id,
                "source_uri": row["source_uri"],
                "station": args.station,
            }
            try:
                cmd_args = {
                    "shot_id": shot_id,
                    "project_id": project_id,
                    "source_uri": row["source_uri"],
                    **row["args"],
                }
                approval_id = propose_approval(
                    store,
                    {
                        "project_id": project_id,
                        "kind": "fix",
                        "title": f"{args.station} shot {shot_id}",
                        "detail": f"{args.station} {row['kind']}",
                        "command": {"name": spec["command"], "args": cmd_args},
                    },
                )
                decided = machine.dispatch(
                    approval_id,
                    "approve",
                    approver=f"{args.station}-eval",
                    reason="EDD eval",
                )
                record["approval_id"] = approval_id
                record["approval_status"] = decided.get("status")
                job_id = f"{spec['prefix']}-{approval_id}"
                record["job_id"] = job_id
                if decided.get("status") != "resolved":
                    raise RuntimeError(
                        f"approval did not resolve: {decided.get('status')}"
                    )
                job = process_job_id(queue, gcs, settings, job_id)
                if job is None:
                    raise RuntimeError("worker could not claim the job")
                record.update(
                    {
                        "job_status": job.status,
                        "cost_micros": job.cost_micros,
                        "flicker": job.result.get("flicker"),
                        "qc_decision": job.result.get("qc_decision"),
                        "alternate_id": job.result.get("alternate_id"),
                        "artifact_ref": job.result.get("artifact_ref"),
                        "render_model": job.result.get("render_model"),
                        "omni_fallback": bool(job.result.get("omni_fallback")),
                        "omni_error": job.result.get("omni_error") or "",
                        "tier": job.result.get("tier") or "draft",
                    }
                )
                if job.result.get("alternate_id"):
                    alternate = store.get_doc(
                        "pc-alternates", job.result["alternate_id"]
                    )
                    record["alternate_status"] = (alternate or {}).get("status")
                    record["alternate_op"] = (alternate or {}).get("op")
                model = str(record.get("render_model") or "")
                if record.get("omni_fallback") or "omni" not in model.lower():
                    stopped = (
                        f"Omni did not render {row['id']} run {run_index}: "
                        f"model={model!r} fallback={record.get('omni_fallback')} "
                        f"error={record.get('omni_error')!r}"
                    )
                    records.append(record)
                    print(json.dumps(record, indent=2), flush=True)
                    print(f"STOP: {stopped}", flush=True)
                    break
            except Exception as exc:
                record.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                stopped = record["error"]
                records.append(record)
                print(json.dumps(record, indent=2), flush=True)
                print(f"STOP: {stopped}", flush=True)
                break
            records.append(record)
            print(json.dumps(record, indent=2), flush=True)
        if stopped:
            break

    payload = summarize_quality(records, station=args.station, op=spec["op"])
    payload["stopped"] = stopped
    payload["project_id"] = project_id
    payload["omni_model"] = OMNI_MODEL
    if stopped:
        payload["pass"] = False
        extra = "omni_stop"
        payload["fail_reason"] = (
            f"{payload.get('fail_reason')},{extra}"
            if payload.get("fail_reason")
            else extra
        )
    evidence = ROOT / "docs" / "evidence" / args.station
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{args.station}_quality_eval_{stamp}.jsonl").write_text(
        "\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8"
    )
    (evidence / f"{args.station}_quality_summary_{stamp}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
