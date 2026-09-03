"""Job model (spec S0, C-6.4). Timestamps are UTC ISO-8601 strings; money is
integer micro-units; status is a closed vocabulary including quarantine and
spend-control holds.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

STATUSES: tuple[str, ...] = (
    "queued",
    "leased",
    "passed",
    "failed",
    "quarantined",
    "throttled",
    "needs_human",
)


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def new_job_id() -> str:
    return f"job-{uuid.uuid4().hex[:12]}"


@dataclass
class Job:
    station: str
    project_id: str
    input_refs: list[str]
    id: str = field(default_factory=new_job_id)
    status: str = "queued"
    attempts: int = 0
    cost_micros: int = 0
    error: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    checksum_sha256: str | None = None
    approval_id: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    # Audit trail of deliberate retries (H-0 peer-review fix): each requeue
    # appends {from_status, had_attempts, at} BEFORE the attempts reset.
    retry_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        known = {f for f in cls.__dataclass_fields__}
        payload = {k: v for k, v in data.items() if k in known}
        if not payload.get("result"):
            payload["result"] = {}
        return cls(**payload)
