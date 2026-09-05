"""H-0b budgeted autonomy loop — dispatch mechanics (TDD, RED-first).

The loop is a CALLER of H-0, not a second brain: candidates flow through the
same ApprovalStateMachine (self-approving, `system:supervisor_budget`), the
nightly envelope is the sole quantity bound (owner ruling: no action-count
cap), Spend Control's daily house cap stays above it, and a human decision on
a target stands for the rest of the night (human-wins rule).

Real Firestore (C-6.2), per-run collections; Harness reused from the
executor suite.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from backend.approvals.machine import propose_approval
from backend.jobs.models import utc_now_iso
from backend.supervisor import budget_loop
from backend.supervisor.budget_loop import (
    SUPERVISOR_APPROVER,
    load_envelope_micros,
    run_budgeted_dispatch,
    supervisor_spend_micros,
)
from tests.test_approval_executor import Harness

pytestmark = pytest.mark.integration


def _action(
    name: str = "remediate",
    cost: Any = 2_000_000,
    job_id: str | None = None,
    **args: Any,
) -> dict[str, Any]:
    return {
        "command_name": name,
        "args": {"job_id": job_id, **args} if job_id else dict(args),
        "cost_estimate_micros": cost,
        "reversible": True,
        "specialist": "reliability_investigator",
        "evidence_refs": ["job://job-1"],
        "leverage": 1.0,
    }


@pytest.fixture()
def h(env, approvals_col, jobs_col):
    harness = Harness(env, approvals_col, jobs_col)
    # The real spend equals the candidate's estimate (draft-first pricing);
    # the loop reconciles from the approval's result, so the behavior echoes
    # the budget claim it was dispatched with.
    harness.register_fast(
        "remediate",
        lambda ctx, ap: {
            "ok": True,
            "cost_micros": int(ap.get("budget_cost_micros") or 0),
        },
    )
    harness.register_fast(
        "cheap_fix", lambda ctx, ap: {"ok": True, "cost_micros": 500_000}
    )
    # Per-run ACT-gate control collection, pre-seeded with a CURRENT-version
    # passing receipt — dispatch-mechanics tests exercise ACT assuming the
    # eval gate holds; the fail-closed tests use fresh/unseeded collections.
    harness.gate_col = f"it-gate-{uuid.uuid4().hex[:8]}"
    harness.store.set_doc(
        harness.gate_col,
        budget_loop.ACT_GATE_DOC,
        {
            "passed": True,
            "gate_version": budget_loop.ACT_GATE_VERSION,
            "suite": budget_loop.ACT_GATE_SUITE,
            "threshold": 0.8,
            "runs": 3,
        },
    )
    return harness


def _act(
    h,
    actions,
    *,
    env="act",
    policies=None,
    jobs_col="it-jobs-x",
    envelope_collection=None,
    gate_collection=None,
    **kwargs,
):
    return run_budgeted_dispatch(
        h.store,
        h.machine,
        actions,
        project_id="proj-1",
        approvals_col=h.approvals_col,
        jobs_col=jobs_col,
        policies=policies or {},
        autonomy_mode=env,
        annotator=h._annotate,
        **({"envelope_collection": envelope_collection} if envelope_collection else {}),
        **{
            "gate_collection": gate_collection
            if gate_collection is not None
            else h.gate_col
        },
        **kwargs,
    )


def test_act_mode_self_approves_down_the_ranked_list(h, approvals_col):
    summary = _act(h, [_action(job_id="job-1"), _action(job_id="job-2")])

    assert [d["decision"] for d in summary["decisions"]] == ["dispatched", "dispatched"]
    approvals = h.store.list_where(approvals_col, "project_id", "proj-1")
    assert len(approvals) == 2
    assert all(ap["approver"] == SUPERVISOR_APPROVER for ap in approvals)
    assert all(ap["status"] == "resolved" for ap in approvals)
    assert summary["spent_micros"] == 4_000_000


def test_envelope_is_the_only_quantity_bound_and_stops_the_list(h):
    summary = _act(
        h,
        [
            _action(job_id="job-1", cost=6_000_000),
            _action(job_id="job-2", cost=6_000_000),
        ],
        envelope_override=10_000_000,
    )

    assert summary["decisions"][0]["decision"] == "dispatched"
    assert summary["decisions"][1] == {
        **summary["decisions"][1],
        "decision": "skipped",
        "reason": "nightly envelope exhausted",
    }
    assert summary["envelope_micros"] == 10_000_000


def test_consecutive_cycles_share_one_nightly_envelope(h):
    first = _act(
        h, [_action(job_id="job-1", cost=6_000_000)], envelope_override=10_000_000
    )
    second = _act(
        h, [_action(job_id="job-2", cost=6_000_000)], envelope_override=10_000_000
    )

    assert first["decisions"][0]["decision"] == "dispatched"
    assert second["decisions"][0]["reason"] == "nightly envelope exhausted"


def test_daily_house_cap_halts_spend_even_with_envelope_room(h, jobs_col):
    # Real project spend today: 4M against a 5M house cap.
    h.store.set_doc(
        jobs_col,
        "job-real-1",
        {
            "project_id": "proj-1",
            "station": "extend",
            "status": "passed",
            "cost_micros": 4_000_000,
            "updated_at": utc_now_iso(),
        },
    )
    policies = {"project": {"daily_budget_micros": 5_000_000}}
    summary = _act(
        h,
        [_action(job_id="job-1", cost=2_000_000)],
        policies=policies,
        jobs_col=jobs_col,
        envelope_override=20_000_000,
    )

    assert summary["decisions"][0]["decision"] == "skipped"
    assert summary["decisions"][0]["reason"] == "daily house cap"
    # Nothing was dispatched, so nothing new was approved.
    assert h.store.list_where(h.approvals_col, "project_id", "proj-1") == []


def test_garbage_or_negative_cost_is_never_dispatchable(h):
    summary = _act(
        h,
        [
            _action(job_id="job-1", cost=-5),
            _action(job_id="job-2", cost="not-a-number"),
            _action(job_id="job-3", cost=0),
        ],
    )

    assert all(d["decision"] == "skipped" for d in summary["decisions"])
    assert all(d["reason"] == "no credible cost estimate" for d in summary["decisions"])
    assert h.store.list_where(h.approvals_col, "project_id", "proj-1") == []


def test_human_wins_rule_loop_cannot_refight_a_human_decision(h, approvals_col):
    # A human already decided on this exact target tonight (a revert).
    propose_approval(
        h.store,
        {
            "project_id": "proj-1",
            "kind": "fix",
            "title": "Human revert",
            "command": {"name": "remediate", "args": {"job_id": "job-1"}},
        },
        collection=approvals_col,
    )
    ap_id = h.store.list_where(approvals_col, "project_id", "proj-1")[0]["approval_id"]
    h.machine.dispatch(ap_id, "approve", approver="human-1")

    summary = _act(h, [_action(name="remediate", job_id="job-1")])

    assert summary["decisions"][0]["decision"] == "skipped"
    assert (
        summary["decisions"][0]["reason"] == "human already decided this target tonight"
    )
    assert h.handler_calls == 1, "the loop must not re-run the human's target"


def test_propose_only_mode_records_ranked_proposals_and_dispatches_nothing(
    h, approvals_col
):
    summary = _act(
        h, [_action(job_id="job-1"), _action(job_id="job-2")], env="propose_only"
    )

    assert all(
        d["decision"] == "skipped" and d["reason"] == "autonomy: propose_only"
        for d in summary["decisions"]
    )
    assert summary["decisions"][0]["ranked_for_morning_report"] is True
    assert h.store.list_where(approvals_col, "project_id", "proj-1") == []
    assert h.handler_calls == 0


def test_act_mode_without_a_passing_gate_receipt_is_fail_closed_to_propose_only(
    h, approvals_col
):
    """ACT-gate review fix 3: 'act' in the settings doc alone must NOT unlock
    spending. A versioned passing eval receipt (pc-control/act-gate) is
    required; without it the loop demotes to propose-only."""
    empty_gate_col = f"it-gate-{uuid.uuid4().hex[:8]}"
    summary = _act(
        h, [_action(job_id="job-1")], env="act", gate_collection=empty_gate_col
    )

    assert summary["mode"] == "propose_only"
    assert all(d["reason"].startswith("act gate:") for d in summary["decisions"])
    assert h.store.list_where(approvals_col, "project_id", "proj-1") == []
    assert h.handler_calls == 0


def test_act_mode_with_a_stale_gate_receipt_is_refused(h):
    stale_col = f"it-gate-{uuid.uuid4().hex[:8]}"
    h.store.set_doc(
        stale_col,
        budget_loop.ACT_GATE_DOC,
        {
            "passed": True,
            "gate_version": budget_loop.ACT_GATE_VERSION - 1,
            "suite": budget_loop.ACT_GATE_SUITE,
        },
    )
    summary = _act(h, [_action(job_id="job-1")], env="act", gate_collection=stale_col)

    assert summary["mode"] == "propose_only"
    assert all(d["reason"].startswith("act gate:") for d in summary["decisions"])


def test_act_mode_with_a_current_passing_gate_receipt_dispatches(h):
    summary = _act(h, [_action(job_id="job-1")], env="act")

    assert summary["mode"] == "act"
    assert summary["decisions"][0]["decision"] == "dispatched"


def test_envelope_round_trips_from_firestore_without_redeploy(h, run_id):
    # Per-run control doc: the shared pc-control/budget doc is production
    # state and must never be mutated by a test.
    col = f"it-control-{run_id}"
    assert load_envelope_micros(h.store, collection=col) == 20_000_000  # owner default
    h.store.set_doc(
        col,
        budget_loop.SETTINGS_DOC,
        {"post_command_budget_micros": 5_000_000},
    )
    assert load_envelope_micros(h.store, collection=col) == 5_000_000
    summary = _act(
        h,
        [_action(job_id="job-1", cost=6_000_000)],
        envelope_collection=col,
    )
    assert summary["decisions"][0]["reason"] == "nightly envelope exhausted"
    assert summary["envelope_micros"] == 5_000_000


def test_supervisor_spend_counts_self_approved_actions_only(h, approvals_col):
    _act(h, [_action(job_id="job-1", cost=2_000_000)])
    # A human approval with real job spend must NOT count toward the
    # supervisor's narrower counter.
    human_ap = propose_approval(
        h.store,
        {
            "project_id": "proj-1",
            "kind": "fix",
            "title": "Human action",
            "command": {"name": "cheap_fix", "args": {"job_id": "job-9"}},
        },
        collection=approvals_col,
    )
    h.machine.dispatch(human_ap, "approve", approver="human-1")

    spent = supervisor_spend_micros(h.store, h.approvals_col, "it-jobs-x")
    assert spent == 2_000_000


def test_budgeted_cycle_end_to_end_collect_rank_dispatch_persist(
    h, approvals_col, jobs_col
):
    """Signal-fired cycle: a real stuck job → specialist finding → verified
    ranking → self-approved dispatch under the envelope → decision table
    persisted on the cycle doc."""
    from backend.core.config import get_settings
    from backend.supervisor.budget_loop import run_budgeted_cycle
    from backend.supervisor.case import DELIVERY_QC, Claim, Finding, ProposedAction

    # A real signal: a stuck needs_human job (the trigger evidence).
    h.store.set_doc(
        jobs_col,
        "job-stuck",
        {
            "project_id": "proj-1",
            "station": "delivery",
            "status": "needs_human",
            "attempts": 1,
            "cost_micros": 0,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        },
    )

    def delivery_specialist(name, case):
        return Finding(
            specialist=DELIVERY_QC,
            case_id=case.case_id,
            claims=[
                Claim(
                    text="delivery job is stuck awaiting human triage",
                    evidence_ref=f"firestore://{jobs_col}/job-stuck",
                    confidence="high",
                )
            ],
            proposed_actions=[
                ProposedAction(
                    command_name="remediate",
                    args={"job_id": "job-stuck"},
                    cost_estimate_micros=2_000_000,
                    reversible=True,
                )
            ],
        )

    deliberation_col = f"it-deliberations-{uuid.uuid4().hex[:8]}"
    gate_col = f"it-gate-{uuid.uuid4().hex[:8]}"
    h.store.set_doc(
        gate_col,
        budget_loop.ACT_GATE_DOC,
        {
            "passed": True,
            "gate_version": budget_loop.ACT_GATE_VERSION,
            "suite": budget_loop.ACT_GATE_SUITE,
            "threshold": 0.8,
            "runs": 3,
        },
    )
    record = asyncio.run(
        run_budgeted_cycle(
            {
                "kind": "pickups_needs_human",
                "job_id": "job-stuck",
                "project_id": "proj-1",
            },
            get_settings(),
            h.store,
            h.machine,
            project_id="proj-1",
            jobs_col=jobs_col,
            approvals_col=approvals_col,
            deliberation_col=deliberation_col,
            envelope_override=20_000_000,
            autonomy_mode="act",
            gate_collection=gate_col,
            specialists={
                DELIVERY_QC: delivery_specialist,
                "reliability_investigator": None,
            },
            annotator=h._annotate,
        )
    )

    persisted = h.store.get_doc(deliberation_col, record["cycle_id"])
    assert persisted["status"] == "acted"
    decisions = persisted["budget"]["decisions"]
    dispatched = [d for d in decisions if d["decision"] == "dispatched"]
    assert len(dispatched) == 1
    assert dispatched[0]["command_name"] == "remediate"
    assert persisted["budget"]["spent_micros"] == 2_000_000
    approvals = h.store.list_where(approvals_col, "project_id", "proj-1")
    assert approvals and approvals[0]["approver"] == SUPERVISOR_APPROVER
    assert any("budget loop" in str(a["text"]) for a in h.annotations)
