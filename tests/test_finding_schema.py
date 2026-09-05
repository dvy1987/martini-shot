"""Finding-schema gate: action target binding + validation (TDD, RED-first).

ACT-gate review fixes: action correctness is enforced deterministically.
- REQUIRED_ACTION_ARGS: an action whose args lack its command's required
  target keys is rejected outright (never ranks, never dispatches).
- Target binding: for an action about the CASE'S SUBJECT (the job the
  specialist was dispatched to investigate), the target is structurally
  determined — the gate binds a missing job_id from the case evidence
  rather than failing the whole finding on a formatting slip. It can never
  mis-bind: only the case's own subject is bound; an action about any OTHER
  job must have carried its id explicitly.
"""

from __future__ import annotations

import pytest

from backend.supervisor.agents.finding_schema import (
    validate_finding_payload,
)


def _payload(**action_overrides):
    action = {
        "command_name": "retry_job",
        "args": {},
        "cost_estimate_micros": 41200,
        "reversible": True,
        "supporting_evidence_refs": ["firestore://pc-jobs/job-1"],
        **action_overrides,
    }
    return {
        "case_id": "case-1",
        "claims": [
            {
                "text": "loudness gate breached",
                "evidence_ref": "firestore://pc-jobs/job-1",
                "confidence": "high",
            }
        ],
        "proposed_actions": [action],
    }


def test_missing_target_args_bind_to_the_case_subject() -> None:
    """The investigated job IS the target: a job-scoped action with empty
    args is bound to the case's subject job_id at the gate (deterministic,
    from case structure — never model guesswork)."""
    finding = validate_finding_payload(
        _payload(),
        case_id="case-1",
        specialist="reliability_investigator",
        subject_job_id="job-1",
    )

    assert finding.proposed_actions[0].args == {"job_id": "job-1"}


def test_action_targeting_another_job_must_carry_its_own_id() -> None:
    """Only the case's own subject is bindable; a different target must be
    explicit, or the gate refuses."""
    payload = _payload(args={"job_id": "job-other"})
    finding = validate_finding_payload(
        payload,
        case_id="case-1",
        specialist="reliability_investigator",
        subject_job_id="job-1",
    )
    assert finding.proposed_actions[0].args == {"job_id": "job-other"}


def test_job_scoped_action_with_no_bindable_subject_is_refused() -> None:
    with pytest.raises(ValueError, match="missing required target keys"):
        validate_finding_payload(
            _payload(),
            case_id="case-1",
            specialist="reliability_investigator",
            subject_job_id=None,
        )
