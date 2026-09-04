"""Command registry for the approval executor (H-0).

Fail-closed rule (locked design §Command registry): a command registered with
lane="fast" MUST declare idempotent=True — doing them twice must be harmless,
because the sweeper may safely re-drive a crashed fast action. Registering a
fast command without it raises at import time.

Production commands live on `default_registry`:
- pause_intake / resume_intake — instant, idempotent (fast lane)
- retry_job — instant, idempotent (fast lane); re-queues an existing job but
  ONLY from a terminal state (failed/throttled/needs_human). A queued/leased
  job is the lease-expiry machinery's business, never retry's (pre-mortem
  finding #1: the double-run).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.approvals.orders import SupersededError, newer_decision_exists
from backend.shots import lifecycle as shots
from backend.stations.spend import control as intake_control

RETRYABLE_STATUSES = {"failed", "throttled", "needs_human"}


@dataclass(frozen=True)
class Command:
    name: str
    lane: str
    idempotent: bool
    fn: Callable[[object, dict], object]


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def command(
        self, name: str, *, lane: str, idempotent: bool = False
    ) -> Callable[[Callable], Callable]:
        if lane not in {"fast", "slow"}:
            raise ValueError(f"lane must be fast or slow, got {lane!r}")
        if lane == "fast" and not idempotent:
            raise ValueError(
                f"fast command {name!r} must be registered idempotent=True: "
                "the sweeper may safely re-drive a crashed fast action"
            )

        def deco(fn: Callable[[object, dict], object]) -> Callable:
            self._commands[name] = Command(
                name=name, lane=lane, idempotent=idempotent, fn=fn
            )
            return fn

        return deco

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)


def _require_fresh(ctx, approval: dict) -> None:
    """Execution-time order-safety (peer-review fix): the sweeper's pre-check
    leaves a check-then-act window; the handler re-checks at the moment it
    acts, so a stale replay can never clobber a newer decision."""
    if ctx.collection is None:
        return
    if newer_decision_exists(ctx.store, ctx.collection, approval):
        raise SupersededError(
            "a newer decision already touched this target; refusing stale replay"
        )


def _pause_intake(ctx, approval: dict) -> dict:
    _require_fresh(ctx, approval)
    args = approval.get("command", {}).get("args", {}) or {}
    station = str(args.get("station") or "ingest")
    reason = str(args.get("reason") or f"approved {approval.get('approval_id')}")
    intake_control.pause_intake(ctx.store, station, reason)
    return {"station": station, "intake_paused": True}


def _resume_intake(ctx, approval: dict) -> dict:
    _require_fresh(ctx, approval)
    args = approval.get("command", {}).get("args", {}) or {}
    station = str(args.get("station") or "ingest")
    intake_control.resume_intake(ctx.store, station)
    return {"station": station, "intake_paused": False}


def _retry_job(ctx, approval: dict) -> dict:
    args = approval.get("command", {}).get("args", {}) or {}
    job_id = str(args.get("job_id") or "")
    if not job_id:
        raise ValueError("retry_job requires args.job_id")
    job = ctx.queue.get(job_id)
    if job is None:
        raise ValueError(f"no such job {job_id}")
    if job.status not in RETRYABLE_STATUSES:
        raise ValueError(
            f"job {job_id} is {job.status}; retry allowed only from "
            f"{sorted(RETRYABLE_STATUSES)} (mid-flight jobs belong to the "
            "lease-expiry machinery)"
        )
    if not ctx.queue.requeue(job_id):
        raise ValueError(f"requeue lost the race for {job_id}")
    return {"job_id": job_id, "requeued": True}


# -- AL-1 shot locking + alternates (all approval-tracked through here) -----


def _lock_shot(ctx, approval: dict) -> dict:
    args = approval.get("command", {}).get("args", {}) or {}
    shot_id = str(args.get("shot_id") or "")
    if not shot_id:
        raise ValueError("lock_shot requires args.shot_id")
    shots.lock_shot(ctx.store, shot_id, locked_by=str(approval.get("approver") or ""))
    return {"shot_id": shot_id, "locked": True}


def _unlock_shot(ctx, approval: dict) -> dict:
    args = approval.get("command", {}).get("args", {}) or {}
    shot_id = str(args.get("shot_id") or "")
    if not shot_id:
        raise ValueError("unlock_shot requires args.shot_id")
    shots.unlock_shot(ctx.store, shot_id)
    return {"shot_id": shot_id, "locked": False}


def _add_to_continuity(ctx, approval: dict) -> dict:
    args = approval.get("command", {}).get("args", {}) or {}
    shot_id = str(args.get("shot_id") or "")
    alternate_id = str(args.get("alternate_id") or "")
    if not shot_id or not alternate_id:
        raise ValueError(
            "add_to_continuity requires args.shot_id and args.alternate_id"
        )
    shots.promote_to_continuity(ctx.store, shot_id, alternate_id)
    return {"shot_id": shot_id, "alternate_id": alternate_id, "in_continuity": True}


def _remove_from_continuity(ctx, approval: dict) -> dict:
    args = approval.get("command", {}).get("args", {}) or {}
    alternate_id = str(args.get("alternate_id") or "")
    if not alternate_id:
        raise ValueError("remove_from_continuity requires args.alternate_id")
    shots.retire_alternate(ctx.store, alternate_id)
    return {"alternate_id": alternate_id, "in_continuity": False}


default_registry = CommandRegistry()
default_registry.command("pause_intake", lane="fast", idempotent=True)(_pause_intake)
default_registry.command("resume_intake", lane="fast", idempotent=True)(_resume_intake)
default_registry.command("retry_job", lane="fast", idempotent=True)(_retry_job)
default_registry.command("lock_shot", lane="fast", idempotent=True)(_lock_shot)
default_registry.command("unlock_shot", lane="fast", idempotent=True)(_unlock_shot)
default_registry.command("add_to_continuity", lane="fast", idempotent=True)(
    _add_to_continuity
)
default_registry.command("remove_from_continuity", lane="fast", idempotent=True)(
    _remove_from_continuity
)
