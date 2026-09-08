"""Run Pulse: Grafana-backed finishing-run answers (C-2.2, C-4.*, C-6.5)."""

from __future__ import annotations

import json
from typing import Any

from backend.jobs.models import Job
from backend.jobs.telemetry import job_metric_labels
from backend.supervisor.annotate import annotation_tags
from backend.supervisor.mcp import GrafanaMcpConnector
from backend.supervisor.run_pulse import assemble_run_pulse, reset_run_pulse_cache
from tests.test_spend import _Store
from tests.test_supervisor_mcp import RecordingSession


def _job(**overrides: Any) -> Job:
    payload = {
        "station": "extend",
        "project_id": "proj-pulse",
        "input_refs": ["gs://b/a.mp4"],
        "id": "job-ext-1",
        "status": "passed",
        "attempts": 1,
        "cost_micros": 1_200_000,
        "result": {},
    }
    payload.update(overrides)
    return Job.from_dict(payload)


class PulseSession(RecordingSession):
    """Records MCP dispatches and returns canned Grafana JSON (unit only)."""

    def __init__(
        self,
        available: list[str],
        replies: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(available)
        self.replies = replies or {}

    async def call_tool(self, name: str, arguments: dict) -> dict:
        if name == "list_datasources" and name not in self.replies:
            return await RecordingSession.call_tool(self, name, arguments)
        self.calls.append((name, arguments))
        payload = self.replies.get(name, "ok")
        if callable(payload):
            payload = payload(arguments)
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        return {"content": [{"type": "text", "text": payload}], "isError": False}


def _connector(replies: dict[str, Any] | None = None) -> GrafanaMcpConnector:
    session = PulseSession(
        [
            "query_prometheus",
            "tempo_traceql-search",
            "get_annotations",
            "generate_deeplink",
            "list_datasources",
        ],
        replies=replies,
    )
    return GrafanaMcpConnector._for_session(session)


def test_annotation_tags_include_project_slice() -> None:
    job = _job()
    tags = annotation_tags(job)
    assert f"project:{job.project_id}" in tags
    assert f"job:{job.id}" in tags
    assert "martini-shot" in tags


def test_job_metric_labels_include_project_id() -> None:
    labels = job_metric_labels("loudness", "proj-pulse")
    assert labels == {"station": "loudness", "project_id": "proj-pulse"}


def test_wheel_lists_project_annotations_and_veo_fallback() -> None:
    reset_run_pulse_cache()
    store = _Store()
    fallback = _job(
        id="job-ext-2",
        cost_micros=800_000,
        attempts=2,
        result={"omni_fallback": True, "omni_error": "recitation"},
    )
    store.set_doc("pc-jobs", fallback.id, fallback.to_dict())
    grafana = _connector(
        {
            "get_annotations": [
                {
                    "id": 35,
                    "time": 1_725_000_000_000,
                    "text": (
                        "spend throttle job_id=job-runaway "
                        "project_id=proj-pulse station=extend"
                    ),
                    "tags": ["martini-shot", "spend", "project:proj-pulse"],
                }
            ],
        }
    )
    pulse = assemble_run_pulse(
        store,  # type: ignore[arg-type]
        "proj-pulse",
        grafana=grafana,
        worklist={"status": "running", "items": [], "spent_micros": 800_000},
    )
    kinds = {item["kind"] for item in pulse["wheel"]["items"]}
    assert "spend" in kinds
    assert "fallback" in kinds
    assert pulse["grafana"] == "ok"


def test_grafana_down_keeps_firestore_burn_and_eta_without_inventing_factory() -> None:
    reset_run_pulse_cache()
    store = _Store()
    job = _job()
    store.set_doc("pc-jobs", job.id, job.to_dict())
    pulse = assemble_run_pulse(
        store,  # type: ignore[arg-type]
        "proj-pulse",
        grafana=None,
        worklist={
            "status": "running",
            "spent_micros": job.cost_micros,
            "items": [
                {"id": "loud", "station": "loudness", "status": "waiting"},
            ],
        },
    )
    assert pulse["grafana"] == "unavailable"
    assert pulse["factory"]["verdict"] == "unknown"
    assert pulse["burn"]["top"][0]["job_id"] == job.id
    assert pulse["burn"]["top"][0]["cost_micros"] == job.cost_micros
    assert pulse["eta"]["remaining_items"] == 1
    assert pulse["eta"]["eta_seconds"] is None
    assert pulse["wheel"]["items"] == []


def test_factory_degraded_when_global_fail_rate_is_high() -> None:
    reset_run_pulse_cache()

    def promql(args: dict[str, Any]) -> dict[str, Any]:
        expr = str(args.get("expr") or "")
        if "project_id" in expr:
            return {
                "data": {
                    "resultType": "vector",
                    "result": [{"value": [0, "0.02"]}],
                }
            }
        return {
            "data": {
                "resultType": "vector",
                "result": [{"value": [0, "0.40"]}],
            }
        }

    grafana = _connector({"query_prometheus": promql, "get_annotations": []})
    pulse = assemble_run_pulse(
        _Store(),  # type: ignore[arg-type]
        "proj-pulse",
        grafana=grafana,
        worklist={"status": "running", "items": []},
    )
    assert pulse["factory"]["verdict"] == "degraded"
    assert "factory" in pulse["factory"]["headline"].lower()


def test_eta_multiplies_percentile_by_remaining_work() -> None:
    reset_run_pulse_cache()

    def promql(args: dict[str, Any]) -> dict[str, Any]:
        expr = str(args.get("expr") or "")
        if "histogram_quantile" in expr:
            return {
                "data": {
                    "resultType": "vector",
                    "result": [
                        {"metric": {"station": "loudness"}, "value": [0, "40"]},
                        {"metric": {"station": "extend"}, "value": [0, "10"]},
                    ],
                }
            }
        return {"data": {"resultType": "vector", "result": [{"value": [0, "0"]}]}}

    grafana = _connector({"query_prometheus": promql, "get_annotations": []})
    pulse = assemble_run_pulse(
        _Store(),  # type: ignore[arg-type]
        "proj-pulse",
        grafana=grafana,
        worklist={
            "status": "running",
            "items": [
                {"id": "a", "station": "loudness", "status": "waiting"},
                {"id": "b", "station": "loudness", "status": "queued"},
                {"id": "c", "station": "extend", "status": "passed"},
            ],
        },
    )
    assert pulse["eta"]["remaining_items"] == 2
    assert pulse["eta"]["eta_seconds"] == 80


def test_burn_headline_prefers_omni_fallback_over_raw_total() -> None:
    reset_run_pulse_cache()
    store = _Store()
    cheap = _job(id="job-loud", station="loudness", cost_micros=50_000)
    expensive = _job(
        id="job-ext-9",
        station="extend",
        cost_micros=4_000_000,
        attempts=3,
        result={"omni_fallback": True},
    )
    store.set_doc("pc-jobs", cheap.id, cheap.to_dict())
    store.set_doc("pc-jobs", expensive.id, expensive.to_dict())
    pulse = assemble_run_pulse(
        store,  # type: ignore[arg-type]
        "proj-pulse",
        grafana=None,
        worklist={"status": "done", "items": [], "spent_micros": 4_050_000},
    )
    top = pulse["burn"]["top"][0]
    assert top["job_id"] == "job-ext-9"
    assert "veo" in top["why"].lower() or "omni" in top["why"].lower()
    assert "4_050_000" not in pulse["burn"]["headline"]


def test_deeplink_lands_on_factory_evidence() -> None:
    reset_run_pulse_cache()
    grafana = _connector(
        {
            "query_prometheus": {"data": {"result": []}},
            "get_annotations": [],
            "generate_deeplink": {
                "url": "https://chipperm.grafana.net/d/pc-station-health"
            },
        }
    )
    pulse = assemble_run_pulse(
        _Store(),  # type: ignore[arg-type]
        "proj-pulse",
        grafana=grafana,
        worklist={"status": "running", "items": []},
        stack_url="https://chipperm.grafana.net",
    )
    assert pulse["factory"].get("evidence_url", "").startswith("https://")
    titles = {row["title"] for row in pulse["dashboards"]}
    assert titles == {"Station Health", "Finishing Cost", "Interventions"}
    assert all(
        row["url"].startswith("https://chipperm.grafana.net/d/")
        for row in pulse["dashboards"]
    )


def test_pulse_cache_skips_second_grafana_read() -> None:
    reset_run_pulse_cache()
    session = PulseSession(
        [
            "query_prometheus",
            "get_annotations",
            "list_datasources",
        ],
        replies={"query_prometheus": {"data": {"result": []}}, "get_annotations": []},
    )
    grafana = GrafanaMcpConnector._for_session(session)
    kwargs: dict[str, Any] = {
        "grafana": grafana,
        "worklist": {"status": "running", "items": []},
        "now": 100.0,
    }
    assemble_run_pulse(_Store(), "proj-pulse", **kwargs)  # type: ignore[arg-type]
    first = len(session.calls)
    assemble_run_pulse(_Store(), "proj-pulse", **kwargs)  # type: ignore[arg-type]
    assert len(session.calls) == first
    assemble_run_pulse(
        _Store(), "proj-pulse", grafana=grafana, worklist={"items": []}, now=116.0
    )  # type: ignore[arg-type]
    assert len(session.calls) > first
