"""Gate G1 live run: real MP4 through the ingest API (same contract as the FE
Log-a-clip control), SSE capture, then Grafana MCP read-back (C-2.2).

Archives docs/evidence/G1/gate.json + sse.ndjson. Zero mocks.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from backend.core.config import get_settings, reset_settings
from backend.core.firestore import get_firestore
from backend.jobs.models import Job
from backend.jobs.queue import FirestoreLeaseQueue
from backend.supervisor.mcp import (
    GrafanaMcpConnector,
    ToolUnavailable,
    build_server_config,
)

EVIDENCE = ROOT / "docs" / "evidence" / "G1"
DEFAULT_MP4 = ROOT / "fixtures" / "g1" / "slate.mp4"
BOGUS_PREFIX = "gs://b/"


def _text(result: dict) -> str:
    content = result.get("content") or []
    if not content:
        return json.dumps(result)[:4000]
    return str(content[0].get("text") or "")[:8000]


def _cleanup_bogus_ingest(queue: FirestoreLeaseQueue) -> list[str]:
    forgotten: list[str] = []
    for snap in queue.store.client.collection("pc-jobs").stream():
        raw = snap.to_dict() or {}
        job = Job.from_dict(raw)
        refs = job.input_refs or []
        if job.station != "ingest":
            continue
        bogus = (
            not refs
            or any(str(ref).startswith(BOGUS_PREFIX) for ref in refs)
            or job.project_id in {"it-x", "it"}
        )
        if bogus:
            queue.forget(job.id)
            forgotten.append(job.id)
    return forgotten


def _listen_sse(
    url: str, headers: dict[str, str], bucket: list[str], stop: threading.Event
) -> None:
    try:
        with (
            httpx.Client(timeout=None) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            for line in response.iter_lines():
                if stop.is_set():
                    break
                if line:
                    bucket.append(line)
    except Exception as exc:
        bucket.append(f"sse-error: {exc}")


def _promql(gmc: GrafanaMcpConnector, expr: str) -> dict:
    return gmc.query_promql(
        expr,
        queryType="range",
        startTime="now-1h",
        stepSeconds=15,
    )


def _extract_trace_id(blob: str) -> str | None:
    match = re.search(r"\b([0-9a-f]{32})\b", blob, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"traceID['\"]?\s*[:=]\s*['\"]([0-9a-f]+)", blob, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def main() -> int:
    reset_settings()
    settings = get_settings()
    if not (settings.api_key and settings.gcp_project_id and settings.gcs_bucket):
        print("g1_gate: missing API key or GCP config", file=sys.stderr)
        return 2
    mp4 = DEFAULT_MP4
    if not mp4.is_file():
        print(f"g1_gate: missing fixture {mp4}", file=sys.stderr)
        return 2

    base = "http://127.0.0.1:8000"
    project_id = "g1"
    headers = {"X-API-Key": settings.api_key, "Accept": "application/json"}
    sse_url = f"{base}/api/v1/projects/{project_id}/events"

    store = get_firestore(settings)
    queue = FirestoreLeaseQueue(store)
    forgotten = _cleanup_bogus_ingest(queue)

    health = httpx.get(f"{base}/api/v1/health", timeout=10)
    health.raise_for_status()

    sse_lines: list[str] = []
    stop = threading.Event()
    listener = threading.Thread(
        target=_listen_sse,
        args=(
            sse_url,
            {"Accept": "text/event-stream", "X-API-Key": settings.api_key},
            sse_lines,
            stop,
        ),
        daemon=True,
    )
    listener.start()
    time.sleep(0.6)

    with mp4.open("rb") as handle:
        uploaded = httpx.post(
            f"{base}/api/v1/projects/{project_id}/ingest",
            headers={"X-API-Key": settings.api_key},
            files={"file": (mp4.name, handle, "video/mp4")},
            timeout=120,
        )
    uploaded.raise_for_status()
    job_body = uploaded.json()
    job_id = str(job_body["job_id"])

    deadline = time.time() + 120
    fetched: dict = {}
    while time.time() < deadline:
        fetched = httpx.get(
            f"{base}/api/v1/jobs/{job_id}",
            headers=headers,
            timeout=30,
        ).json()
        if fetched.get("status") in {"pass", "fail"}:
            break
        time.sleep(0.4)

    # OTLP metric reader is 60s; traces/logs flush sooner.
    time.sleep(75)
    stop.set()

    trace_query = f'{{ span.pc.job_id = "{job_id}" }}'
    service_query = '{ resource.service.name = "martini-shot-backend" && name = "station.ingest.run" }'
    config = build_server_config(settings)
    with GrafanaMcpConnector(config) as gmc:
        prom = {
            "pc_job_duration_seconds": _text(
                _promql(gmc, "pc_job_duration_seconds_count")
            ),
            "pc_job_cost_micros": _text(_promql(gmc, "pc_job_cost_micros_count")),
            "pc_job_outcome_total": _text(_promql(gmc, "pc_job_outcome_total")),
        }
        loki_attempts = [
            f'{{service_name="martini-shot-backend"}} |= `{job_id}`',
            f'{{job="martini-shot-backend"}} |= `{job_id}`',
            '{service_name="martini-shot-backend"} |= `ingest checksum done`',
        ]
        loki_hits: list[dict[str, str]] = []
        for logql in loki_attempts:
            result = gmc.query_loki(logql, limit=20)
            loki_hits.append({"logql": logql, "response": _text(result)})
            if job_id in _text(result) or "ingest checksum" in _text(result):
                break
        traces: dict[str, str] = {}
        try:
            traces["by_job_id"] = _text(gmc.search_traces(trace_query))
        except ToolUnavailable as exc:
            traces["error"] = str(exc)
        if "error" not in traces:
            traces["by_span_name"] = _text(gmc.search_traces(service_query))
        annotations = gmc.get_annotations(tags=["g1"])
        annotation_text = _text(annotations)

    trace_id = _extract_trace_id(traces.get("by_job_id") or "") or _extract_trace_id(
        traces.get("by_span_name") or ""
    )
    sse_job_events = [
        line for line in sse_lines if "job.updated" in line or "annotation" in line
    ]
    pack = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project_id": project_id,
        "job_id": job_id,
        "job_status": fetched.get("status"),
        "checksum_sha256": fetched.get("checksum_sha256"),
        "input_refs": fetched.get("input_refs"),
        "fixture": str(mp4.relative_to(ROOT)).replace("\\", "/"),
        "forgotten_bogus_jobs": forgotten,
        "sse_line_count": len(sse_lines),
        "sse_job_related": sse_job_events[:20],
        "trace_id": trace_id,
        "traceql": {"job": trace_query, "span": service_query},
        "traces": traces,
        "promql": prom,
        "loki": loki_hits,
        "annotation_readback": annotation_text[:4000],
        "annotation_mentions_job": job_id in annotation_text,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "gate.json").write_text(json.dumps(pack, indent=2), encoding="utf-8")
    (EVIDENCE / "sse.ndjson").write_text("\n".join(sse_lines), encoding="utf-8")
    print(
        json.dumps(
            {"job_id": job_id, "status": fetched.get("status"), "trace_id": trace_id}
        )
    )
    if fetched.get("status") != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
