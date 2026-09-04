"""H-1a (Amendment A9): case model, deterministic routing, orchestrator
plumbing for the multi-agent specialist team (TDD, RED-first).

Contracts (docs/plans/2026-09-03-multiagent-supervisor-plan.md):
- `build_case` derives an immutable Case from a real job doc (no LLM call).
- `route_specialists` is a deterministic table — no LLM decides who is asked.
- `apply_verdict` HARD-filters: a rejected finding's actions never reach the
  ranked list (excluded, not down-weighted).
- `run_deliberation_cycle` persists a `pc-deliberations` doc through a
  single-specialist stand-in call (personas arrive in H-1b..H-1e).
"""

from __future__ import annotations

import uuid

import pytest

from backend.core.config import get_settings
from backend.supervisor.case import (
    Case,
    Claim,
    Finding,
    ProposedAction,
    Verdict,
    build_case,
    route_specialists,
)
from backend.supervisor.deliberation import (
    apply_verdict,
    run_deliberation_cycle,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def jobs_col(run_id) -> str:
    return f"it-jobs-h1a-{run_id}"


def _seed_job(store, jobs_collection: str, **overrides) -> str:
    from backend.jobs.models import utc_now_iso

    job_id = f"job-{uuid.uuid4().hex[:10]}"
    doc = {
        "job_id": job_id,
        "station": "loudness",
        "project_id": f"it-{uuid.uuid4().hex[:6]}",
        "input_refs": ["gs://b/a.mp4"],
        "status": "failed",
        "attempts": 2,
        "error": "ffmpeg ebur128 parse failed",
        "cost_micros": 1500,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    doc.update(overrides)
    store.set_doc(jobs_collection, job_id, doc)
    return job_id


def test_case_built_from_real_job_doc(env, jobs_col) -> None:
    job_id = _seed_job(env, jobs_col, status="failed", station="loudness")

    case = build_case(
        {"kind": "job_failed", "job_id": job_id},
        env,
        jobs_collection=jobs_col,
    )

    assert case.case_id.startswith("case-")
    assert case.version == 1
    assert case.trigger["kind"] == "job_failed"
    evidence_job = case.evidence["job"]
    assert evidence_job is not None
    assert evidence_job["job_id"] == job_id
    assert evidence_job["station"] == "loudness"
    assert case.created_at.endswith("Z") or "+00:00" in case.created_at


def test_case_survives_missing_job_doc(env, jobs_col) -> None:
    case = build_case(
        {"kind": "job_failed", "job_id": "job-nothing"},
        env,
        jobs_collection=jobs_col,
    )
    assert case.evidence["job"] is None, (
        "absence is evidence too — recorded, not hidden"
    )


def test_routing_table_covers_every_trigger_category() -> None:
    from backend.supervisor.case import SPECIALIST_ROUTES

    required = {
        "job_failed",
        "stuck_lease",
        "crash_recovered",
        "quarantine",
        "qc_breach",
        "spend_breach",
        "runaway",
        "daily_budget",
        "dub_breach",
        "pickups_needs_human",
    }
    assert required <= set(SPECIALIST_ROUTES), (
        "every trigger category from plan §2.4 must have a row"
    )
    for category, specialists in SPECIALIST_ROUTES.items():
        assert specialists, f"{category} must route to at least one specialist"
        assert len(set(specialists)) == len(specialists), f"{category} has duplicates"

    assert route_specialists({"kind": "quarantine"}) == ["reliability_investigator"]
    assert route_specialists({"kind": "spend_breach"}) == [
        "spend_guardian",
        "reliability_investigator",
    ]
    assert route_specialists({"kind": "qc_breach"}) == [
        "delivery_qc",
        "reliability_investigator",
    ]
    assert "delivery_qc" in route_specialists(
        {"kind": "job_failed", "station": "loudness"}
    ), "station-specific QC agent joins failure triage when applicable"
    assert "reliability_investigator" in route_specialists({"kind": "daily_budget"}), (
        "root-cause is always in scope for genuine failure signals"
    )


def test_route_specialists_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown trigger"):
        route_specialists({"kind": "seance"})


def test_apply_verdict_is_a_hard_filter() -> None:
    finding_reliable = Finding(
        specialist="reliability_investigator",
        case_id="case-1",
        claims=[
            Claim(text="ffmpeg parse failed", evidence_ref="trace-1", confidence="high")
        ],
        proposed_actions=[
            ProposedAction(
                command_name="retry_job",
                args={"job_id": "job-1"},
                cost_estimate_micros=500,
                reversible=True,
            )
        ],
    )
    finding_bad = Finding(
        specialist="delivery_qc",
        case_id="case-1",
        claims=[Claim(text="captions fine", evidence_ref="doc-x", confidence="low")],
        proposed_actions=[
            ProposedAction(
                command_name="add_to_continuity",
                args={"shot_id": "shot-1", "alternate_id": "alt-1"},
                cost_estimate_micros=0,
                reversible=True,
            )
        ],
    )
    verdict = Verdict(
        case_id="case-1",
        rejected=[("doc-x", "stale: the job was re-rendered after this claim")],
        approved_specialists=["reliability_investigator"],
        overall_confidence="high",
    )

    surviving = apply_verdict([finding_reliable, finding_bad], verdict)

    assert [f.specialist for f in surviving] == ["reliability_investigator"], (
        "a rejected finding's actions NEVER reach the ranked list (hard filter)"
    )
    assert surviving[0].proposed_actions == finding_reliable.proposed_actions


def test_verdict_drops_individual_rejected_claims(env) -> None:
    """Rejection is per-claim: a specialist with one bad claim and one good
    one survives with only the good claim's actions."""
    good = Claim(text="loudness -26 LUFS", evidence_ref="metric-a", confidence="high")
    stale = Claim(text="quota exceeded", evidence_ref="log-old", confidence="medium")
    finding = Finding(
        specialist="reliability_investigator",
        case_id="case-2",
        claims=[good, stale],
        proposed_actions=[
            ProposedAction("retry_job", {"job_id": "j"}, 500, True),
            ProposedAction("pause_intake", {"station": "ingest"}, 0, True),
        ],
    )
    verdict = Verdict(
        case_id="case-2",
        rejected=[("log-old", "evidence predates the fix commit")],
        approved_specialists=["reliability_investigator"],
        overall_confidence="medium",
    )

    surviving = apply_verdict([finding], verdict)

    assert len(surviving) == 1
    assert surviving[0].claims == [good]


def test_orchestrator_persists_deliberation_doc(env, run_id) -> None:
    """H-1a DoD: the cycle persists a pc-deliberations doc from a
    single-specialist stand-in call — the control flow works before any
    persona exists (H-1b..)."""
    jobs_col = f"it-jobs-h1a-{run_id}"
    job_id = _seed_job(env, jobs_col, status="failed", station="loudness")

    def stand_in_specialist(name: str, case: Case) -> Finding:
        return Finding(
            specialist=name,
            case_id=case.case_id,
            claims=[
                Claim(
                    text="job failed on ebur128 parse",
                    evidence_ref=f"firestore://{jobs_col}/{job_id}",
                    confidence="high",
                )
            ],
            proposed_actions=[
                ProposedAction(
                    command_name="retry_job",
                    args={"job_id": job_id},
                    cost_estimate_micros=500,
                    reversible=True,
                )
            ],
        )

    import asyncio

    deliberation_col = f"it-deliberations-{run_id}"
    record = asyncio.run(
        run_deliberation_cycle(
            {"kind": "job_failed", "job_id": job_id},
            get_settings(),
            store=env,
            jobs_collection=jobs_col,
            deliberation_col=deliberation_col,
            specialists={
                "reliability_investigator": stand_in_specialist,
                "delivery_qc": stand_in_specialist,
            },
        )
    )

    doc = env.get_doc(deliberation_col, record["cycle_id"])
    assert doc is not None, "the cycle must persist a pc-deliberations document"
    assert doc["case_id"] == record["case_id"]
    assert set(doc["specialists"]) == {"reliability_investigator", "delivery_qc"}
    assert doc["verdict"]["approved_specialists"]
    ranked = doc["recommendation"]["ranked_actions"]
    assert ranked and ranked[0]["command_name"] == "retry_job"
    assert doc["status"] == "proposed"


def test_cycle_notifies_on_complete_for_sse(env, run_id) -> None:
    """H-1f contract: after persisting, the cycle hands the record to an
    injected `on_complete` callback (app.py publishes `deliberation.completed`
    SSE with it). Failures in the callback never fail the cycle."""
    import asyncio

    jobs_col = f"it-jobs-h1a-{run_id}"
    job_id = _seed_job(env, jobs_col, status="failed", station="loudness")
    seen: list[dict] = []
    failing_calls: list[dict] = []

    record = asyncio.run(
        run_deliberation_cycle(
            {"kind": "job_failed", "job_id": job_id, "project_id": "proj-x"},
            get_settings(),
            store=env,
            jobs_collection=jobs_col,
            deliberation_col=f"it-deliberations-{run_id}",
            on_complete=seen.append,
        )
    )
    assert len(seen) == 1
    assert seen[0]["cycle_id"] == record["cycle_id"]
    assert seen[0]["trigger"]["job_id"] == job_id

    def _boom(rec: dict) -> None:
        failing_calls.append(rec)
        raise RuntimeError("hub down")

    survived = asyncio.run(
        run_deliberation_cycle(
            {"kind": "job_failed", "job_id": job_id},
            get_settings(),
            store=env,
            jobs_collection=jobs_col,
            deliberation_col=f"it-deliberations-{run_id}",
            on_complete=_boom,
        )
    )
    assert len(failing_calls) == 1
    assert survived["cycle_id"] != record["cycle_id"]


def test_spine_lists_deliberations_for_job(env, run_id, monkeypatch) -> None:
    """H-1f contract: GET /projects/{id}/deliberations?job_id= returns the
    real pc-deliberations docs for that job, newest first."""
    import uuid

    from backend.api import spine
    from backend.api.app import create_app
    from backend.core.config import get_settings, reset_settings

    monkeypatch.setattr(spine, "DELIBERATIONS", f"it-deliberations-{run_id}")

    jobs_col = f"it-jobs-h1a-{run_id}"
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    other_project = f"it-{uuid.uuid4().hex[:6]}"
    job_id = _seed_job(
        env, jobs_col, status="failed", station="loudness", project_id=project_id
    )
    other_job = _seed_job(
        env, jobs_col, status="failed", station="loudness", project_id=other_project
    )
    for target in (job_id, other_job):
        env.set_doc(
            f"it-deliberations-{run_id}",
            f"cyc-{target}",
            {
                "cycle_id": f"cyc-{target}",
                "case_id": f"case-{target}",
                "created_at": "2026-09-04T00:00:00.000Z",
                "project_id": project_id if target == job_id else other_project,
                "trigger": {"kind": "job_failed", "job_id": target},
                "specialists": ["reliability_investigator"],
                "findings": [],
                "verdict": {"rejected": [], "approved_specialists": []},
                "recommendation": {"ranked_actions": [], "dissent": []},
                "status": "proposed",
            },
        )

    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    from fastapi.testclient import TestClient

    headers = {"X-API-Key": settings.api_key}
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/projects/{project_id}/deliberations",
            params={"job_id": job_id},
            headers=headers,
        )
        assert response.status_code == 200
        rows = response.json()
        assert [row["cycle_id"] for row in rows] == [f"cyc-{job_id}"]
        assert rows[0]["trigger"]["job_id"] == job_id
