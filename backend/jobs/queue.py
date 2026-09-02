"""Firestore lease queue (plan A-3, C-6.3). All state transitions run inside
Firestore transactions so concurrent workers can never double-lease: a lease
claim re-reads the doc inside the transaction and only writes when the job is
still claimable (queued, or leased with an expired lease). Workers are
idempotent per job_id — resubmission and retried transactions converge.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore as _firestore

from backend.core.firestore import FirestoreStore
from backend.jobs.models import Job, utc_now_iso

_QUEUE_FETCH = 10
_LEASED_FETCH = 20


def _iso_minus(dt_iso: str | None) -> bool:
    """True if the ISO timestamp is in the past (None counts as expired)."""
    if not dt_iso:
        return True
    then = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    return then <= datetime.now(timezone.utc)


def _iso_plus(seconds: int) -> str:
    return (
        (datetime.now(timezone.utc) + timedelta(seconds=seconds))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class FirestoreLeaseQueue:
    def __init__(
        self,
        store: FirestoreStore,
        *,
        collection: str = "pc-jobs",
        visibility_timeout_s: int = 300,
        max_attempts: int = 2,
    ) -> None:
        self._store = store
        self._collection = collection
        self._visibility = visibility_timeout_s
        self._max_attempts = max_attempts

    @property
    def store(self) -> FirestoreStore:
        return self._store

    # -- write path ---------------------------------------------------------

    def submit(self, job: Job) -> None:
        """Idempotent per job_id (C-6.3): create() succeeds once; duplicates
        raise Conflict, which we swallow — the stored job stays authoritative."""
        ref = self._store.client.collection(self._collection).document(job.id)
        try:
            ref.create(job.to_dict())
        except Exception as exc:  # AlreadyExists surfaces as ValueError/Conflict
            if (
                "already exists" not in str(exc).lower()
                and "conflict" not in str(exc).lower()
            ):
                raise

    def lease(self, worker_id: str, stations: list[str]) -> Job | None:
        """Claim the oldest claimable job for the given stations, or None."""
        now_iso = utc_now_iso()
        candidates: list[Job] = []
        queued = (
            self._store.client.collection(self._collection)
            .where("status", "==", "queued")
            .limit(_QUEUE_FETCH)
            .stream()
        )
        leased = (
            self._store.client.collection(self._collection)
            .where("status", "==", "leased")
            .limit(_LEASED_FETCH)
            .stream()
        )
        for snap in (*queued, *leased):
            job = Job.from_dict(snap.to_dict() or {})
            if job.station not in stations:
                continue
            if job.status == "leased" and not _iso_minus(job.lease_expires_at):
                continue  # someone else holds a live lease
            candidates.append(job)
        if not candidates:
            return None
        candidates.sort(key=lambda j: j.created_at)
        return self._claim_tx(candidates[0].id, worker_id, now_iso)

    def claim(self, job_id: str, worker_id: str) -> Job | None:
        """Claim a specific job_id if it is still claimable."""
        return self._claim_tx(job_id, worker_id, utc_now_iso())

    def complete(
        self,
        job_id: str,
        worker_id: str,
        cost_micros: int,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        payload: dict[str, Any] = {
            "status": "passed",
            "cost_micros": cost_micros,
            "error": None,
        }
        if extra:
            payload.update(extra)
        return self._transition(
            job_id,
            worker_id,
            lambda job: job.status == "leased",
            payload,
        )

    def fail(self, job_id: str, worker_id: str, error: str) -> bool:
        def fields(job: Job) -> dict[str, Any]:
            if job.attempts >= self._max_attempts:
                return {"status": "failed", "error": error}
            return {"status": "queued", "error": error}

        return self._transition(
            job_id, worker_id, lambda job: job.status == "leased", fields
        )

    def quarantine(
        self,
        job_id: str,
        worker_id: str,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """Terminal hold: never re-queued (AC-S1.1)."""
        payload: dict[str, Any] = {
            "status": "quarantined",
            "error": reason,
            "lease_owner": None,
            "lease_expires_at": None,
        }
        if extra:
            payload.update(extra)
        return self._transition(
            job_id, worker_id, lambda job: job.status == "leased", payload
        )

    def close(
        self,
        job_id: str,
        worker_id: str,
        status: str,
        *,
        cost_micros: int = 0,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """Terminal state other than pass/fail (throttled, needs_human)."""
        payload: dict[str, Any] = {
            "status": status,
            "cost_micros": cost_micros,
            "error": error,
            "lease_owner": None,
            "lease_expires_at": None,
        }
        if extra:
            payload.update(extra)
        return self._transition(
            job_id, worker_id, lambda job: job.status == "leased", payload
        )

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        def fields(job: Job) -> dict[str, Any]:
            return {"lease_expires_at": _iso_plus(self._visibility)}

        return self._transition(
            job_id, worker_id, lambda job: job.status == "leased", fields
        )

    def forget(self, job_id: str) -> None:
        """Test/cleanup helper: remove the job document entirely."""
        self._store.client.collection(self._collection).document(job_id).delete()

    # -- read path ----------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        snap = self._store.client.collection(self._collection).document(job_id).get()
        raw = snap.to_dict()  # type: ignore[union-attr]
        return Job.from_dict(raw) if snap.exists and raw else None  # type: ignore[union-attr]

    def list_for_project(self, project_id: str) -> list[Job]:
        jobs = [
            Job.from_dict(row)
            for row in self._store.list_where(
                self._collection, "project_id", project_id
            )
        ]
        jobs.sort(key=lambda job: job.created_at)
        return jobs

    # -- transactional core --------------------------------------------------

    def _claim_tx(self, job_id: str, worker_id: str, now_iso: str) -> Job | None:
        @_firestore.transactional
        def _tx(tx: Any, ref: Any) -> Job | None:
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return None
            job = Job.from_dict(snap.to_dict() or {})
            claimable = job.status == "queued" or (
                job.status == "leased" and _iso_minus(job.lease_expires_at)
            )
            if not claimable:
                return None
            claimed = {
                "status": "leased",
                "lease_owner": worker_id,
                "lease_expires_at": _iso_plus(self._visibility),
                "attempts": job.attempts + 1,
                "updated_at": now_iso,
            }
            tx.update(ref, claimed)
            merged = {**(snap.to_dict() or {}), **claimed}
            return Job.from_dict(merged)

        ref = self._store.client.collection(self._collection).document(job_id)
        try:
            return _tx(self._store.client.transaction(), ref)
        except Exception:
            return None

    def _transition(
        self,
        job_id: str,
        worker_id: str,
        guard: Any,
        fields: Any,
    ) -> bool:
        @_firestore.transactional
        def _tx(tx: Any, ref: Any) -> bool:
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return False
            job = Job.from_dict(snap.to_dict() or {})
            if job.status != "leased" or job.lease_owner != worker_id:
                return False
            if not guard(job):
                return False
            payload = fields(job) if callable(fields) else fields
            tx.update(ref, {**payload, "updated_at": utc_now_iso()})
            return True

        ref = self._store.client.collection(self._collection).document(job_id)
        try:
            return bool(_tx(self._store.client.transaction(), ref))
        except Exception:
            return False
