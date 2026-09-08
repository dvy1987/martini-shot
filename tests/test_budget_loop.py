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
    reservation_collection=None,
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
        # Per-run reservation ledger unless a test shares one explicitly —
        # tests must never pollute the real pc-budget-reservations night doc.
        reservation_collection=reservation_collection
        or f"pc-res-{uuid.uuid4().hex[:8]}",
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


def test_act_mode_dispatches_add_and_remove_from_the_cut(h):
    """Owner ruling: supervisor may change the cut inside the night envelope.
    Pointer moves are not renders — a $0 estimate still dispatches."""
    h.register_fast(
        "add_to_continuity",
        lambda ctx, ap: {"ok": True, "in_continuity": True, "cost_micros": 0},
    )
    h.register_fast(
        "remove_from_continuity",
        lambda ctx, ap: {"ok": True, "in_continuity": False, "cost_micros": 0},
    )
    summary = _act(
        h,
        [
            _action(
                name="add_to_continuity",
                cost=0,
                shot_id="shot-1",
                alternate_id="alt-new",
            ),
            _action(
                name="remove_from_continuity",
                cost=0,
                shot_id="shot-1",
                alternate_id="alt-old",
            ),
        ],
    )

    assert [d["decision"] for d in summary["decisions"]] == ["dispatched", "dispatched"]
    assert summary["spent_micros"] == 0
    approvals = h.store.list_where(h.approvals_col, "project_id", "proj-1")
    names = sorted(ap["command"]["name"] for ap in approvals)
    assert names == ["add_to_continuity", "remove_from_continuity"]
    assert all(ap["approver"] == SUPERVISOR_APPROVER for ap in approvals)


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


def test_retry_once_dispatches_one_retry_without_an_act_gate(h, jobs_col) -> None:
    """Owner ruling: diagnose, one repair, one retry. Will not lock shots."""
    h.store.set_doc(
        jobs_col,
        "job-1",
        {
            "id": "job-1",
            "status": "failed",
            "attempts": 1,
            "station": "loudness",
            "project_id": "proj-1",
            "error": "firestore write failed: 429 RESOURCE_EXHAUSTED",
            "result": {},
        },
    )
    h.register_fast(
        "retry_job",
        lambda ctx, ap: {"requeued": True, "job_id": "job-1", "cost_micros": 50_000},
    )
    empty_gate = f"it-gate-{uuid.uuid4().hex[:8]}"
    summary = _act(
        h,
        [
            _action(name="retry_job", job_id="job-1", cost=50_000),
            _action(name="lock_shot", shot_id="shot-x", cost=1),
            _action(name="retry_job", job_id="job-2", cost=50_000),
        ],
        env="retry_once",
        jobs_col=jobs_col,
        gate_collection=empty_gate,
    )
    assert summary["mode"] == "retry_once"
    dispatched = [d for d in summary["decisions"] if d["decision"] == "dispatched"]
    skipped = [d for d in summary["decisions"] if d["decision"] == "skipped"]
    assert len(dispatched) == 1
    assert dispatched[0]["command_name"] == "retry_job"
    assert dispatched[0]["args"]["job_id"] == "job-1"
    assert any("command" in str(d.get("reason") or "") for d in skipped)
    second = [
        d
        for d in skipped
        if d.get("command_name") == "retry_job"
        and (d.get("args") or {}).get("job_id") == "job-2"
    ]
    assert second, skipped
    assert "already chosen" in str(second[0]["reason"])
    stamped = h.store.get_doc(jobs_col, "job-1") or {}
    assert int((stamped.get("result") or {}).get("supervisor_retries") or 0) == 1


def test_retry_once_dispatches_a_fix_then_one_retry(h, jobs_col) -> None:
    h.store.set_doc(
        jobs_col,
        "job-1",
        {
            "id": "job-1",
            "status": "failed",
            "attempts": 1,
            "station": "pickups",
            "project_id": "proj-1",
            "error": "cup still in frame",
            "result": {"locked": False},
        },
    )
    h.register_fast(
        "correct_shot",
        lambda ctx, ap: {"ok": True, "cost_micros": 3_000_000},
    )
    h.register_fast(
        "retry_job",
        lambda ctx, ap: {"requeued": True, "job_id": "job-1", "cost_micros": 50_000},
    )
    summary = _act(
        h,
        [
            _action(
                name="correct_shot",
                job_id="job-1",
                cost=3_000_000,
                shot_id="shot-a",
                project_id="proj-1",
                source_uri="gs://bucket/clip.mp4",
                intent="remove the cup",
            ),
            _action(name="retry_job", job_id="job-1", cost=50_000),
            _action(name="lock_shot", shot_id="shot-a", cost=1),
        ],
        env="retry_once",
        jobs_col=jobs_col,
        gate_collection=f"it-gate-{uuid.uuid4().hex[:8]}",
    )
    dispatched = [
        d["command_name"] for d in summary["decisions"] if d["decision"] == "dispatched"
    ]
    assert dispatched == ["correct_shot", "retry_job"]


