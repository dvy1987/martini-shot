"""H-1d — Spend Guardian agent (TDD scope).

Deterministic surface: reading REAL Spend Control state (the station's own
policies.yaml + Firestore job rows via the same detect helpers), the spend
assessment schema (reasonable | underpriced | over_budget), payload
validation, prompt construction and the call wiring. Judgment quality is
EDD (spend_guardian_judgment.jsonl, live run).
"""

import json

import pytest

from backend.supervisor.agents import spend_guardian as sg


@pytest.fixture
def case() -> "object":
    from backend.supervisor.case import Case

    return Case(
        case_id="case-sg-01",
        version=1,
        created_at="2026-09-04T00:00:00.000Z",
        trigger={"kind": "spend_breach", "job_id": "job-sg-01", "station": "loudness"},
        evidence={},
    )


def test_read_spend_state_uses_real_policy_and_rows(env) -> None:  # type: ignore[no-untyped-def]
    env.set_doc(
        "it-jobs-sg",
        "job-sg-01",
        {
            "id": "job-sg-01",
            "station": "loudness",
            "project_id": "proj-sg",
            "status": "failed",
            "attempts": 2,
            "cost_micros": 800000,
        },
    )
    state = sg.read_spend_state(
        env, project_id="proj-sg", station="loudness", jobs_collection="it-jobs-sg"
    )

    # REAL policy caps from backend/stations/spend/policies.yaml
    assert state["policy"]["max_retries"] == 2
    assert state["policy"]["max_cost_micros_per_job"] == 1000000
    assert state["policy"]["runaway_requeues"] == 8
    # REAL budgets + aggregation through the station's own detect helpers
    assert state["budgets"]["daily_budget_micros"] == 500000000
    assert state["station_spent_micros"] == 800000
    assert state["jobs"][0]["attempts"] == 2


def test_read_spend_state_excludes_other_stations(env) -> None:  # type: ignore[no-untyped-def]
    env.set_doc(
        "it-jobs-sg",
        "job-a",
        {
            "id": "job-a",
            "station": "loudness",
            "project_id": "proj-sg2",
            "status": "failed",
            "attempts": 1,
            "cost_micros": 111,
        },
    )
    env.set_doc(
        "it-jobs-sg",
        "job-b",
        {
            "id": "job-b",
            "station": "ingest",
            "project_id": "proj-sg2",
            "status": "failed",
            "attempts": 1,
            "cost_micros": 999,
        },
    )
    state = sg.read_spend_state(
        env, project_id="proj-sg2", station="loudness", jobs_collection="it-jobs-sg"
    )

    assert [j["job_id"] for j in state["jobs"]] == ["job-a"]
    assert state["station_spent_micros"] == 111


def test_validate_assessment_builds_typed_result(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-sg-01",
        "assessment": "underpriced",
        "claims": [
            {
                "text": "both retries already spent; 100k estimate ignores history",
                "evidence_ref": "pc-jobs/job-sg-01.attempts=2",
                "confidence": "high",
            }
        ],
        "proposed_actions": [],
    }
    result = sg.validate_assessment_payload(payload, case=case)

    assert result.finding.specialist == "spend_guardian"
    assert result.assessment == "underpriced"


@pytest.mark.parametrize("bad", ["cheap", "OK", "", "underpriced!"])
def test_validate_rejects_unknown_assessment(case, bad) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-sg-01",
        "assessment": bad,
        "claims": [{"text": "x", "evidence_ref": "y", "confidence": "low"}],
        "proposed_actions": [],
    }
    with pytest.raises(ValueError):
        sg.validate_assessment_payload(payload, case=case)


def test_validate_rejects_invented_command(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-sg-01",
        "assessment": "reasonable",
        "claims": [{"text": "x", "evidence_ref": "y", "confidence": "low"}],
        "proposed_actions": [
            {
                "command_name": "slash_budget",
                "args": {},
                "cost_estimate_micros": 0,
                "reversible": True,
            }
        ],
    }
    with pytest.raises(ValueError, match="registry"):
        sg.validate_assessment_payload(payload, case=case)


def test_validate_rejects_foreign_case_id(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "nope",
        "assessment": "reasonable",
        "claims": [{"text": "x", "evidence_ref": "y", "confidence": "low"}],
        "proposed_actions": [],
    }
    with pytest.raises(ValueError, match="case_id"):
        sg.validate_assessment_payload(payload, case=case)


def test_build_prompt_carries_real_caps_and_proposal(case) -> None:  # type: ignore[no-untyped-def]
    state = sg.read_spend_state(
        store=None,
        project_id="proj-sg",
        station="loudness",
        jobs=[
            {
                "id": "job-sg-01",
                "station": "loudness",
                "status": "failed",
                "attempts": 2,
                "cost_micros": 800000,
            }
        ],
    )
    proposal = {
        "command_name": "retry_job",
        "args": {"job_id": "job-sg-01"},
        "cost_estimate_micros": 100000,
    }
    prompt = sg.build_spend_prompt(case, state, proposal)

    assert "1000000" in prompt  # per-job cap from the real policies.yaml
    assert "runaway_requeues" in prompt
    assert "500000000" in prompt  # daily budget from the real policies.yaml
    assert "retry_job" in prompt
    assert "100000" in prompt  # the proposal's own cost estimate
    assert "underpriced" in prompt
    assert "over_budget" in prompt


def test_investigate_wires_persona_schema(monkeypatch, case) -> None:  # type: ignore[no-untyped-def]
    from backend.core.config import get_settings

    state = sg.read_spend_state(store=None, project_id="p", station="loudness", jobs=[])
    proposal = {"command_name": "retry_job", "args": {}, "cost_estimate_micros": 1}
    captured: dict = {}
    valid_json = json.dumps(
        {
            "case_id": "case-sg-01",
            "assessment": "underpriced",
            "claims": [
                {
                    "text": "x",
                    "evidence_ref": "policies.yaml:loudness",
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

    monkeypatch.setattr(sg, "run_agent_call", fake_run_agent_call)
    result = sg.investigate(case, get_settings(), spend_state=state, proposal=proposal)

    assert result.assessment == "underpriced"
    assert captured["persona"] == "spend_guardian"
    assert captured["span_name"] == "specialist.spend_guardian"
    assert captured["response_schema"] == sg.SPEND_FINDING_SCHEMA
    assert "runaway_requeues" in captured["prompt"]
