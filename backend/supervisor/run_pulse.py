"""Run Pulse: four finishing-run answers from Grafana MCP + Firestore.

No LLM on this path (C-6.5). Grafana numbers are never invented (C-1).
This-run dollars stay on Firestore jobs; Grafana supplies factory health,
duration percentiles, annotations, and optional Tempo enrich / deep links.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from backend.jobs.models import Job
from backend.supervisor.annotate import project_annotation_tag

log = logging.getLogger("pc.run_pulse")

CACHE_TTL_S = 15.0
REMAINING_STATUSES = frozenset({"waiting", "queued", "running"})
_JOB_ID_RE = re.compile(r"job_id=([^\s]+)")
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

FAIL_RATE_EXPR = (
    "sum(rate(pc_job_outcome_total"
    '{outcome=~"fail|failed|quarantined"}[1h]))'
    " / sum(rate(pc_job_outcome_total[1h]))"
)
PROJECT_FAIL_RATE_EXPR = (
    "sum(rate(pc_job_outcome_total"
    '{{project_id="{project_id}",outcome=~"fail|failed|quarantined"}}[1h]))'
    ' / sum(rate(pc_job_outcome_total{{project_id="{project_id}"}}[1h]))'
)
DURATION_P50_EXPR = (
    "histogram_quantile(0.5, sum by (le, station) "
    "(rate(pc_job_duration_seconds_bucket[1h])))"
)


def reset_run_pulse_cache() -> None:
    _cache.clear()


def assemble_run_pulse(
    store: Any,
    project_id: str,
    *,
    grafana: Any = None,
    settings: Any = None,
    worklist: dict[str, Any] | None = None,
    jobs: list[Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """One snapshot for GET /api/v1/projects/{id}/run-pulse."""
    clock = time.monotonic() if now is None else now
    hit = _cache.get(project_id)
    if hit is not None and clock - hit[0] < CACHE_TTL_S:
        return hit[1]

    closer = None
    if grafana is None and settings is not None:
        grafana, closer = _open_grafana(settings)

    if worklist is None:
        try:
            from backend.supervisor.worklist import load_worklist

            worklist = load_worklist(store, project_id) or {}
        except Exception:
            worklist = {}

    rows = jobs
    if rows is None:
        try:
            rows = store.list_where("pc-jobs", "project_id", project_id)
        except Exception:
            log.exception("run-pulse job list failed project=%s", project_id)
            rows = []
    parsed_jobs = [_as_job(row) for row in rows or []]

    grafana_status = "ok" if grafana is not None else "unavailable"
    factory = _unknown_factory()
    p50_by_station: dict[str, float] = {}
    annotations: list[dict[str, Any]] = []
    evidence_url: str | None = None
    traces_by_job: dict[str, dict[str, Any]] = {}
    if grafana is not None:
        try:
            factory, p50_by_station = _query_metrics(grafana, project_id)
            annotations = _query_annotations(grafana, project_id)
            evidence_url = _deeplink(grafana)
        except Exception:
            log.exception("run-pulse grafana read failed project=%s", project_id)
            grafana_status = "unavailable"
            factory = _unknown_factory()
            p50_by_station = {}
            annotations = []

    burn = _burn(parsed_jobs)
    if grafana is not None and grafana_status == "ok" and burn.get("top"):
        try:
            traces_by_job = _trace_enrich(
                grafana, str(burn["top"][0].get("job_id") or "")
            )
        except Exception:
            log.exception("run-pulse tempo enrich failed project=%s", project_id)
        burn = _apply_trace_enrich(burn, traces_by_job)

    if closer is not None:
        try:
            closer()
        except Exception:
            pass

    eta = _eta(worklist or {}, p50_by_station, grafana_ok=grafana_status == "ok")
    wheel = {"items": _wheel_items(annotations, parsed_jobs)}
    if evidence_url:
        factory = {**factory, "evidence_url": evidence_url}
        burn = {**burn, "evidence_url": evidence_url}
        eta = {**eta, "evidence_url": evidence_url}

    snapshot = {
        "project_id": project_id,
        "grafana": grafana_status,
        "factory": factory,
        "burn": burn,
        "eta": eta,
        "wheel": wheel,
    }
    _cache[project_id] = (clock, snapshot)
    return snapshot


def _open_grafana(settings: Any) -> tuple[Any | None, Any | None]:
    try:
        from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config

        connector = GrafanaMcpConnector(build_server_config(settings))
        connector.connect()
        return connector, connector.close
    except Exception:
        log.exception("run-pulse could not open Grafana MCP")
        return None, None


def _as_job(row: Any) -> Job:
    if isinstance(row, Job):
        return row
    data = dict(row or {})
    if "id" not in data and data.get("job_id"):
        data["id"] = data["job_id"]
    return Job.from_dict(data)


def _mcp_text(result: dict[str, Any]) -> str:
    content = result.get("content") or []
    if not content:
        return ""
    first = content[0]
    if isinstance(first, dict):
        return str(first.get("text") or "")
    return str(getattr(first, "text", "") or "")


def _mcp_json(result: dict[str, Any]) -> Any:
    text = _mcp_text(result).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _vector_samples(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    if not isinstance(parsed, dict):
        return []
    data = parsed.get("data")
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, list):
            return [row for row in result if isinstance(row, dict)]
    result = parsed.get("result")
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    return []


def _sample_float(row: dict[str, Any]) -> float | None:
    value = row.get("value")
    if isinstance(value, list) and len(value) >= 2:
        try:
            return float(value[1])
        except (TypeError, ValueError):
            return None
    raw = row.get("value")
    try:
        return float(raw) if raw is not None and not isinstance(raw, list) else None
    except (TypeError, ValueError):
        return None


def _query_metrics(
    grafana: Any, project_id: str
) -> tuple[dict[str, Any], dict[str, float]]:
    global_raw = grafana.query_promql(FAIL_RATE_EXPR)
    project_raw = grafana.query_promql(
        PROJECT_FAIL_RATE_EXPR.format(project_id=project_id)
    )
    duration_raw = grafana.query_promql(DURATION_P50_EXPR)
    global_rate = _first_ratio(global_raw)
    project_rate = _first_ratio(project_raw)
    factory = _factory_verdict(global_rate, project_rate)
    p50: dict[str, float] = {}
    for row in _vector_samples(_mcp_json(duration_raw)):
        station = str((row.get("metric") or {}).get("station") or "")
        seconds = _sample_float(row)
        if station and seconds is not None:
            p50[station] = seconds
    return factory, p50


def _first_ratio(result: dict[str, Any]) -> float | None:
    samples = _vector_samples(_mcp_json(result))
    if not samples:
        return None
    return _sample_float(samples[0])


def _unknown_factory() -> dict[str, Any]:
    return {
        "verdict": "unknown",
        "headline": "Factory health is unknown until Grafana answers.",
    }


def _factory_verdict(
    global_rate: float | None, project_rate: float | None
) -> dict[str, Any]:
    if global_rate is None:
        return {
            "verdict": "unknown",
            "headline": "No station-failure samples yet for the factory.",
        }
    if global_rate >= 0.25:
        return {
            "verdict": "degraded",
            "headline": (
                "The factory is sick — failures across projects, not just this dump."
            ),
        }
    if project_rate is not None and project_rate >= 0.25:
        return {
            "verdict": "healthy",
            "headline": "This dump is failing; the factory looks fine.",
        }
    return {
        "verdict": "healthy",
        "headline": "Factory looks healthy.",
    }


def _query_annotations(grafana: Any, project_id: str) -> list[dict[str, Any]]:
    raw = grafana.get_annotations(tags=[project_annotation_tag(project_id)])
    parsed = _mcp_json(raw)
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    if isinstance(parsed, dict):
        for key in ("annotations", "result", "data"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _deeplink(grafana: Any) -> str | None:
    fn = getattr(grafana, "generate_deeplink", None)
    if not callable(fn):
        return None
    try:
        raw = fn(title="Martini Shot")
    except Exception:
        return None
    parsed = _mcp_json(raw)
    text = _mcp_text(raw)
    if isinstance(parsed, dict):
        for key in ("url", "link", "deeplink"):
            value = parsed.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
    if text.startswith("http"):
        return text.split()[0]
    return None


def _burn(jobs: list[Job]) -> dict[str, Any]:
    ranked = sorted(jobs, key=lambda job: int(job.cost_micros or 0), reverse=True)
    top = []
    for job in ranked[:3]:
        if int(job.cost_micros or 0) <= 0:
            continue
        top.append(
            {
                "job_id": job.id,
                "station": job.station,
                "cost_micros": int(job.cost_micros or 0),
                "why": _burn_why(job),
            }
        )
    if not top:
        return {
            "headline": "No metered work on this dump yet.",
            "top": [],
        }
    lead = top[0]
    return {
        "headline": (
            f"{lead['station']} on {lead['job_id']} is the expensive one — "
            f"{lead['why']}."
        ),
        "top": top,
    }


def _burn_why(job: Job) -> str:
    result = job.result or {}
    if result.get("omni_fallback"):
        return "Omni refused; Veo finished it"
    if int(job.attempts or 0) > 1:
        return f"retried {job.attempts} times"
    return f"{job.station} work"


def _eta(
    worklist: dict[str, Any],
    p50_by_station: dict[str, float],
    *,
    grafana_ok: bool,
) -> dict[str, Any]:
    items = [
        item
        for item in (worklist.get("items") or [])
        if isinstance(item, dict)
        and str(item.get("status") or "") in REMAINING_STATUSES
    ]
    remaining = len(items)
    if remaining == 0:
        return {
            "headline": "Nothing left in the worklist.",
            "eta_seconds": 0,
            "remaining_items": 0,
        }
    if not grafana_ok or not p50_by_station:
        return {
            "headline": (
                f"{remaining} item{'s' if remaining != 1 else ''} left; "
                "duration history unavailable."
            ),
            "eta_seconds": None,
            "remaining_items": remaining,
        }
    total = 0.0
    missing = False
    for item in items:
        station = str(item.get("station") or "")
        seconds = p50_by_station.get(station)
        if seconds is None:
            missing = True
            continue
        total += seconds
    if missing and total == 0:
        return {
            "headline": (f"{remaining} items left; duration history unavailable."),
            "eta_seconds": None,
            "remaining_items": remaining,
        }
    eta_seconds = int(round(total))
    minutes = max(1, int(round(eta_seconds / 60))) if eta_seconds >= 30 else 0
    if minutes:
        headline = f"About {minutes} min left for {remaining} remaining items."
    else:
        headline = f"About {eta_seconds}s left for {remaining} remaining items."
    return {
        "headline": headline,
        "eta_seconds": eta_seconds,
        "remaining_items": remaining,
    }


def _wheel_items(
    annotations: list[dict[str, Any]], jobs: list[Job]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_jobs: set[str] = set()
    for row in annotations:
        text = str(row.get("text") or "")
        job_id = _job_id_from_text(text)
        if job_id:
            seen_jobs.add(job_id)
        items.append(
            {
                "at": _iso_from_grafana_time(row.get("time") or row.get("created")),
                "kind": _wheel_kind(text),
                "text": text,
                "job_id": job_id,
            }
        )
    for job in jobs:
        if not (job.result or {}).get("omni_fallback"):
            continue
        if job.id in seen_jobs:
            continue
        items.append(
            {
                "at": job.updated_at,
                "kind": "fallback",
                "text": f"Omni refused; Veo finished job_id={job.id}",
                "job_id": job.id,
            }
        )
    return items


def _trace_enrich(grafana: Any, job_id: str) -> dict[str, dict[str, Any]]:
    if not job_id or not hasattr(grafana, "search_traces"):
        return {}
    raw = grafana.search_traces(f'{{span.pc.job_id="{job_id}"}}')
    parsed = _mcp_json(raw)
    text = _mcp_text(raw).lower()
    blob = json.dumps(parsed).lower() if parsed is not None else text
    extra: dict[str, Any] = {}
    if "omni" in blob or "fallback" in blob:
        extra["trace_note"] = "trace shows a model fallback on this job"
    return {job_id: extra} if extra else {}


def _apply_trace_enrich(
    burn: dict[str, Any], traces_by_job: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if not traces_by_job:
        return burn
    top = []
    for row in burn.get("top") or []:
        note = (traces_by_job.get(str(row.get("job_id") or "")) or {}).get("trace_note")
        if note and note.lower() not in str(row.get("why") or "").lower():
            row = {**row, "why": f"{row.get('why')}; {note}"}
        top.append(row)
    headline = burn.get("headline")
    if top:
        lead = top[0]
        headline = (
            f"{lead['station']} on {lead['job_id']} is the expensive one — "
            f"{lead['why']}."
        )
    return {**burn, "top": top, "headline": headline}


def _wheel_kind(text: str) -> str:
    lower = text.lower()
    if "spend throttle" in lower or "spend control" in lower:
        return "spend"
    if "omni" in lower or "fallback" in lower:
        return "fallback"
    if "approv" in lower:
        return "human"
    if "investigation" in lower or "verdict=" in lower:
        return "intervention"
    return "note"


def _job_id_from_text(text: str) -> str | None:
    match = _JOB_ID_RE.search(text)
    return match.group(1) if match else None


def _iso_from_grafana_time(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)) and value > 0:
        seconds = value / 1000 if value > 1e12 else float(value)
        return (
            datetime.fromtimestamp(seconds, tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    return ""