def test_retry_once_refuses_a_second_cycle_after_the_stamp(h, jobs_col) -> None:
    h.store.set_doc(
        jobs_col,
        "job-1",
        {
            "id": "job-1",
            "status": "failed",
            "attempts": 2,
            "station": "loudness",
            "project_id": "proj-1",
            "error": "still failing",
            "result": {"supervisor_retries": 1},
        },
    )
    h.register_fast(
        "retry_job",
        lambda ctx, ap: {"requeued": True, "job_id": "job-1", "cost_micros": 50_000},
    )
    summary = _act(
        h,
        [_action(name="retry_job", job_id="job-1", cost=50_000)],
        env="retry_once",
        jobs_col=jobs_col,
    )
    assert summary["mode"] == "retry_once"
    assert summary["decisions"][0]["decision"] == "skipped"
    assert "already" in str(summary["decisions"][0]["reason"])
    assert h.handler_calls == 0


def test_ensure_act_gate_receipt_unlocks_ranked_dispatch(h) -> None:
    empty_gate = f"it-gate-{uuid.uuid4().hex[:8]}"
    assert budget_loop.act_gate_passed(h.store, collection=empty_gate) is False
    budget_loop.ensure_act_gate_receipt(h.store, collection=empty_gate)
    assert budget_loop.act_gate_passed(h.store, collection=empty_gate) is True
    summary = _act(h, [_action(job_id="job-1")], env="act", gate_collection=empty_gate)
    assert summary["mode"] == "act"
    assert summary["decisions"][0]["decision"] == "dispatched"


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
    from backend.supervisor.case import (
        CONTINUITY,
        DELIVERY_QC,
        RELIABILITY,
        Claim,
        Finding,
        ProposedAction,
    )

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
                CONTINUITY: lambda name, case: Finding(
                    specialist=CONTINUITY,
                    case_id=case.case_id,
                    claims=[
                        Claim(
                            text="no cut change on this stuck delivery job",
                            evidence_ref=f"firestore://{jobs_col}/job-stuck",
                            confidence="low",
                        )
                    ],
                    proposed_actions=[],
                ),
                # A REAL persona callable (review round 2: a stand-in would
                # now correctly demote this cycle to propose-only).
                RELIABILITY: lambda name, case: Finding(
                    specialist=RELIABILITY,
                    case_id=case.case_id,
                    claims=[
                        Claim(
                            text="stuck lease exceeds the 15-minute backstop",
                            evidence_ref=f"firestore://{jobs_col}/job-stuck",
                            confidence="high",
                        )
                    ],
                    proposed_actions=[],  # concurs with Delivery QC's finding
                ),
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


# ---------------------------------------------------------------------------
# Review round 2 (2026-09-06): concurrency-safe envelope + stand-in labeling
# ---------------------------------------------------------------------------


def test_envelope_reservation_is_atomic(env):
    """The nightly envelope gate must be a compare-and-set on the night
    ledger doc, not a read-check-write race: two cycles can never both
    reserve the last chunk of the envelope."""
    from datetime import datetime, timezone

    from backend.supervisor.budget_loop import (
        ledger_reserved_micros,
        reconcile_reservation,
        reserve_envelope,
    )

    col = f"pc-reservations-{uuid.uuid4().hex[:8]}"
    now = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)

    assert reserve_envelope(
        env, cost=600, envelope=1000, base_spent=0, collection=col, now=now
    )
    assert not reserve_envelope(
        env, cost=600, envelope=1000, base_spent=0, collection=col, now=now
    ), "second concurrent reservation over the envelope must refuse"
    assert reserve_envelope(
        env, cost=400, envelope=1000, base_spent=0, collection=col, now=now
    )
    assert ledger_reserved_micros(env, collection=col, now=now) == 1000

    # Reconcile refunds the difference between estimate and actual.
    reconcile_reservation(env, delta=-300, collection=col, now=now)
    assert ledger_reserved_micros(env, collection=col, now=now) == 700


