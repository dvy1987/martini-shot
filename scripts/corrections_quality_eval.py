#!/usr/bin/env python
"""D-10 Corrections quality eval: H-0 → Omni edit → flicker QC → alternate.

Three fresh holdout shots. Natural BBB grove/clearing recitation-refuse
Omni `edit` (same content-dependent refusal D-9 recorded); the quality suite
therefore uses labeled synthetic INPUT (C-1.3) that Omni will actually render:
synthetic-drift-01, synthetic-drift-02 (gradient variants), and
synthetic-mark-03 (gradient + red box). Metric: mean and max flicker < 0.02.

Cost estimate (draft 360p, ≤7s): 3 × ~$0.23 ≈ $0.70 per run; 3 runs ≈ $2.10
(under $5, C-7.2 — still printed). Use --yes if you raise --runs enough to
cross $5. Evidence: docs/evidence/D-10/ (dated files, never overwrite).
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
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id
from backend.shots import lifecycle as shots

CASES = [
    (
        "synthetic-drift-01-720p.mp4",
        "Synthetic drift — signage plate",
        "Replace any visible signage text with OPEN. Keep the characters identical.",
    ),
    (
        "synthetic-drift-02-720p.mp4",
        "Synthetic drift — faster plate",
        "Keep everything else the same while smoothing a small background blemish.",
    ),
    (
        "synthetic-mark-03-720p.mp4",
        "Synthetic mark — red box",
        "Remove the small red mark in the lower left. Keep everything else the same.",
    ),
]
SOURCE_PREFIX = "probes720"
FLICKER_GATE = 0.02


def _local_source(filename: str) -> Path | None:
    for folder in ("tmp", "spike"):
        path = ROOT / "fixtures" / folder / filename
        if path.exists():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    n = len(CASES) * args.runs
    estimate = n * estimate_extend_cost_micros(7.0, resolution="360p")
    print(
        f"estimated_cost_micros={estimate} (~${estimate / 1_000_000:.2f}) "
        f"for {n} Omni correction drafts",
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
    project_id = f"proj-d10-corrections-{time.strftime('%Y%m%d')}"
    store.set_doc(
        "pc-projects",
        project_id,
        {
            "project_id": project_id,
            "title": "D-10 Corrections eval",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        },
    )

    records: list[dict] = []
    for run_index in range(1, args.runs + 1):
        for filename, title, intent in CASES:
            key = f"{SOURCE_PREFIX}/{filename}"
            local = _local_source(filename)
            if not gcs.exists(key):
                if local is None:
                    raise FileNotFoundError(
                        f"missing correction source {key} in GCS and fixtures"
                    )
                gcs.upload_bytes(key, local.read_bytes(), content_type="video/mp4")
            shot_id = shots.ensure_shot(store, project_id=project_id, title=title)
            source_uri = f"gs://{settings.gcs_bucket}/{key}"
            record: dict = {
                "run": run_index,
                "shot_file": filename,
                "shot_id": shot_id,
                "source_uri": source_uri,
                "intent": intent,
            }
            try:
                approval_id = propose_approval(
                    store,
                    {
                        "project_id": project_id,
                        "kind": "fix",
                        "title": f"Correct shot {shot_id}",
                        "detail": f"D-10 EDD {filename}",
                        "command": {
                            "name": "correct_shot",
                            "args": {
                                "shot_id": shot_id,
                                "project_id": project_id,
                                "source_uri": source_uri,
                                "intent": intent,
                                "protected_subjects": ["lead characters"],
                                "continuity_constraints": ["preserve framing"],
                            },
                        },
                    },
                )
                decided = machine.dispatch(
                    approval_id, "approve", approver="d10-eval", reason="EDD eval"
                )
                record["approval_id"] = approval_id
                record["approval_status"] = decided.get("status")
                job_id = f"cor-{approval_id}"
                record["job_id"] = job_id
                if decided.get("status") != "resolved":
                    raise RuntimeError(
                        f"approval did not resolve: {decided.get('status')}"
                    )
                job = process_job_id(queue, gcs, settings, job_id)
                if job is None:
                    raise RuntimeError("worker could not claim the correction job")
                record.update(
                    {
                        "job_status": job.status,
                        "cost_micros": job.cost_micros,
                        "flicker": job.result.get("flicker"),
                        "qc_decision": job.result.get("qc_decision"),
                        "alternate_id": job.result.get("alternate_id"),
                        "artifact_ref": job.result.get("artifact_ref"),
                        "render_model": job.result.get("render_model"),
                    }
                )
                if job.result.get("alternate_id"):
                    alternate = store.get_doc(
                        "pc-alternates", job.result["alternate_id"]
                    )
                    record["alternate_status"] = (alternate or {}).get("status")
                    record["alternate_op"] = (alternate or {}).get("op")
            except Exception as exc:
                record.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            records.append(record)
            print(json.dumps(record, indent=2), flush=True)

    flickers = [
        float(row["flicker"])
        for row in records
        if isinstance(row.get("flicker"), (int, float))
    ]
    mean_flicker = sum(flickers) / len(flickers) if flickers else 1.0
    max_flicker = max(flickers) if flickers else 1.0
    payload = {
        "suite": "corrections_quality",
        "metric": "mean_output_flicker",
        "threshold": FLICKER_GATE,
        "mean_output_flicker": round(mean_flicker, 5),
        "max_output_flicker": round(max_flicker, 5),
        "n": len(records),
        "renders_completed": sum(1 for row in records if row.get("alternate_id")),
        "pass": (
            len(flickers) == len(records)
            and mean_flicker < FLICKER_GATE
            and max_flicker < FLICKER_GATE
            and all(row.get("alternate_status") == "draft" for row in records)
            and all(row.get("alternate_op") == "correction" for row in records)
            and all(row.get("qc_decision") == "pass" for row in records)
        ),
    }
    evidence = ROOT / "docs" / "evidence" / "D-10"
    evidence.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (evidence / f"corrections_quality_eval_{stamp}.jsonl").write_text(
        "\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8"
    )
    (evidence / f"corrections_quality_summary_{stamp}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
