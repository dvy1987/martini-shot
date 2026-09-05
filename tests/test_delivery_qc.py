"""H-1c — Delivery QC agent (TDD scope).

Deterministic surface: reading the REAL D-2/D-4 QC report off the job doc,
the QC finding schema (adds the breach/borderline/pass classification),
payload validation, prompt construction and the call wiring through the
single instrumented site. Judgment quality is EDD
(backend/evals/datasets/delivery_qc_judgment.jsonl, live run).
"""

import json

import pytest

from backend.supervisor.agents import delivery_qc as dqc


@pytest.fixture
def case() -> "object":
    from backend.supervisor.case import Case

    return Case(
        case_id="case-dqc-01",
        version=1,
        created_at="2026-09-04T00:00:00.000Z",
        trigger={"kind": "qc_breach", "job_id": "job-dqc-01", "station": "delivery"},
        evidence={},
    )


@pytest.fixture
def seeded_job_doc() -> dict:
    """Shape produced by the real delivery station run (run_delivery)."""
    return {
        "id": "job-dqc-01",
        "station": "delivery",
        "project_id": "proj-eval",
        "status": "quarantined",
        "result": {
            "lufs": -13.4,
            "delivery": {
                "destination": "streaming",
                "verdict": "fail",
                "violations": [
                    {"rule_id": "DEL-006", "message": "loudness -13.4 (fail_hot)"}
                ],
                "profile": {"loudness_target_lufs": -16.0},
            },
        },
    }


def test_read_qc_report_reads_real_d2_d4_output(env, seeded_job_doc) -> None:  # type: ignore[no-untyped-def]
    env.set_doc("it-jobs-dqc", "job-dqc-01", seeded_job_doc)
    report = dqc.read_qc_report(env, "job-dqc-01", jobs_collection="it-jobs-dqc")

    assert report["found"] is True
    assert report["delivery_report"]["verdict"] == "fail"
    assert report["delivery_report"]["violations"][0]["rule_id"] == "DEL-006"
    assert report["lufs"] == -13.4


def test_read_qc_report_records_absence(env) -> None:  # type: ignore[no-untyped-def]
    report = dqc.read_qc_report(env, "job-missing", jobs_collection="it-jobs-dqc")

    assert report["found"] is False
    assert report["delivery_report"] is None
    assert "missing" in str(report.get("note", "")).lower()


def test_validate_qc_finding_builds_typed_result(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-dqc-01",
        "classification": "genuine_breach",
        "claims": [
            {
                "text": "loudness 2.6 LU hot vs the -16.0 target",
                "evidence_ref": "pc-jobs/job-dqc-01.result.delivery.violations[DEL-006]",
                "confidence": "high",
            }
        ],
        "proposed_actions": [],
    }
    result = dqc.validate_qc_finding_payload(payload, case=case)

    assert result.finding.specialist == "delivery_qc"
    assert result.classification == "genuine_breach"
    assert result.finding.claims[0].confidence == "high"


@pytest.mark.parametrize(
    "bad_classification",
    ["fail", "Genuine_Breach", "alarm", ""],
)
def test_validate_rejects_unknown_classification(case, bad_classification) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-dqc-01",
        "classification": bad_classification,
        "claims": [{"text": "x", "evidence_ref": "y", "confidence": "low"}],
        "proposed_actions": [],
    }
    with pytest.raises(ValueError):
        dqc.validate_qc_finding_payload(payload, case=case)


def test_validate_rejects_missing_claims(case) -> None:  # type: ignore[no-untyped-def]
    payload = {"case_id": "case-dqc-01", "classification": "pass", "claims": []}
    with pytest.raises(ValueError):
        dqc.validate_qc_finding_payload(payload, case=case)


def test_validate_rejects_invented_command(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-dqc-01",
        "classification": "genuine_breach",
        "claims": [{"text": "x", "evidence_ref": "y", "confidence": "low"}],
        "proposed_actions": [
            {
                "command_name": "re_render_master",
                "args": {},
                "cost_estimate_micros": 0,
                "reversible": True,
            }
        ],
    }
    with pytest.raises(ValueError, match="registry"):
        dqc.validate_qc_finding_payload(payload, case=case)


def test_validate_rejects_foreign_case_id(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "another-case",
        "classification": "pass",
        "claims": [{"text": "x", "evidence_ref": "y", "confidence": "low"}],
        "proposed_actions": [],
    }
    with pytest.raises(ValueError, match="case_id"):
        dqc.validate_qc_finding_payload(payload, case=case)


def test_build_prompt_carries_real_report_and_rules(case, seeded_job_doc) -> None:  # type: ignore[no-untyped-def]

    qc_report = dqc.read_qc_report_from_doc(seeded_job_doc)
    prompt = dqc.build_qc_prompt(case, qc_report)

    assert "streaming" in prompt
    assert "DEL-006" in prompt
    assert "-16.0" in prompt
    assert "1.0 LU" in prompt  # the real tolerance, so borderline is judgeable
    assert "genuine_breach" in prompt
    assert "borderline_pass" in prompt
    assert "never override" in prompt.lower()
    # the registry command vocabulary is named (H-0 ground rule)
    assert "retry_job" in prompt


def test_investigate_wires_persona_schema_and_report(
    monkeypatch, case, seeded_job_doc, env
) -> None:  # type: ignore[no-untyped-def]
    from backend.core.config import get_settings

    env.set_doc("it-jobs-dqc", "job-dqc-01", seeded_job_doc)
    captured: dict = {}
    valid_json = json.dumps(
        {
            "case_id": "case-dqc-01",
            "classification": "genuine_breach",
            "claims": [
                {
                    "text": "loudness hot",
                    "evidence_ref": "pc-jobs/job-dqc-01.result.delivery",
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

    monkeypatch.setattr(dqc, "run_agent_call", fake_run_agent_call)
    result = dqc.investigate(
        case, get_settings(), store=env, jobs_collection="it-jobs-dqc"
    )

    assert result.classification == "genuine_breach"
    assert captured["persona"] == "delivery_qc"
    assert captured["span_name"] == "specialist.delivery_qc"
    assert captured["response_schema"] == dqc.QC_FINDING_SCHEMA
    assert "DEL-006" in captured["prompt"]  # the REAL report reached the model
