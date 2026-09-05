"""H-1b — Reliability Investigator agent (TDD scope).

Deterministic surface only: the read-only Grafana tool allowlist, the
finding JSON-schema contract, payload validation, prompt construction and
the call wiring through the single instrumented site (`run_agent_call`).
Judgment quality is EDD (backend/evals/datasets/reliability_root_cause.jsonl).
"""

import json

import pytest

from backend.supervisor.agents import reliability_investigator as ri


@pytest.fixture
def case() -> "object":
    from backend.supervisor.case import Case

    return Case(
        case_id="case-test-01",
        version=1,
        created_at="2026-09-04T00:00:00.000Z",
        trigger={
            "kind": "job_failed",
            "job_id": "job-rel-eval-01",
            "station": "loudness",
        },
        evidence={
            "job": {
                "id": "job-rel-eval-01",
                "station": "loudness",
                "error": "loudness gate breached",
            }
        },
    )


def test_read_only_allowlist_excludes_write_tools() -> None:
    """C-2.1/C-4.3: specialists hold zero act-class tools. The allowlist must
    never contain annotation/incident write tools."""
    write_tools = {"add_annotation", "create_incident"}
    assert write_tools.isdisjoint(set(ri.READ_ONLY_GRAFANA_TOOLS))
    assert set(ri.READ_ONLY_GRAFANA_TOOLS) <= {
        "search_dashboards",
        "query_promql",
        "query_loki",
        "search_traces",
        "get_annotations",
        "list_incidents",
        "get_incident",
    }


def test_read_only_tool_binder_never_binds_write_methods() -> None:
    """The binder maps only allowlisted plan tools onto connector methods,
    whatever the connector exposes."""

    class FakeConnector:
        available_tools = ["query_promql", "add_annotation", "create_incident"]

        def query_promql(self, query: str) -> dict:
            return {}

        def add_annotation(self, text: str) -> dict:  # pragma: no cover
            return {}

        def create_incident(self, *a: object) -> dict:  # pragma: no cover
            return {}

    bound = ri.read_only_grafana_tools(FakeConnector())
    assert [fn.__name__ for fn in bound] == ["query_promql"]


def test_validate_finding_payload_builds_typed_finding(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-test-01",
        "claims": [
            {
                "text": "integrated loudness -13.4 LUFS breaches the -16.0 gate",
                "evidence_ref": "pc-jobs/job-rel-eval-01.result.integrated_lufs",
                "confidence": "high",
            }
        ],
        "proposed_actions": [
            {
                "command_name": "retry_job",
                "args": {"job_id": "job-rel-eval-01"},
                "cost_estimate_micros": 41200,
                "reversible": True,
            }
        ],
    }
    finding = ri.validate_finding_payload(payload, case=case)
    assert finding.specialist == "reliability_investigator"
    assert finding.case_id == "case-test-01"
    assert finding.claims[0].confidence == "high"
    assert finding.proposed_actions[0].command_name == "retry_job"


@pytest.mark.parametrize(
    "mutation",
    [
        {"claims": []},  # no claims = no evidence = not a finding
        {
            "claims": [{"text": "x", "evidence_ref": "", "confidence": "high"}]
        },  # empty evidence
        {
            "claims": [{"text": "x", "evidence_ref": "y", "confidence": "certain"}]
        },  # bad confidence
        {
            "proposed_actions": [
                {
                    "command_name": "delete_everything",
                    "args": {},
                    "cost_estimate_micros": 0,
                    "reversible": True,
                }
            ]
        },  # invented command (not in H-0 registry)
        {
            "proposed_actions": [
                {"command_name": "retry_job", "args": {}, "cost_estimate_micros": 1}
            ]
        },  # missing reversibility flag
    ],
)
def test_validate_finding_payload_rejects_malformed(case, mutation) -> None:  # type: ignore[no-untyped-def]
    payload: dict = {
        "claims": [
            {"text": "ok", "evidence_ref": "pc-jobs/job-1", "confidence": "low"}
        ],
        "proposed_actions": [],
    }
    payload.update(mutation)
    with pytest.raises(ValueError):
        ri.validate_finding_payload(payload, case=case)


def test_validate_rejects_foreign_case_id(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "some-other-case",
        "claims": [{"text": "x", "evidence_ref": "y", "confidence": "low"}],
        "proposed_actions": [],
    }
    with pytest.raises(ValueError, match="case_id"):
        ri.validate_finding_payload(payload, case=case)


def test_build_prompt_names_case_evidence_and_rules(case) -> None:  # type: ignore[no-untyped-def]
    prompt = ri.build_investigation_prompt(case)
    assert "case-test-01" in prompt
    assert "job-rel-eval-01" in prompt
    assert "loudness" in prompt
    assert "retry_job" in prompt  # the registry command vocabulary is named


def test_investigate_goes_through_run_agent_call(monkeypatch, case) -> None:  # type: ignore[no-untyped-def]
    from backend.core.config import get_settings

    captured: dict = {}
    valid_json = json.dumps(
        {
            "case_id": "case-test-01",
            "claims": [
                {
                    "text": "loudness gate breached",
                    "evidence_ref": "pc-jobs/job-rel-eval-01",
                    "confidence": "high",
                }
            ],
            "proposed_actions": [],
        }
    )

    def fake_run_agent_call(settings, prompt, **kwargs):
        captured.update(kwargs)
        captured["prompt"] = prompt
        return {
            "model": "m",
            "text": valid_json,
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_micros": 10,
            "latency_ms": 1.0,
        }

    monkeypatch.setattr(ri, "run_agent_call", fake_run_agent_call)
    finding = ri.investigate(case, get_settings())

    assert isinstance(finding, ri.Finding)
    assert captured["persona"] == "reliability_investigator"
    assert captured["span_name"] == "specialist.reliability_investigator"
    assert captured["response_schema"] == ri.FINDING_SCHEMA


def test_investigate_fails_loud_on_bad_json(monkeypatch, case) -> None:  # type: ignore[no-untyped-def]
    """C-1.1: a malformed model response must raise, never degrade to an
    invented or empty finding."""
    from backend.core.config import get_settings

    def fake_run_agent_call(settings, prompt, **kwargs):
        return {
            "model": "m",
            "text": "not json at all",
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_micros": 10,
            "latency_ms": 1.0,
        }

    monkeypatch.setattr(ri, "run_agent_call", fake_run_agent_call)
    with pytest.raises(ValueError):
        ri.investigate(case, get_settings())