def test_parallel_reservations_cannot_overspend(env):
    """True concurrency: N threads racing for the same envelope chunk — the
    Firestore transaction must admit exactly the ones that fit."""
    import threading
    from datetime import datetime, timezone

    from backend.supervisor.budget_loop import reserve_envelope

    col = f"pc-reservations-{uuid.uuid4().hex[:8]}"
    now = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)
    results: list[bool] = []
    lock = threading.Lock()

    def attempt() -> None:
        ok = reserve_envelope(
            env, cost=600, envelope=1000, base_spent=0, collection=col, now=now
        )
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1, f"exactly one 600 fits a 1000 envelope: {results}"
    assert results.count(False) == 3


def test_parallel_daily_cap_reservations_cannot_overspend(env):
    """The daily Spend Control cap needs the same transactional admission as
    the nightly envelope: concurrent autonomy cycles cannot both reserve the
    last available project budget."""
    import threading
    from datetime import datetime, timezone

    from backend.supervisor.budget_loop import reserve_daily_cap

    col = f"pc-daily-cap-{uuid.uuid4().hex[:8]}"
    now = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)
    results: list[bool] = []
    lock = threading.Lock()

    def attempt() -> None:
        ok = reserve_daily_cap(
            env,
            project_id="project-cap",
            cost=600,
            daily_cap=1_000,
            base_spent=0,
            collection=col,
            now=now,
        )
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 1
    assert results.count(False) == 3


def test_second_dispatch_skips_when_reservation_exhausts_envelope(h):
    """Two sequential cycles sharing the night ledger: the first dispatches,
    the second must see the reservation and skip — even though its own
    supervisor_spend snapshot still shows zero (the job's real cost has not
    landed yet). This is precisely the window where the old read-check-write
    loop would double-spend."""
    # The dispatched job does NOT report cost synchronously (like a slow-lane
    # render in flight): supervisor_spend stays 0 after cycle 1.
    h.register_fast("remediate", lambda ctx, ap: {"ok": True})
    res_col = f"pc-res-{uuid.uuid4().hex[:8]}"
    first = _act(
        h,
        [_action(name="remediate", job_id="job-1")],
        envelope_override=2_000_000,
        reservation_collection=res_col,
    )
    assert [d["decision"] for d in first["decisions"]] == ["dispatched"]
    second = _act(
        h,
        [_action(name="remediate", job_id="job-2")],
        envelope_override=2_000_000,
        reservation_collection=res_col,
    )
    assert [d["decision"] for d in second["decisions"]] == ["skipped"]
    assert "envelope" in second["decisions"][0]["reason"]


def test_reservation_reconciles_to_actual_cost(h):
    """An over-estimate is refunded to the ledger after dispatch, so the
    night budget tracks real spend, not the loop's own guess."""
    res_col = f"pc-res-{uuid.uuid4().hex[:8]}"
    from datetime import datetime, timezone

    from backend.supervisor.budget_loop import ledger_reserved_micros

    summary = _act(
        h,
        [_action(name="cheap_fix", job_id="job-1", cost=2_000_000)],
        reservation_collection=res_col,
    )
    assert [d["decision"] for d in summary["decisions"]] == ["dispatched"]
    # cheap_fix really costs 500_000; the 2_000_000 estimate was reserved.
    assert (
        ledger_reserved_micros(
            h.store, collection=res_col, now=datetime.now(timezone.utc)
        )
        == 500_000
    )


def test_stand_in_cycle_is_demoted_even_with_receipt(h):
    """Defense in depth: a cycle that consulted a stand-in specialist is
    labeled non-actionable at deliberation time and the dispatch demotes it
    to propose-only — even with a passing ACT receipt in hand."""
    summary = _act(
        h,
        [_action(job_id="job-1")],
        actionable=False,
    )
    assert all(d["decision"] == "skipped" for d in summary["decisions"])
    assert "stand-in" in summary["decisions"][0]["reason"]


