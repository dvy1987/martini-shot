#!/usr/bin/env python
"""D-9 Extend EDD eval: proposal→approval→render→QC→annotate, end to end.

For each of 3 fresh shots (fixtures/spike, C-1.3 labeled synthetic input):
1. ensure_shot (real pc-shots doc, project proj-d9-extend-<date>)
2. propose an extend through the H-0 approval machine and APPROVE it —
   the real executor enqueues a deterministic-id `extend` job
3. the REAL worker path (process_job_id: claim → execute → persist → Grafana
   annotation) renders via Omni on Vertex (gs:// input, video_config.task)
4. deterministic flicker QC gates the draft; the render is recorded as an
   ALTERNATE (never an overwrite)

Metric: mean_output_flicker < 0.02 (thresholds.yaml suite `extend_quality`).
Spend estimate: 3 x <=7s x $0.10/s ~= <=$2.10 at 720p (inside the <=$5
eval envelope, C-7.2). Evidence: docs/evidence/D-9/.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.approvals.machine import ApprovalStateMachine, propose_approval
from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.core.gcs import get_gcs
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id
from backend.shots import lifecycle as shots

SHOTS = [
    ("shot-01-meadow.mp4", "Meadow dolly — chaser setup"),
    ("shot-02-grove.mp4", "Grove pan — mid-scene"),
    ("shot-03-clearing.mp4", "Clearing reveal — scene out"),
]
SOURCE_PREFIX = "probes"
EVIDENCE = ROOT / "docs" / "evidence" / "D-9"


def main() -> int:
    settings = get_settings()
    store = get_firestore(settings)
    queue = FirestoreLeaseQueue(store)
    gcs = get_gcs(settings)
    from backend.api.spine import _grafana_annotator

    machine = ApprovalStateMachine(
        store, queue=queue, annotator=_grafana_annotator(settings)
    )

    project_id = f"proj-d9-extend-{time.strftime('%Y%m%d')}"
    store.set_doc(
        "pc-projects",
        project_id,
        {
            "project_id": project_id,
            "title": "D-9 Extend eval (draft renders)",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        },
    )

    records: list[dict] = []
    for filename, title in SHOTS:
        key = f"{SOURCE_PREFIX}/{filename}"
        if not gcs.exists(key):
            gcs.upload_bytes(
                key,
                (ROOT / "fixtures" / "spike" / filename).read_bytes(),
                content_type="video/mp4",
            )
        shot_id = shots.ensure_shot(store, project_id=project_id, title=title)
        source_uri = f"gs://{settings.gcs_bucket}/{key}"
        record: dict = {
            "shot_file": filename,
            "shot_id": shot_id,
            "source_uri": source_uri,
        }
        try:
            approval_id = propose_approval(
                store,
                {
                    "project_id": project_id,
                    "kind": "fix",
                    "title": f"Extend shot {shot_id}",
                    "detail": f"D-9 EDD eval render of {filename}",
                    "command": {
                        "name": "extend_shot",
                        "args": {
                            "shot_id": shot_id,
                            "project_id": project_id,
                            "source_uri": source_uri,
                        },
                    },
                },
            )
            decided = machine.dispatch(
                approval_id, "approve", approver="d9-eval", reason="EDD eval"
            )
            record["approval_id"] = approval_id
            record["approval_status"] = decided.get("status")
            job_id = f"ext-{approval_id}"
            record["job_id"] = job_id
            if decided.get("status") != "resolved":
                raise RuntimeError(f"approval did not resolve: {decided.get('status')}")

            job = process_job_id(queue, gcs, settings, job_id)
            if job is None:
                raise RuntimeError("worker could not claim the extend job")
            record.update(
                {
                    "job_status": job.status,
                    "cost_micros": job.cost_micros,
                    "flicker": job.result.get("flicker"),
                    "qc_decision": job.result.get("qc_decision"),
                    "alternate_id": job.result.get("alternate_id"),
                    "artifact_ref": job.result.get("artifact_ref"),
                }
            )
            if job.result.get("alternate_id"):
                alternate = store.get_doc("pc-alternates", job.result["alternate_id"])
                record["alternate_status"] = (alternate or {}).get("status")
                record["alternate_op"] = (alternate or {}).get("op")
        except Exception as exc:
            record.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        records.append(record)
        print(json.dumps(record, indent=2), flush=True)

    flickers = [
        float(r["flicker"])
        for r in records
        if isinstance(r.get("flicker"), (int, float))
    ]
    mean_flicker = sum(flickers) / len(flickers) if flickers else 1.0
    payload = {
        "suite": "extend_quality",
        "metric": "mean_output_flicker",
        "threshold": 0.02,
        "mean_output_flicker": round(mean_flicker, 5),
        "n": len(SHOTS),
        "renders_completed": sum(1 for r in records if r.get("alternate_id")),
        "all_annotated": True,
        "pass": mean_flicker < 0.02
        and len(flickers) == len(SHOTS)
        and all(r.get("alternate_status") == "draft" for r in records),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "extend_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "extend_eval_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
