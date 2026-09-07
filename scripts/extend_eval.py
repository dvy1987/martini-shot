#!/usr/bin/env python
"""D-9 Extend EDD: 3 original clips → Omni draft + Omni master (no Veo pass).

Uses already-generated original café/florist tapes (not Big Buck Bunny).
Each shot: H-0 extend_shot (360p draft) then render_master (720p) after QC.

Usage: .venv\\Scripts\\python.exe scripts\\extend_eval.py
Cost: print estimate; --yes if over $5 (C-7.2).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.approvals.machine import ApprovalStateMachine, propose_approval
from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.core.gcs import get_gcs, object_key
from backend.core.generative import estimate_extend_cost_micros
from backend.core.models import OMNI_MODEL
from backend.evals.extend_quality import summarize_extend_quality
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id
from backend.shots import lifecycle as shots

EVIDENCE = ROOT / "docs" / "evidence" / "D-9"
SOURCES = [
    {
        "id": "kitchen-cooks",
        "title": "Kitchen — cooks keep working",
        "source_uri": (
            "gs://martini-shot-media/original-probes/20260907T083210Z-kitchen-cooks.mp4"
        ),
    },
    {
        "id": "florist-tulips",
        "title": "Florist counter — tulips keep being arranged",
        "source_uri": (
            "gs://martini-shot-media/original-probes/"
            "20260907T081720Z-florist-tulips.mp4"
        ),
    },
    {
        "id": "cafe-sign",
        "title": "Café exterior — sign stays in frame",
        "source_uri": (
            "gs://martini-shot-media/original-probes/20260907T080221Z-cafe-sign.mp4"
        ),
    },
]


def _job_record(job: Any, *, scene_id: str, source_uri: str, shot_id: str) -> dict:
    record = {
        "scene_id": scene_id,
        "source_uri": source_uri,
        "shot_id": shot_id,
        "job_id": job.id,
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
        "interaction_id": job.result.get("interaction_id"),
    }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    n = len(SOURCES)
    estimate = n * estimate_extend_cost_micros(
        7.0, resolution="360p"
    ) + n * estimate_extend_cost_micros(7.0, resolution="720p")
    print(
        f"estimated_cost_micros={estimate} (~${estimate / 1_000_000:.2f}) "
        f"for {n} Omni drafts + {n} Omni masters on original clips",
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
    project_id = f"proj-d9-omni-{stamp.lower()}"
    store.set_doc(
        "pc-projects",
        project_id,
        {
            "project_id": project_id,
            "title": "D-9 Omni 3-shot draft+master eval",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        },
    )

    records: list[dict] = []
    try:
        for scene in SOURCES:
            key = object_key(scene["source_uri"])
            if not gcs.exists(key):
                raise RuntimeError(f"missing original clip {scene['source_uri']}")
            shot_id = shots.ensure_shot(
                store, project_id=project_id, title=scene["title"]
            )
            print(f"=== DRAFT extend {scene['id']} {shot_id} ===", flush=True)
            draft_id = propose_approval(
                store,
                {
                    "project_id": project_id,
                    "kind": "fix",
                    "title": f"Extend shot {shot_id}",
                    "detail": f"D-9 Omni draft {scene['id']}",
                    "command": {
                        "name": "extend_shot",
                        "args": {
                            "shot_id": shot_id,
                            "project_id": project_id,
                            "source_uri": scene["source_uri"],
                        },
                    },
                },
            )
            decided = machine.dispatch(
                draft_id, "approve", approver="d9-omni-eval", reason="EDD draft"
            )
            if decided.get("status") != "resolved":
                raise RuntimeError(f"draft approval {decided.get('status')}")
            job = process_job_id(queue, gcs, settings, f"ext-{draft_id}")
            if job is None:
                raise RuntimeError("could not claim draft extend job")
            record = _job_record(
                job,
                scene_id=scene["id"],
                source_uri=scene["source_uri"],
                shot_id=shot_id,
            )
            record["approval_id"] = draft_id
            if job.result.get("alternate_id"):
                alternate = store.get_doc("pc-alternates", job.result["alternate_id"])
                record["alternate_status"] = (alternate or {}).get("status")
                record["alternate_op"] = (alternate or {}).get("op")
                record["alternate_tier"] = (alternate or {}).get("tier")
            if record.get("omni_fallback") or OMNI_MODEL not in str(
                record.get("render_model") or ""
            ):
                print(
                    "OWNER NOTICE: Omni FAILED on D-9 draft extend. "
                    f"render_model={record.get('render_model')} "
                    f"omni_error={record.get('omni_error')}",
                    flush=True,
                )
                raise RuntimeError("omni draft fallback")
            records.append(record)
            print(json.dumps(record, indent=2), flush=True)

            print(f"=== MASTER extend {scene['id']} ===", flush=True)
            master_id = propose_approval(
                store,
                {
                    "project_id": project_id,
                    "kind": "fix",
                    "title": f"Master extend shot {shot_id}",
                    "detail": f"D-9 Omni master {scene['id']}",
                    "command": {
                        "name": "render_master",
                        "args": {
                            "shot_id": shot_id,
                            "project_id": project_id,
                            "op": "extend",
                            "source_uri": scene["source_uri"],
                        },
                    },
                },
            )
            decided = machine.dispatch(
                master_id, "approve", approver="d9-omni-eval", reason="EDD master"
            )
            if decided.get("status") != "resolved":
                raise RuntimeError(
                    f"master approval {decided.get('status')}: {decided}"
                )
            job = process_job_id(queue, gcs, settings, f"mst-ext-{master_id}")
            if job is None:
                raise RuntimeError("could not claim master extend job")
            master = _job_record(
                job,
                scene_id=scene["id"],
                source_uri=scene["source_uri"],
                shot_id=shot_id,
            )
            master["approval_id"] = master_id
            if job.result.get("alternate_id"):
                alternate = store.get_doc("pc-alternates", job.result["alternate_id"])
                master["alternate_status"] = (alternate or {}).get("status")
                master["alternate_op"] = (alternate or {}).get("op")
                master["alternate_tier"] = (alternate or {}).get("tier")
            if master.get("omni_fallback") or OMNI_MODEL not in str(
                master.get("render_model") or ""
            ):
                print(
                    "OWNER NOTICE: Omni FAILED on D-9 master extend. "
                    f"render_model={master.get('render_model')} "
                    f"omni_error={master.get('omni_error')}",
                    flush=True,
                )
                raise RuntimeError("omni master fallback")
            records.append(master)
            print(json.dumps(master, indent=2), flush=True)
    except Exception as exc:
        print(f"STOPPED. {type(exc).__name__}: {exc}", flush=True)
        payload = {
            **summarize_extend_quality(records, min_drafts=n, min_masters=n),
            "stopped": True,
            "pass": False,
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "records": records,
        }
        _write_evidence(stamp, payload, records)
        print(
            json.dumps({k: v for k, v in payload.items() if k != "records"}, indent=2)
        )
        return 1

    summary = summarize_extend_quality(records, min_drafts=n, min_masters=n)
    payload = {**summary, "stopped": False, "records": records}
    _write_evidence(stamp, payload, records)
    print(json.dumps({k: payload[k] for k in payload if k != "records"}, indent=2))
    if not payload["pass"]:
        print(f"FAIL reason={payload.get('fail_reason')}", flush=True)
        return 1
    return 0


def _write_evidence(stamp: str, payload: dict, records: list[dict]) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    dated = EVIDENCE / f"extend_omni_station_{stamp}.json"
    dated.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (EVIDENCE / "extend_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    summary = {k: v for k, v in payload.items() if k != "records"}
    (EVIDENCE / "extend_eval_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
