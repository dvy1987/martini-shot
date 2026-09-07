#!/usr/bin/env python
"""Generate one original LIVE-ACTION clip, then D-9 Omni extend (no Veo pass).

People must be doing something (hands, tools, motion). If Omni fails, stop.

Usage: .venv\\Scripts\\python.exe scripts\\d9_omni_live_action.py
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
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from d9_omni_extend_original import _upload_gs, generate_start_clip

from backend.approvals.machine import ApprovalStateMachine, propose_approval
from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.core.gcs import get_gcs
from backend.core.generative import estimate_extend_cost_micros
from backend.core.models import OMNI_MODEL
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id
from backend.shots import lifecycle as shots

EVIDENCE = ROOT / "docs" / "evidence" / "D-9"
SCENE = {
    "id": "kitchen-cooks",
    "title": "Kitchen — cooks keep working",
    "prompt": (
        "Two cooks in a small restaurant kitchen. One chops onions on a "
        "wooden board. The other stirs a steaming pan. They keep working "
        "the whole time. Eight seconds."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-uri",
        default="",
        help="Reuse an existing original live-action gs:// clip (skip generate)",
    )
    args = parser.parse_args()
    reuse = args.source_uri.startswith("gs://")
    estimate = (
        estimate_extend_cost_micros(7.0, resolution="360p")
        if reuse
        else estimate_extend_cost_micros(8.0)
        + estimate_extend_cost_micros(7.0, resolution="360p")
    )
    print(
        f"estimated_cost_micros={estimate} (~${estimate / 1_000_000:.2f}) "
        + (
            "for 1 Omni D-9 draft extend on existing live-action clip"
            if reuse
            else "for 1 live-action Omni clip + 1 Omni D-9 draft extend"
        ),
        flush=True,
    )
    settings = get_settings()
    store = get_firestore(settings)
    queue = FirestoreLeaseQueue(store)
    gcs = get_gcs(settings)
    from backend.api.spine import _grafana_annotator

    machine = ApprovalStateMachine(
        store, queue=queue, annotator=_grafana_annotator(settings)
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    project_id = f"proj-d9-live-{stamp.lower()}"
    store.set_doc(
        "pc-projects",
        project_id,
        {
            "project_id": project_id,
            "title": "D-9 Omni live-action extend",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        },
    )
    record: dict = {
        "scene_id": SCENE["id"],
        "prompt": SCENE["prompt"],
        "project_id": project_id,
    }
    print(f"=== Omni MAKE live-action clip {SCENE['id']} ===", flush=True)
    try:
        if reuse:
            source_uri = args.source_uri
            record.update(
                {
                    "start_maker": "omni",
                    "start_model": OMNI_MODEL,
                    "start_shape": "reused",
                    "source_uri": source_uri,
                }
            )
            print(f"REUSING {source_uri}", flush=True)
        else:
            made = generate_start_clip(settings, SCENE["prompt"])
            key = f"original-probes/{stamp}-{SCENE['id']}.mp4"
            source_uri = _upload_gs(settings, key, made["video_bytes"])
            record.update(
                {
                    "start_maker": made["maker"],
                    "start_model": made["model"],
                    "start_shape": made.get("shape"),
                    "source_uri": source_uri,
                    "start_bytes": len(made["video_bytes"]),
                }
            )
            if made.get("omni_create_error"):
                record["omni_create_error"] = made["omni_create_error"]
                print(
                    "OWNER NOTICE: Omni could not CREATE the start clip; "
                    f"Veo made it. Omni error: {made['omni_create_error']}",
                    flush=True,
                )
            print(f"START CLIP ok maker={made['maker']} {source_uri}", flush=True)

        shot_id = shots.ensure_shot(store, project_id=project_id, title=SCENE["title"])
        record["shot_id"] = shot_id
        print("=== D-9 station EXTEND (Omni required) ===", flush=True)
        approval_id = propose_approval(
            store,
            {
                "project_id": project_id,
                "kind": "fix",
                "title": f"Extend shot {shot_id}",
                "detail": "D-9 Omni live-action eval",
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
            approval_id, "approve", approver="d9-live-eval", reason="live-action EDD"
        )
        record["approval_id"] = approval_id
        if decided.get("status") != "resolved":
            raise RuntimeError(f"approval {decided.get('status')}")
        job_id = f"ext-{approval_id}"
        job = process_job_id(queue, gcs, settings, job_id)
        if job is None:
            raise RuntimeError("worker could not claim the extend job")
        record.update(
            {
                "job_id": job_id,
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
            alternate = store.get_doc("pc-alternates", job.result["alternate_id"])
            record["alternate_status"] = (alternate or {}).get("status")
        if record.get("omni_fallback") or OMNI_MODEL not in str(
            record.get("render_model") or ""
        ):
            print(
                "OWNER NOTICE: Omni FAILED on live-action D-9 extend. "
                f"render_model={record.get('render_model')} "
                f"omni_error={record.get('omni_error')}",
                flush=True,
            )
            raise RuntimeError("omni extend fallback")
        passed = (
            record.get("qc_decision") == "pass"
            and record.get("alternate_status") == "draft"
            and isinstance(record.get("flicker"), (int, float))
            and float(record["flicker"]) < 0.02
        )
        record["pass"] = passed
    except Exception as exc:
        record["pass"] = False
        record["error"] = f"{type(exc).__name__}: {exc}"[:500]
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / f"omni_live_action_{stamp}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        print("STOPPED.", flush=True)
        print(json.dumps(record, indent=2), flush=True)
        return 1

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"omni_live_action_{stamp}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
