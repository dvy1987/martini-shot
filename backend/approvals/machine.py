"""ApprovalStateMachine — the ONLY writer of approval status (H-0).

Every transition runs inside a Firestore transaction guarded on the current
status (same proven pattern as FirestoreLeaseQueue._transition). Emission
(SSE + Grafana annotation) is best-effort and happens AFTER the transition
commits: a Grafana outage can strand nothing (pre-mortem clause: commit-first,
emit-after). The completion hook is a projection, not truth — job state is the
source of truth and a hook failure can never alter a job's own outcome.

Delivery guarantees, stated precisely (peer-review 2026-09-03):
- SLOW lane: exactly-once. Deterministic job id makes submit idempotent; the
  guarded proposed→acting transition admits one owner; the completion hook and
  the sweeper reconcile from job truth only.
- FAST lane: at-least-once with mandatory idempotency (fail-closed registry
  rule). The handler runs after the guarded proposed→approved transition, but
  a crash between handler and resolve — or a redrive — can run the handler
  again; doing so twice must be harmless by construction. The redrive claims
  via guarded approved→acting so concurrent sweepers cannot double-dispatch,
  and targeted commands re-check order-safety at execution time.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from google.cloud import firestore as _firestore

from backend.approvals.commands import CommandRegistry, default_registry
from backend.jobs.models import utc_now_iso
from backend.shots import lifecycle as shots

log = logging.getLogger("pc.approvals")

APPROVALS = "pc-approvals"


def propose_approval(
    store: Any, doc: dict[str, Any], *, collection: str = APPROVALS
) -> str:
    """The only creation path for approval documents (single-writer rule:
    creation is also a status write — status 'proposed'). Stations and API
    routes call this instead of touching the collection themselves."""
    approval_id = str(doc.get("approval_id") or f"ap-{uuid.uuid4().hex[:12]}")
    payload = {
        **doc,
        "approval_id": approval_id,
        "status": "proposed",
        "created_at": str(doc.get("created_at") or utc_now_iso()),
    }
    store.set_doc(collection, approval_id, payload)
    return approval_id


class ApprovalConflict(RuntimeError):
    """The approval is not in the expected state (double-dispatch, stale)."""


class ApprovalNotFound(RuntimeError):
    """No such approval document."""


# Order-safety lives in its own module (no import cycle with commands.py);
# re-exported here for the machine's and callers' convenience.
from backend.approvals.orders import (  # noqa: E402
    SupersededError,
)


@dataclass
class DispatchContext:
    """What a command handler may touch. Nothing else."""

    store: Any
    queue: Any
    settings: Any = None
    collection: str | None = None  # approvals collection, for order-safety checks


class ApprovalStateMachine:
    def __init__(
        self,
        store: Any,
        *,
        queue: Any,
        hub: Any | None = None,
        registry: CommandRegistry | None = None,
        collection: str = APPROVALS,
        annotator: Callable[[str, list[str]], dict] | None = None,
    ) -> None:
        self._store = store
        self._queue = queue
        self._hub = hub
        self._registry = registry or default_registry
        # A custom registry is overridden-first; production commands remain
        # reachable so callers like retry_job never vanish inside a test scoping.
        self._fallback = default_registry if registry is not None else None
        self._collection = collection
        self._annotator = annotator

    def _lookup(self, name: str) -> Any:
        cmd = self._registry.get(name)
        if cmd is None and self._fallback is not None:
            cmd = self._fallback.get(name)
        return cmd

    # -- public API ----------------------------------------------------------

    def dispatch(
        self,
        approval_id: str,
        decision: str,
        *,
        approver: str = "dev",
        reason: str = "",
    ) -> dict[str, Any]:
        """One human/system decision: reject, or approve (fast or slow lane)."""
        doc = self._store.get_doc(self._collection, approval_id)
        if doc is None:
            raise ApprovalNotFound(f"no such approval {approval_id}")
        if doc.get("status") != "proposed":
            raise ApprovalConflict(
                f"approval {approval_id} is {doc.get('status')!r}, not 'proposed'"
            )
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")

        if decision == "reject":
            self._transition(
                approval_id,
                "proposed",
                {
                    "status": "rejected",
                    "approver": approver,
                    "decision_reason": reason,
                    "decided_at": utc_now_iso(),
                },
            )
            merged = self._store.get_doc(self._collection, approval_id) or {}
            self._emit(merged, "rejected")
            return merged

        command = dict(doc.get("command") or {})
        if not command.get("name"):
            # Commandless approval (informational): approving it resolves the
            # request without dispatching anything. Action-carrying approvals
            # must always carry their command (see spend act resume fix).
            self._transition(
                approval_id,
                "proposed",
                {
                    "status": "approved",
                    "approver": approver,
                    "decision_reason": reason,
                    "decided_at": utc_now_iso(),
                    "result": {"ok": True, "noop": True},
                },
            )
            merged = self._store.get_doc(self._collection, approval_id) or {}
            self._emit(merged, "approved")
            return merged
        cmd = self._lookup(str(command.get("name") or ""))
        if cmd is None:
            raise ValueError(f"unknown command {command.get('name')!r}")

        self._transition(
            approval_id,
            "proposed",
            {
                "status": "approved",
                "approver": approver,
                "decision_reason": reason,
                "decided_at": utc_now_iso(),
            },
        )
        # Re-fetch: the handler (and its order-safety check) must see the
        # COMMITTED doc — including the decided_at the transition just wrote.
        doc = self._store.get_doc(self._collection, approval_id) or doc
        locked = self._locked_target_result(doc, cmd)
        if locked is not None:
            # Locked-target guard (AL-1): central, dispatch-time, for every
            # caller. Only lock/unlock themselves are exempt.
            self._transition(
                approval_id,
                "approved",
                {"status": "failed", "result": locked},
            )
            merged = self._store.get_doc(self._collection, approval_id) or {}
            self._emit(merged, "failed")
            return merged
        ctx = DispatchContext(
            store=self._store, queue=self._queue, collection=self._collection
        )
        try:
            outcome = cmd.fn(ctx, doc)
        except SupersededError as exc:
            log.warning("command %s superseded: %s", cmd.name, exc)
            self._transition(
                approval_id,
                "approved",
                {"status": "failed", "result": {"ok": False, "superseded": True}},
            )
            merged = self._store.get_doc(self._collection, approval_id) or {}
            self._emit(merged, "failed")
            return merged
        except Exception as exc:  # handler failure is a terminal state
            log.exception("command %s failed", cmd.name)
            self._transition(
                approval_id,
                "approved",
                {"status": "failed", "result": {"ok": False, "error": str(exc)[:300]}},
            )
            merged = self._store.get_doc(self._collection, approval_id) or {}
            self._emit(merged, "failed")
            return merged

        if cmd.lane == "fast":
            payload = {"ok": True}
            if isinstance(outcome, dict):
                payload.update(outcome)
            self._transition(
                approval_id,
                "approved",
                {"status": "resolved", "result": payload},
            )
        else:
            job = outcome
            job.id = f"job-cmd-{approval_id}"
            job.approval_id = approval_id
            # Acting FIRST, submit second (peer-review fix): the job must
            # never exist while the approval is still 'proposed' — a crash
            # between the writes would orphan a running render. If we crash
            # after the transition instead, the approval is 'acting' with a
            # deterministic job id and the sweeper backstops or resubmits
            # from the job_spec snapshot (submit is idempotent per id).
            self._transition(
                approval_id,
                "approved",
                {
                    "status": "acting",
                    "job_id": job.id,
                    "acting_since": utc_now_iso(),
                    "job_spec": {
                        "station": job.station,
                        "project_id": job.project_id,
                        "input_refs": list(job.input_refs),
                    },
                },
            )
            self._queue.submit(job)  # idempotent per deterministic id
        merged = self._store.get_doc(self._collection, approval_id) or {}
        self._emit(merged, str(merged.get("status") or ""))
        return merged

    # -- sweeper-facing transitions (the watchdog's hands, same single writer) -

    def _locked_target_result(
        self, doc: dict[str, Any], cmd: Any
    ) -> dict[str, Any] | None:
        """Locked-target guard (AL-1): a command whose args carry a shot_id
        that resolves to a LOCKED shot is refused. Lock/unlock commands are
        exempt (unlock is the whole point)."""
        args = (doc.get("command") or {}).get("args") or {}
        shot_id = str(args.get("shot_id") or "")
        if not shot_id or cmd.name in shots.LOCK_COMMANDS:
            return None
        if shots.is_locked(self._store, shot_id):
            return {"ok": False, "locked": True, "shot_id": shot_id}
        return None

    def redrive_fast(self, approval_id: str) -> dict[str, Any]:
        """Re-drive a fast action whose process died between the two fast
        transitions (status 'approved', no result). Safe precisely because
        fast commands are fail-closed idempotent (registry rule)."""
        doc = self._store.get_doc(self._collection, approval_id)
        if doc is None:
            raise ApprovalNotFound(f"no such approval {approval_id}")
        if doc.get("status") != "approved" or doc.get("result"):
            raise ApprovalConflict(
                f"approval {approval_id} is not a crashed fast action"
            )
        if doc.get("job_id"):
            raise ApprovalConflict(
                f"approval {approval_id} is slow-lane; the job owns the outcome"
            )
        command = dict(doc.get("command") or {})
        cmd = self._lookup(str(command.get("name") or ""))
        if cmd is None or cmd.lane != "fast":
            raise ApprovalConflict(
                f"command {command.get('name')!r} is not fast; refusing redrive"
            )
        retries = int(doc.get("sweep_retries") or 0)
        # Claim transition (peer-review fix): approved→acting is guarded, so
        # two concurrent sweepers cannot both run the handler; a crash after
        # the claim leaves an 'acting' approval the 15-min backstop catches.
        self._transition(
            approval_id,
            "approved",
            {
                "status": "acting",
                "acting_since": utc_now_iso(),
                "sweep_retries": retries + 1,
            },
        )
        ctx = DispatchContext(
            store=self._store, queue=self._queue, collection=self._collection
        )
        locked = self._locked_target_result(doc, cmd)
        if locked is not None:
            # The human locked the target after this action was approved.
            self._transition(
                approval_id,
                "acting",
                {"status": "failed", "result": locked},
            )
            merged = self._store.get_doc(self._collection, approval_id) or {}
            self._emit(merged, "failed")
            return merged
        try:
            outcome = cmd.fn(ctx, doc)
        except SupersededError as exc:
            log.warning("redrive of %s superseded: %s", cmd.name, exc)
            self._transition(
                approval_id,
                "acting",
                {"status": "failed", "result": {"ok": False, "superseded": True}},
            )
            merged = self._store.get_doc(self._collection, approval_id) or {}
            self._emit(merged, "failed")
            return merged
        except Exception as exc:
            log.exception("redrive of %s failed", cmd.name)
            self._transition(
                approval_id,
                "acting",
                {
                    "status": "failed",
                    "result": {"ok": False, "error": str(exc)[:300]},
                },
            )
            merged = self._store.get_doc(self._collection, approval_id) or {}
            self._emit(merged, "failed")
            return merged
        payload = {"ok": True}
        if isinstance(outcome, dict):
            payload.update(outcome)
        self._transition(
            approval_id,
            "acting",
            {"status": "resolved", "result": payload},
        )
        merged = self._store.get_doc(self._collection, approval_id) or {}
        self._emit(merged, "resolved")
        return merged

    def fail_stale(
        self, approval_id: str, *, expected_status: str, note: str
    ) -> dict[str, Any]:
        """Watchdog backstop: an action stuck past its patience window fails
        with a human-review flag — never auto-retried, never auto-resumed."""
        self._transition(
            approval_id,
            expected_status,
            {
                "status": "failed",
                "result": {"ok": False, "needs_human_review": True, "error": note},
            },
        )
        merged = self._store.get_doc(self._collection, approval_id) or {}
        self._emit(merged, "failed")
        return merged

    def mark_superseded(self, approval_id: str) -> dict[str, Any]:
        """Order-safety: a stale re-drive yields to a newer decision on the
        same target — the newer (often human) decision always stands."""
        self._transition(
            approval_id,
            "approved",
            {
                "status": "failed",
                "result": {"ok": False, "superseded": True},
            },
        )
        merged = self._store.get_doc(self._collection, approval_id) or {}
        self._emit(merged, "failed")
        return merged

    def on_job_terminal(self, job: Any) -> bool:
        """Completion hook (projection, not truth): a job the approval is
        watching turned terminal → flip the approval. Never raises; job truth
        was already written. Non-terminal jobs (requeued after a crash) are
        ignored — the sweeper's patience rule owns those."""
        if job is None or not getattr(job, "approval_id", None):
            return False
        approval_id = str(job.approval_id)
        doc = self._store.get_doc(self._collection, approval_id)
        if doc is None or doc.get("status") != "acting":
            return False
        if job.status == "passed":
            fields = {
                "status": "resolved",
                "result": {
                    "ok": True,
                    "job_id": job.id,
                    "cost_micros": job.cost_micros,
                },
            }
        elif job.status in {"failed", "quarantined"}:
            fields = {
                "status": "failed",
                "result": {"ok": False, "job_id": job.id, "error": job.error},
            }
        else:
            return False  # queued/leased/throttled/needs_human: keep watching
        try:
            self._transition(approval_id, "acting", fields)
        except ApprovalConflict:
            return False
        merged = self._store.get_doc(self._collection, approval_id) or {}
        self._emit(merged, str(merged.get("status") or ""))
        return True

    # -- transactional core ---------------------------------------------------

    def _transition(
        self, approval_id: str, expected_status: str, fields: dict[str, Any]
    ) -> None:
        @_firestore.transactional
        def _tx(tx: Any, ref: Any) -> bool:
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return False
            doc = snap.to_dict() or {}
            if doc.get("status") != expected_status:
                return False
            tx.update(ref, {**fields, "updated_at": utc_now_iso()})
            return True

        ref = self._store.client.collection(self._collection).document(approval_id)
        ok = _tx(self._store.client.transaction(), ref)
        if not ok:
            raise ApprovalConflict(
                f"approval {approval_id} no longer {expected_status!r}"
            )

    def _emit(self, doc: dict[str, Any], outcome: str) -> None:
        """SSE + Grafana annotation, best-effort AFTER commit (never blocks)."""
        approval_id = str(doc.get("approval_id") or "")
        project_id = str(doc.get("project_id") or "")
        if self._hub is not None and project_id:
            try:
                self._hub.publish(
                    project_id,
                    "approval.updated",
                    {
                        "approval_id": approval_id,
                        "status": doc.get("status"),
                        "kind": doc.get("kind"),
                        "title": doc.get("title"),
                        "job_id": doc.get("job_id"),
                        "result": doc.get("result"),
                    },
                )
            except Exception:  # emit-after must never raise
                log.exception("sse emit failed for %s", approval_id)
        if self._annotator is not None:
            try:
                self._annotator(
                    f"approval {approval_id} project_id={project_id} "
                    f"outcome={outcome} command={(doc.get('command') or {}).get('name')}",
                    ["martini-shot", "approval", outcome],
                )
            except Exception:
                log.exception("grafana annotation failed for %s", approval_id)
