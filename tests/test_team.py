"""H-0b production wiring (review gap: no production caller, silent stand-ins).

- `run_budgeted_cycle` is FAIL-CLOSED about specialists: every routed name
  must map to a real persona — no silent stand-in specialists in production.
- `team.maybe_deliberate` is the app-level signal-fired trigger: a terminal
  failure state fires ONE propose-only (unless ACT receipt) deliberation per
  job, deterministically idempotent per job (C-6.3).
- `team.production_specialists` covers the full routed vocabulary with REAL
  personas (reliability / delivery_qc / spend_guardian).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from backend.core.config import get_settings
from backend.jobs.models import Job
from backend.supervisor import team
from backend.supervisor.budget_loop import run_budgeted_cycle

pytestmark = pytest.mark.integration


def test_run_budgeted_cycle_refuses_missing_routed_specialists(
    env, approvals_col, jobs_col
):
    """Fail-closed: a production caller that omits a routed specialist is a
    wiring bug, not a reason to consult a stand-in."""
    from backend.supervisor.case import DELIVERY_QC

    with pytest.raises(ValueError, match="reliability_investigator"):
        asyncio.run(
            run_budgeted_cycle(
                {"kind": "pickups_needs_human", "job_id": "job-x", "project_id": "p"},
                get_settings(),
                env,
                None,
                project_id="p",
                jobs_col=jobs_col,
                approvals_col=approvals_col,
                gate_collection=f"it-gate-{uuid.uuid4().hex[:8]}",
                autonomy_mode="propose_only",
                specialists={DELIVERY_QC: lambda name, case: None},
            )
        )


def test_production_specialists_cover_every_routed_name(env) -> None:
    from backend.core.config import get_settings
    from backend.supervisor.case import SPECIALIST_ROUTES, route_specialists

    specialists = team.production_specialists(env, get_settings())
    for kind in SPECIALIST_ROUTES:
        for name in route_specialists({"kind": kind, "job_id": "job-nothing"}):
            assert name in specialists, f"{kind} routes {name} — no real persona wired"
            assert callable(specialists[name])


def test_every_non_terminal_route_is_explicitly_deferred() -> None:
    """The router may define future signal types, but their absence from the
    worker hook must be deliberate and visible—not a silent coverage gap."""
    from backend.supervisor.case import SPECIALIST_ROUTES

    runtime_signals = set(team._DELIBERATION_TRIGGERS.values())
    assert set(SPECIALIST_ROUTES) - runtime_signals == set(
        team.DEFERRED_SIGNAL_REASONS
    )


def _job(**overrides) -> Job:
    defaults = {
        "id": f"job-{uuid.uuid4().hex[:8]}",
        "station": "loudness",
        "project_id": "proj-1",
        "input_refs": [],
        "status": "failed",
        "attempts": 1,
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_maybe_deliberate_fires_one_propose_only_cycle_per_job(
    env, monkeypatch
) -> None:
    fired: list[dict[str, Any]] = []

    async def fake_cycle(trigger, settings, store, machine, **kwargs):
        # Mirror the real contract: run_budgeted_cycle persists the cycle doc
        # keyed by cycle_id — that persistence IS the durable dedup layer.
        store.set_doc(
            team.DELIBERATION_COL, kwargs["cycle_id"], {"cycle_id": kwargs["cycle_id"]}
        )
        fired.append({"trigger": trigger, **kwargs})
        return {"cycle_id": kwargs["cycle_id"], "status": "recorded"}

    monkeypatch.setattr(team, "run_budgeted_cycle", fake_cycle)

    async def scenario() -> None:
        job = _job(status="failed")
        team.maybe_deliberate(job, store=env, settings=get_settings())
        await asyncio.sleep(0)
        team.maybe_deliberate(job, store=env, settings=get_settings())  # dedup
        await asyncio.sleep(0)

    asyncio.run(scenario())

    assert len(fired) == 1, "one signal, one deliberation cycle (idempotent per job)"
    assert fired[0]["trigger"]["kind"] == "job_failed"
    assert fired[0]["autonomy_mode"] == "propose_only"
    assert fired[0]["cycle_id"] == f"cyc-job-{fired[0]['trigger']['job_id']}"
    assert callable(fired[0]["verifier"]), (
        "production cycles must use the real Verification Agent rather than "
        "the permissive deliberation fallback"
    )
    assert callable(fired[0]["synthesizer"]), (
        "production cycles must use the metered Post Supervisor synthesis "
        "rather than deterministic fallback ranking"
    )


def test_maybe_deliberate_ignores_healthy_terminal_states(env, monkeypatch) -> None:
    fired: list[Any] = []

    async def fake_cycle(*args, **kwargs):
        fired.append(args)

    monkeypatch.setattr(team, "run_budgeted_cycle", fake_cycle)

    async def scenario() -> None:
        team.maybe_deliberate(_job(status="passed"), store=env, settings=get_settings())
        team.maybe_deliberate(
            _job(status="pass"), store=env, settings=get_settings()
        )  # typosquat guard
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert fired == []
