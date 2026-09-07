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
from backend.stations.draft_first import assert_master_eligible
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


def _extend_shot(ctx, approval: dict) -> dict:
    """D-9: approve → enqueue a real `extend` station job (async render,
    C-6.5). First render is always a draft (360p). Masters go through
    `render_master` after QC. Job id is deterministic from the approval id."""
    return _enqueue_shot_job(
        ctx, approval, station="extend", prefix="ext", extra={"tier": "draft"}
    )


OP_STATIONS = {
    "extend": "extend",
    "correction": "corrections",
    "relight": "relight",
    "coverage": "coverage",
    "camera_language": "camera_language",
}

CREATIVE_PREFIXES = {
    "corrections": "cor",
    "relight": "rlt",
    "coverage": "cov",
    "camera_language": "cam",
    "extend": "ext",
}

REGEN_STATIONS = {"corrections", "extend", "dub", "delivery"}


def _require_gs(uri: str, field: str) -> str:
    if not str(uri).startswith("gs://"):
        raise ValueError(f"{field} must be a gs:// URI")
    return str(uri)


def _enqueue_shot_job(
    ctx,
    approval: dict,
    *,
    station: str,
    prefix: str,
    extra: dict | None = None,
) -> dict:
    """Shared enqueue for Stage 1a creative ops. Job id is deterministic
    from the approval id so a sweeper redrive is idempotent (C-6.3)."""
    args = (approval.get("command") or {}).get("args") or {}
    extra = extra or {}
    shot_id = str(args.get("shot_id") or extra.get("shot_id") or "")
    project_id = str(args.get("project_id") or extra.get("project_id") or "")
    source_uri = str(args.get("source_uri") or extra.get("source_uri") or "")
    if not shot_id or not project_id or not source_uri:
        raise ValueError(f"{station} requires shot_id, project_id and source_uri")
    _require_gs(source_uri, "source_uri")
    if shots.get_shot(ctx.store, shot_id) is None:
        raise ValueError(f"no such shot {shot_id}")
    approval_id = approval.get("approval_id")
    from backend.jobs.models import Job

    result = {
        "shot_id": shot_id,
        "approval_id": approval_id,
        "destination_key": (
            f"projects/{project_id}/{station}/{prefix}-{approval_id}.mp4"
        ),
        "tier": extra.get("tier") or args.get("tier") or "draft",
        **{
            key: value
            for key, value in extra.items()
            if key not in {"shot_id", "project_id", "source_uri"}
        },
    }
    for key in (
        "intent",
        "prompt",
        "preset",
        "angle",
        "movement",
        "reference_style",
        "protected_subjects",
        "continuity_constraints",
        "reference_uris",
    ):
        if key in args and key not in result:
            result[key] = args[key]
    job = Job(
        station=station,
        project_id=project_id,
        input_refs=[source_uri],
        id=f"{prefix}-{approval_id}",
        status="queued",
        result=result,
    )
    ctx.queue.submit(job)
    return {"job_id": job.id, "enqueued": True, "shot_id": shot_id}


def _correct_shot(ctx, approval: dict) -> dict:
    args = (approval.get("command") or {}).get("args") or {}
    intent = str(args.get("intent") or "").strip()
    if not intent:
        raise ValueError("correct_shot requires args.intent")
    return _enqueue_shot_job(
        ctx,
        approval,
        station="corrections",
        prefix="cor",
        extra={"intent": intent},
    )


def _relight_shot(ctx, approval: dict) -> dict:
    from backend.stations.relight.run import PRESETS

    args = (approval.get("command") or {}).get("args") or {}
    preset = str(args.get("preset") or "")
    if preset not in PRESETS:
        raise ValueError(f"relight_shot requires a known preset ({sorted(PRESETS)})")
    return _enqueue_shot_job(
        ctx, approval, station="relight", prefix="rlt", extra={"preset": preset}
    )


def _generate_coverage(ctx, approval: dict) -> dict:
    from backend.stations.coverage.run import ANGLES

    args = (approval.get("command") or {}).get("args") or {}
    angle = str(args.get("angle") or "")
    intent = str(args.get("intent") or "").strip()
    references = args.get("reference_uris") or []
    if angle not in ANGLES:
        raise ValueError(f"generate_coverage requires a known angle ({sorted(ANGLES)})")
    if not intent:
        raise ValueError("generate_coverage requires args.intent")
    if not isinstance(references, list) or not references:
        raise ValueError("generate_coverage requires args.reference_uris")
    return _enqueue_shot_job(
        ctx,
        approval,
        station="coverage",
        prefix="cov",
        extra={"angle": angle, "intent": intent, "reference_uris": list(references)},
    )