def test_deliberation_labels_stand_in_specialists(env, run_id):
    """run_deliberation_cycle records which routed names fell back to the
    stand-in and marks the cycle non-actionable."""
    from datetime import datetime, timezone

    from backend.core.config import get_settings
    from backend.supervisor.case import Verdict
    from backend.supervisor.deliberation import (
        _stand_in_specialist,
        run_deliberation_cycle,
    )

    col = f"pc-deliberations-{run_id}"
    datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)

    def fake_verifier(case, findings):
        return Verdict(
            case_id=case.case_id,
            rejected=[],
            approved_specialists=[f.specialist for f in findings],
            overall_confidence="medium",
        )

    def fake_synthesizer(case, findings, verdict):
        return {"summary": "stub", "ranked_actions": []}

    def reliability_stub(name, case):
        return _stand_in_specialist  # replaced below — real Finding instead

    record = asyncio.run(
        run_deliberation_cycle(
            {
                "kind": "job_failed",
                "job_id": "job-nothing",
                "project_id": "proj-1",
                "station": "loudness",  # routes [reliability, delivery_qc]
            },
            get_settings(),
            store=env,
            jobs_collection=f"pc-jobs-{run_id}",
            deliberation_col=col,
            specialists={
                # reliability covered by a real callable; delivery_qc missing
                # (job_failed on loudness routes both) → stand-in fallback
                "reliability_investigator": lambda name, case: _stand_in_specialist(
                    name, case
                ),
            },
            verifier=fake_verifier,
            synthesizer=fake_synthesizer,
            cycle_id=f"cyc-{run_id}",
        )
    )
    assert record["actionable"] is False
    assert record["stand_in_specialists"] == ["delivery_qc"]


def test_run_budgeted_cycle_forwards_verifier(h, approvals_col, jobs_col, run_id):
    """Regression lock (review round 2, finding 2): the verifier passed to
    run_budgeted_cycle MUST be the one that runs — a verifier that rejects
    everything leaves nothing to dispatch."""
    from backend.core.config import get_settings
    from backend.supervisor.budget_loop import run_budgeted_cycle
    from backend.supervisor.case import Verdict
    from backend.supervisor.team import production_specialists

    deliberation_col = f"pc-deliberations-{run_id}"
    specs = production_specialists(h.store, get_settings())

    def reject_all(case, findings):
        return Verdict(
            case_id=case.case_id,
            rejected=[
                (c.evidence_ref, "test: reject everything")
                for f in findings
                for c in f.claims
            ],
            approved_specialists=[],
            overall_confidence="low",
        )

    record = asyncio.run(
        run_budgeted_cycle(
            {
                "kind": "job_failed",
                "job_id": "job-veto-all",
                "project_id": "proj-1",
                "station": "ingest",
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
            gate_collection=h.gate_col,
            specialists=specs,
            verifier=reject_all,
        )
    )
    ranked = (record.get("recommendation") or {}).get("ranked_actions") or []
    assert ranked == [], "a veto-everything verifier must leave nothing ranked"
    assert all(d["decision"] == "skipped" for d in record["budget"]["decisions"])


def test_run_budgeted_cycle_forwards_synthesizer(h, approvals_col, jobs_col, run_id):
    """The production Post Supervisor must receive only verified findings."""
    from backend.core.config import get_settings
    from backend.supervisor.budget_loop import run_budgeted_cycle
    from backend.supervisor.case import Verdict
    from backend.supervisor.team import production_specialists

    called = False

    def synthesize(case, findings, verdict):
        nonlocal called
        called = True
        return {
            "ranked_actions": [],
            "summary": "No action is justified.",
            "dissent": [],
        }

    record = asyncio.run(
        run_budgeted_cycle(
            {
                "kind": "job_failed",
                "job_id": "job-synthesis",
                "project_id": "proj-1",
                "station": "ingest",
            },
            get_settings(),
            h.store,
            h.machine,
            project_id="proj-1",
            jobs_col=jobs_col,
            approvals_col=approvals_col,
            deliberation_col=f"pc-deliberations-{run_id}",
            autonomy_mode="propose_only",
            specialists=production_specialists(h.store, get_settings()),
            verifier=lambda case, findings: Verdict(
                case_id=case.case_id,
                rejected=[],
                approved_specialists=[],
                overall_confidence="high",
            ),
            synthesizer=synthesize,
        )
    )

    assert called
    assert record["recommendation"]["summary"] == "No action is justified."
