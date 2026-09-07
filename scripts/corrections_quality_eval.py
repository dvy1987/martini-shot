#!/usr/bin/env python
"""D-10 Corrections quality eval on original clips with real deficits.

Three diverse correction kinds (not gradients, not BBB):
  signage        — café wooden sign → rewrite to OPEN
  prop_removal   — paper cup on the table → remove
  on_set_graphic — chalkboard misspelled OPNN → rewrite to OPEN

Omni edit only. If Omni cannot be called, stop. A Veo-finished row is not
an Omni pass. Evidence: docs/evidence/D-10/ (dated files, never overwrite).

Usage: .venv\\Scripts\\python.exe scripts\\corrections_quality_eval.py
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
from backend.core.gcs import get_gcs
from backend.core.generative import estimate_extend_cost_micros
from backend.core.models import OMNI_MODEL
from backend.evals.corrections_quality import (
    SOURCES,
    summarize_corrections_quality,
)
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id
from backend.shots import lifecycle as shots


def _ensure_source(settings: Any, row: dict[str, Any]) -> None:
    from backend.core.gcs import object_key

    gcs = get_gcs(settings)
    key = object_key(row["source_uri"])
    if gcs.exists(key):
        return
    prompt = row.get("generate_if_missing") or ""
    if not prompt:
        raise FileNotFoundError(f"missing original tape {row['source_uri']}")
    print(f"generating original start clip for {row['id']}", flush=True)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "d9_omni_extend_original", ROOT / "scripts" / "d9_omni_extend_original.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load original-clip generator")
    d9 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d9)
    start = d9.generate_start_clip(settings, prompt)
    d9._upload_gs(settings, key, start["video_bytes"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    n = len(SOURCES) * args.runs
    estimate = n * estimate_extend_cost_micros(7.0, resolution="360p")
    print(
        f"estimated_cost_micros={estimate} (~${estimate / 1_000_000:.2f}) "
        f"for {n} Omni correction drafts on original clips",
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
    project_id = f"proj-d10-omni-{stamp.lower()}"
    store.set_doc(
        "pc-projects",
        project_id,
        {
            "project_id": project_id,
            "title": "D-10 Omni original-clip corrections eval",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        },
    )

    for row in SOURCES:
        _ensure_source(settings, row)

    records: list[dict] = []
    stopped = ""
    for run_index in range(1, args.runs + 1):
        for row in SOURCES:
            shot_id = shots.ensure_shot(
                store, project_id=project_id, title=row["title"]
            )
            record: dict = {
                "run": run_index,
                "kind": row["kind"],
                "scene_id": row["id"],
                "shot_id": shot_id,
                "source_uri": row["source_uri"],
                "intent": row["intent"],
            }
            try:
                approval_id = propose_approval(
                    store,
                    {
                        "project_id": project_id,
                        "kind": "fix",
                        "title": f"Correct shot {shot_id}",
                        "detail": f"D-10 {row['kind']}",
                        "command": {
                            "name": "correct_shot",
                            "args": {
                                "shot_id": shot_id,
                                "project_id": project_id,
                                "source_uri": row["source_uri"],
                                "intent": row["intent"],
                                "protected_subjects": row["protected_subjects"],
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

    payload = summarize_corrections_quality(records)
    payload["stopped"] = stopped
    payload["project_id"] = project_id
    payload["kinds"] = [row["kind"] for row in SOURCES]
    payload["omni_model"] = OMNI_MODEL
    if stopped:
        payload["pass"] = False
        payload["fail_reason"] = (
            payload.get("fail_reason") + "," if payload.get("fail_reason") else ""
        ) + "omni_stop"
    evidence = ROOT / "docs" / "evidence" / "D-10"
    evidence.mkdir(parents=True, exist_ok=True)
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