def _apply_camera_language(ctx, approval: dict) -> dict:
    from backend.stations.camera_language.run import MOVEMENTS

    args = (approval.get("command") or {}).get("args") or {}
    movement = str(args.get("movement") or "")
    if movement not in MOVEMENTS:
        raise ValueError(
            f"apply_camera_language requires a known movement ({sorted(MOVEMENTS)})"
        )
    return _enqueue_shot_job(
        ctx,
        approval,
        station="camera_language",
        prefix="cam",
        extra={"movement": movement, "reference_style": args.get("reference_style")},
    )


def _render_master(ctx, approval: dict) -> dict:
    """D-11: enqueue a master-tier re-render of an op that already has a
    QC-passing draft. The draft-first gate is deterministic and fail-loud."""
    args = (approval.get("command") or {}).get("args") or {}
    shot_id = str(args.get("shot_id") or "")
    project_id = str(args.get("project_id") or "")
    op = str(args.get("op") or "")
    station = OP_STATIONS.get(op)
    if not shot_id or not project_id or station is None:
        raise ValueError(
            "render_master requires args.shot_id, project_id and a known op"
        )
    if shots.get_shot(ctx.store, shot_id) is None:
        raise ValueError(f"no such shot {shot_id}")
    draft = assert_master_eligible(shots.list_alternates(ctx.store, shot_id), op=op)
    source_uri = str(args.get("source_uri") or draft.get("artifact_ref") or "")
    _require_gs(source_uri, "source_uri")
    prefix = CREATIVE_PREFIXES[station]
    extra = {
        "tier": "master",
        "source_draft_id": draft.get("alternate_id"),
        "shot_id": shot_id,
        "project_id": project_id,
        "source_uri": source_uri,
        "op": op,
    }
    for key in ("intent", "preset", "angle", "movement", "prompt", "reference_uris"):
        if args.get(key) is not None:
            extra[key] = args[key]
    return _enqueue_shot_job(
        ctx, approval, station=station, prefix=f"mst-{prefix}", extra=extra
    )


def _regenerate_affected_spans(ctx, approval: dict) -> dict:
    """D-15: enqueue one draft job per affected span. Stations are a closed
    set so a stale script edit cannot invent an unknown render path."""
    args = (approval.get("command") or {}).get("args") or {}
    project_id = str(args.get("project_id") or "")
    version_id = str(args.get("version_id") or "")
    spans = args.get("spans") or []
    if not project_id or not version_id:
        raise ValueError(
            "regenerate_affected_spans requires args.project_id and args.version_id"
        )
    if not isinstance(spans, list) or not spans:
        raise ValueError("regenerate_affected_spans requires a non-empty args.spans")
    approval_id = approval.get("approval_id")
    from backend.jobs.models import Job

    job_ids: list[str] = []
    for index, span in enumerate(spans):
        if not isinstance(span, dict):
            raise ValueError("each span must be an object")
        station = str(span.get("station") or "")
        shot_id = str(span.get("shot_id") or "")
        source_uri = str(span.get("source_uri") or "")
        if station not in REGEN_STATIONS:
            raise ValueError(
                f"span station {station!r} not in {sorted(REGEN_STATIONS)}"
            )
        if not shot_id:
            raise ValueError("each span requires shot_id")
        _require_gs(source_uri, "source_uri")
        job = Job(
            station=station,
            project_id=project_id,
            input_refs=[source_uri],
            id=f"rev-{approval_id}-{index:02d}",
            status="queued",
            result={
                "shot_id": shot_id,
                "approval_id": approval_id,
                "version_id": version_id,
                "tier": "draft",
                **{key: value for key, value in span.items() if key not in {"station"}},
            },
        )
        ctx.queue.submit(job)
        job_ids.append(job.id)
    return {
        "job_ids": job_ids,
        "enqueued": True,
        "version_id": version_id,
        "span_count": len(job_ids),
    }


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
default_registry.command("extend_shot", lane="fast", idempotent=True)(_extend_shot)
default_registry.command("correct_shot", lane="fast", idempotent=True)(_correct_shot)
default_registry.command("relight_shot", lane="fast", idempotent=True)(_relight_shot)
default_registry.command("generate_coverage", lane="fast", idempotent=True)(
    _generate_coverage
)
default_registry.command("apply_camera_language", lane="fast", idempotent=True)(
    _apply_camera_language
)
default_registry.command("render_master", lane="fast", idempotent=True)(_render_master)
default_registry.command("regenerate_affected_spans", lane="fast", idempotent=True)(
    _regenerate_affected_spans
)
