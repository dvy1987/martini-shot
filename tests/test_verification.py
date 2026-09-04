"""H-1e — Verification agent (TDD scope): the hard filter's judgment feed.

Deterministic surface: the verdict schema (approve|veto per claim, phantom
vetoes rejected), specialist-approval computed deterministically from the
rejected set, prompt construction, call wiring, and the DoD grep-test as a
real test: a vetoed finding's actions NEVER reach the ranked list through
run_deliberation_cycle. Judgment quality is EDD (verification_veto.jsonl).
"""

import json

import pytest

from backend.supervisor.agents import verification as vf


@pytest.fixture
def case() -> "object":
    from backend.supervisor.case import Case

    return Case(
        case_id="case-ver-01",
        version=1,
        created_at="2026-09-04T00:00:00.000Z",
        trigger={"kind": "job_failed", "job_id": "job-ver-01", "station": "ingest"},
        evidence={
            "job": {"id": "job-ver-01", "error": "checksum mismatch: sha256 ab12cf"}
        },
    )


def _findings() -> "list":
    from backend.supervisor.case import Claim, Finding, ProposedAction

    return [
        Finding(
            specialist="reliability_investigator",
            case_id="case-ver-01",
            claims=[
                Claim(
                    text="retry will clear it",
                    evidence_ref="pc-jobs/job-ver-01.error",
                    confidence="high",
                )
            ],
            proposed_actions=[
                ProposedAction(
                    command_name="retry_job",
                    args={"job_id": "job-ver-01"},
                    cost_estimate_micros=50000,
                    reversible=True,
                )
            ],
        ),
        Finding(
            specialist="delivery_qc",
            case_id="case-ver-01",
            claims=[
                Claim(
                    text="pack fine",
                    evidence_ref="pc-jobs/job-ver-01.result",
                    confidence="medium",
                )
            ],
            proposed_actions=[],
        ),
    ]


def test_validate_verdict_builds_typed_result(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-ver-01",
        "decision": "veto",
        "overall_confidence": "high",
        "rejected": [
            {
                "evidence_ref": "pc-jobs/job-ver-01.error",
                "reason": "claim contradicts the cited checksum-corruption error",
            }
        ],
    }
    verdict = vf.validate_verdict_payload(
        payload, case_id="case-ver-01", findings=_findings()
    )

    assert verdict.rejected == [
        (
            "pc-jobs/job-ver-01.error",
            "claim contradicts the cited checksum-corruption error",
        )
    ]
    # specialist approval is DETERMINISTIC from the rejected set
    assert verdict.approved_specialists == ["delivery_qc"]
    assert verdict.overall_confidence == "high"


def test_validate_rejects_phantom_veto(case) -> None:  # type: ignore[no-untyped-def]
    """The verifier cannot veto claims that do not exist in the findings."""
    payload = {
        "case_id": "case-ver-01",
        "decision": "approve",
        "overall_confidence": "high",
        "rejected": [{"evidence_ref": "made-up://ref", "reason": "because"}],
    }
    with pytest.raises(ValueError, match="phantom veto"):
        vf.validate_verdict_payload(
            payload, case_id="case-ver-01", findings=_findings()
        )


@pytest.mark.parametrize(
    "field,value",
    [("decision", "maybe"), ("overall_confidence", "certain")],
)
def test_validate_rejects_bad_enums(case, field, value) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-ver-01",
        "decision": "approve",
        "overall_confidence": "medium",
        "rejected": [],
    }
    payload[field] = value
    with pytest.raises(ValueError):
        vf.validate_verdict_payload(
            payload, case_id="case-ver-01", findings=_findings()
        )


def test_validate_rejects_empty_reason(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "case-ver-01",
        "decision": "veto",
        "overall_confidence": "high",
        "rejected": [{"evidence_ref": "pc-jobs/job-ver-01.error", "reason": "  "}],
    }
    with pytest.raises(ValueError, match="reason"):
        vf.validate_verdict_payload(
            payload, case_id="case-ver-01", findings=_findings()
        )


def test_validate_rejects_foreign_case_id(case) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "case_id": "other",
        "decision": "approve",
        "overall_confidence": "low",
        "rejected": [],
    }
    with pytest.raises(ValueError, match="case_id"):
        vf.validate_verdict_payload(
            payload, case_id="case-ver-01", findings=_findings()
        )


def test_build_prompt_carries_claims_and_case_evidence(case) -> None:  # type: ignore[no-untyped-def]
    prompt = vf.build_verification_prompt(case, _findings())

    assert "case-ver-01" in prompt
    assert "retry will clear it" in prompt
    assert "pc-jobs/job-ver-01.error" in prompt
    assert "checksum" in prompt  # the case evidence the claims must survive
    assert "delivery_qc" in prompt
    assert "veto" in prompt


def test_investigate_wires_persona_schema(monkeypatch, case) -> None:  # type: ignore[no-untyped-def]
    from backend.core.config import get_settings

    captured: dict = {}
    valid_json = json.dumps(
        {
            "case_id": "case-ver-01",
            "decision": "veto",
            "overall_confidence": "high",
            "rejected": [
                {
                    "evidence_ref": "pc-jobs/job-ver-01.error",
                    "reason": "claim contradicts the checksum corruption",
                }
            ],
        }
    )

    def fake_run_agent_call(settings, prompt, **kwargs):
        captured.update(kwargs)
        return {
            "model": "m",
            "text": valid_json,
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_micros": 10,
            "latency_ms": 1.0,
        }

    monkeypatch.setattr(vf, "run_agent_call", fake_run_agent_call)
    verdict = vf.verify(case, _findings(), get_settings())

    assert verdict.rejected[0][0] == "pc-jobs/job-ver-01.error"
    assert captured["persona"] == "verification_agent"
    assert captured["span_name"] == "specialist.verification"
    assert captured["response_schema"] == vf.VERIFICATION_SCHEMA


def test_hard_filter_wiring_rejected_actions_never_ranked(monkeypatch, case) -> None:  # type: ignore[no-untyped-def]
    """DoD grep-test, executable: through the REAL apply_verdict + rank_actions
    path, a vetoed finding's actions never reach the ranked list."""
    from backend.core.config import get_settings
    from backend.supervisor import deliberation as delib

    def fake_verify(case_arg, findings_arg, settings, **kwargs):
        return vf.validate_verdict_payload(
            {
                "case_id": case_arg.case_id,
                "decision": "veto",
                "overall_confidence": "high",
                "rejected": [
                    {
                        "evidence_ref": "pc-jobs/job-ver-01.error",
                        "reason": "contradicts evidence",
                    }
                ],
            },
            case_id=case_arg.case_id,
            findings=findings_arg,
        )

    monkeypatch.setattr(vf, "run_agent_call", lambda *a, **k: {"text": "{}"})
    monkeypatch.setattr(vf, "verify", fake_verify)

    findings = _findings()
    verdict = vf.verify(case, findings, get_settings())
    filtered = delib.apply_verdict(findings, verdict)
    ranked = delib.rank_actions(case, filtered)

    assert all(row["specialist"] != "reliability_investigator" for row in ranked)
    assert not any(
        row["specialist"] == "delivery_qc" and not row["command_name"] for row in ranked
    )
    # the surviving specialist's claims are intact
    assert [f.specialist for f in filtered] == ["delivery_qc"]
