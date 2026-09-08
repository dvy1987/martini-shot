"""Production specialist team (H-0b runtime wiring).

Two pieces close the "no production caller / silent stand-ins" review gap:

- `production_specialists(store, settings)` builds the REAL persona map for
  the full routed vocabulary (reliability / delivery_qc / spend_guardian /
  localization / continuity).
  `run_budgeted_cycle` refuses to run when any routed name is missing, so
  production can never silently fall back to stand-in specialists.
- `maybe_deliberate(job, ...)` is the app-level signal-fired trigger wired
  into the worker's `on_terminal` hook in `app.py`: a terminal failure state
  fires ONE deliberation cycle per job, deterministically idempotent
  (`cycle_id = cyc-job-<job_id>`, C-6.3). Default autonomy is act:
  rank, then spend the night envelope. propose_only is the kill switch.
  It NEVER raises into the worker path — a deliberation
  failure is logged and the worker carries on.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.core.config import Settings
from backend.jobs.models import Job
from backend.supervisor.budget_loop import run_budgeted_cycle

log = logging.getLogger("pc.supervisor.team")

DELIBERATION_COL = "pc-deliberations"

# Terminal states worth investigating (H-0b signal taxonomy). Anything else
# (pass, cancelled) is healthy and never triggers deliberation.
_DELIBERATION_TRIGGERS = {
    "failed": "job_failed",
    "quarantined": "quarantine",
    "needs_human": "pickups_needs_human",
}

# In-process guard so concurrent terminal events for one job don't race the
# Firestore existence check. Firestore check is the durable idempotency
# layer; this set just avoids duplicate in-flight cycles.
_in_flight: set[str] = set()
DEFERRED_SIGNAL_REASONS = {
    "stuck_lease": "requires a durable lease-expiry event source",
    "crash_recovered": "requires worker recovery event emission",
    "qc_breach": "requires QC-report event emission",
    "spend_breach": "requires Spend Control event emission",
    "runaway": "requires Spend Control runaway event emission",
    "daily_budget": "requires Spend Control daily-budget event emission",
    "dub_breach": "requires Dub QC event emission",
}


def production_specialists(
    store: Any,
    settings: Settings,
    *,
    jobs_collection: str = "pc-jobs",
) -> dict[str, Any]:
    """REAL personas for every routed name — the map production callers pass
    to `run_budgeted_cycle` (which refuses incomplete maps). No stand-ins."""
    from backend.supervisor.agents.continuity_investigator import (
        investigate as continuity_investigate,
    )
    from backend.supervisor.agents.delivery_qc import investigate as qc_investigate
    from backend.supervisor.agents.localization_investigator import (
        investigate as localization_investigate,
    )
    from backend.supervisor.agents.reliability_investigator import (
        investigate as reliability_investigate,
    )
    from backend.supervisor.agents.spend_guardian import (
        investigate as spend_investigate,
    )

    def delivery_qc_specialist(name: str, case: Any) -> Any:
        # The REAL D-4 QC evaluator report from the job doc / Firestore.
        return qc_investigate(
            case, settings, store=store, jobs_collection=jobs_collection
        ).finding

    def spend_guardian_specialist(name: str, case: Any) -> Any:
        # The pending requeue the sweeper would issue, judged against real
        # spend policies and real per-attempt cost (same wiring as shadow).
        job = dict(case.evidence.get("job") or {})
        proposal = None
        if case.trigger.get("kind") in ("runaway", "spend_breach", "daily_budget"):
            attempts = max(1, int(job.get("attempts") or 1))
            proposal = {
                "command_name": "retry_job",
                "args": {"job_id": job.get("job_id") or job.get("id")},
                "cost_estimate_micros": int(job.get("cost_micros") or 0) // attempts,
            }
        return spend_investigate(
            case,
            settings,
            proposal=proposal,
            store=store,
            jobs_collection=jobs_collection,
        )

    from backend.supervisor.case import (
        CONTINUITY,
        DELIVERY_QC,
        LOCALIZATION,
        RELIABILITY,
        SPEND_GUARDIAN,
    )

    return {
        RELIABILITY: lambda name, case: reliability_investigate(case, settings),
        DELIVERY_QC: delivery_qc_specialist,
        SPEND_GUARDIAN: spend_guardian_specialist,
        LOCALIZATION: lambda name, case: localization_investigate(case, settings),
        CONTINUITY: lambda name, case: continuity_investigate(
            case, settings, store=store, jobs_collection=jobs_collection
        ),
    }


def production_verifier(settings: Settings) -> Any:
    """Return the real Verification Agent for production deliberations.

    Keeping this explicit prevents `run_deliberation_cycle` from selecting its
    test-only permissive default verifier when a worker signal creates a
    deliberation cycle.
    """
    from backend.supervisor.agents.verification import verify

    return lambda case, findings: verify(case, findings, settings)


def production_synthesizer(settings: Settings) -> Any:
    """Return the real Post Supervisor synthesis stage for production."""
    from backend.supervisor.agents.post_supervisor import synthesize

    return lambda case, findings, verdict: synthesize(case, findings, verdict, settings)


def maybe_deliberate(
    job: Job,
    *,
    store: Any,
    settings: Settings,
    machine: Any = None,
    annotator: Any = None,
) -> asyncio.Task[dict[str, Any]] | None:
    """Signal-fired deliberation (worker `on_terminal` seam). Default
    autonomy is act: rank, then spend the night envelope. Best-effort:
    never raises into the worker path; returns the scheduled task (or None)."""
    trigger_kind = _DELIBERATION_TRIGGERS.get(job.status)
    if trigger_kind is None:
        return None  # healthy terminal state — nothing to investigate

    cycle_id = f"cyc-job-{job.id}"
    if cycle_id in _in_flight:
        return None
    try:
        if store.get_doc(DELIBERATION_COL, cycle_id) is not None:
            return None  # already deliberated this job (idempotent, C-6.3)
    except Exception:
        log.exception("deliberation dedup check failed for %s", cycle_id)
        return None

    _in_flight.add(cycle_id)

    async def _cycle() -> dict[str, Any]:
        try:
            from backend.supervisor.budget_loop import load_autonomy_mode

            return await run_budgeted_cycle(
                {
                    "kind": trigger_kind,
                    "job_id": job.id,
                    "project_id": job.project_id,
                    "station": job.station,
                },
                settings,
                store,
                machine,
                project_id=job.project_id,
                jobs_col="pc-jobs",
                approvals_col="pc-approvals",
                specialists=production_specialists(store, settings),
                verifier=production_verifier(settings),
                synthesizer=production_synthesizer(settings),
                annotator=annotator,
                autonomy_mode=load_autonomy_mode(store),
                cycle_id=cycle_id,
                deliberation_col=DELIBERATION_COL,
            )
        except Exception:
            log.exception(
                "signal-fired deliberation failed (worker unaffected) cycle_id=%s",
                cycle_id,
            )
            raise
        finally:
            _in_flight.discard(cycle_id)

    try:
        task = asyncio.get_running_loop().create_task(
            _cycle(), name=f"pc-deliberation-{cycle_id}"
        )
    except RuntimeError:
        _in_flight.discard(cycle_id)
        return None  # no running loop (e.g. shutdown) — skip, don't raise

    def _observe_completion(completed: asyncio.Task[dict[str, Any]]) -> None:
        """Consume detached failures so the runtime has one logged outcome,
        rather than an unobserved-task warning during worker shutdown."""
        if completed.cancelled():
            log.info("signal-fired deliberation cancelled cycle_id=%s", cycle_id)
            return
        try:
            completed.result()
        except Exception:
            log.exception("signal-fired deliberation task failed cycle_id=%s", cycle_id)

    task.add_done_callback(_observe_completion)
    return task
