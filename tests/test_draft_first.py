"""D-11 Draft-first state machine — master requires a QC-passing draft."""

from __future__ import annotations

import pytest

from backend.stations.draft_first import (
    MasterNotEligibleError,
    assert_master_eligible,
    cost_delta_micros,
    evaluate_readiness,
)


def test_master_rejected_without_eligible_draft() -> None:
    with pytest.raises(MasterNotEligibleError, match="QC-passing draft"):
        assert_master_eligible(
            [{"op": "correction", "status": "draft", "eval_scores": {"flicker": 0.9}}],
            op="correction",
        )


def test_master_eligible_when_draft_clears_bars() -> None:
    draft = {
        "alternate_id": "alt-ok",
        "op": "relight",
        "status": "draft",
        "created_at": "2026-09-07T00:00:00Z",
        "eval_scores": {"flicker": 0.003, "vision_judge": 4.2},
    }
    assert assert_master_eligible([draft], op="relight")["alternate_id"] == "alt-ok"
    readiness = evaluate_readiness(op="relight", alternates=[draft], revision_count=0)
    assert readiness.state == "master_eligible"


def test_failed_draft_revises_once_then_escalates() -> None:
    failed = {
        "op": "coverage",
        "status": "draft",
        "created_at": "2026-09-07T00:00:00Z",
        "eval_scores": {"flicker": 0.4},
    }
    assert (
        evaluate_readiness(op="coverage", alternates=[failed], revision_count=0).state
        == "revise"
    )
    assert (
        evaluate_readiness(op="coverage", alternates=[failed], revision_count=1).state
        == "escalate"
    )


def test_draft_first_agent_cannot_authorize_ineligible_master() -> None:
    import json

    from backend.supervisor.station_agents.draft_first import (
        parse_draft_first_decision,
    )

    decision = parse_draft_first_decision(
        json.dumps(
            {
                "agent": "draft_first",
                "decision": "authorize_master",
                "reason": "looks fine to me",
                "confidence": "high",
                "proposal": {
                    "command_name": "render_master",
                    "args": {"shot_id": "s", "project_id": "p", "op": "correction"},
                },
            }
        ),
        op="correction",
        alternates=[],
        revision_count=0,
    )
    assert decision.decision == "wait"
    assert decision.overridden is True


def test_cost_delta_is_integer_micros() -> None:
    assert cost_delta_micros(233_338, 700_000) == 466_662


def test_visual_qc_maps_promote_to_master_eligible() -> None:
    from backend.stations.draft_first import map_visual_qc_decision

    assert map_visual_qc_decision("promote", revision_count=0) == "master_eligible"
    assert map_visual_qc_decision("bounded_revision", revision_count=0) == "revise"
    assert map_visual_qc_decision("bounded_revision", revision_count=1) == "escalate"
    assert map_visual_qc_decision("abstain", revision_count=0) == "escalate"


def test_flicker_only_metrics_can_promote() -> None:
    from backend.supervisor.station_agents.visual_qc import suggestion_for_metrics

    assert suggestion_for_metrics({"flicker": 0.003}) == "promote"
    assert suggestion_for_metrics({"flicker": 0.4}) == "bounded_revision"
    assert suggestion_for_metrics(None) == "abstain"


def test_apply_draft_qc_stamps_master_eligible_without_live_gemini() -> None:
    from backend.jobs.models import Job
    from backend.supervisor.finishing_loop import apply_draft_qc

    job = Job(
        station="relight",
        project_id="p",
        input_refs=["gs://b/a.mp4"],
        result={
            "shot_id": "shot-a",
            "worklist_item": "relight::shot-a",
            "flicker": 0.001,
            "preset": "noir",
            "alternate_id": "alt-1",
            "tier": "draft",
        },
    )
    job.status = "passed"
    job.cost_micros = 233_338
    doc = {
        "items": [
            {
                "id": "relight::shot-a",
                "station": "relight",
                "status": "passed",
                "job_id": job.id,
                "shot_id": "shot-a",
            }
        ]
    }
    out = apply_draft_qc(doc, job, settings=None, store=None)
    assert job.result["draft_state"] == "master_eligible"
    assert job.result["visual_qc"] == "promote"
    assert out["items"][0]["master_eligible"] is True
    assert int(job.result["cost_delta_micros"]) > 0


def test_apply_draft_qc_enqueues_one_bounded_revision() -> None:
    from backend.jobs.models import Job
    from backend.supervisor.finishing_loop import apply_draft_qc

    job = Job(
        station="relight",
        project_id="p",
        input_refs=["gs://b/a.mp4"],
        result={
            "shot_id": "shot-a",
            "worklist_item": "relight::shot-a",
            "flicker": 0.4,
            "preset": "noir",
            "tier": "draft",
            "revision_count": 0,
        },
    )
    job.status = "passed"
    doc = {
        "items": [
            {
                "id": "relight::shot-a",
                "station": "relight",
                "status": "passed",
                "job_id": job.id,
                "shot_id": "shot-a",
            }
        ]
    }
    out = apply_draft_qc(doc, job, settings=None, store=None)
    assert job.result["draft_state"] == "revise"
    retry = [item for item in out["items"] if str(item.get("id")).endswith("::revise")]
    assert len(retry) == 1
    assert retry[0]["status"] == "waiting"
    assert retry[0]["proposal"]["args"]["revision_count"] == 1
