"""Spend Control detectors. Money is integer micro-units (C-6.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def coerce_cost_micros(value: object) -> int:
    """Refuse negative or non-numeric values (adversarial money path)."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float):
        n = int(value)
        return n if n > 0 else 0
    if isinstance(value, str):
        try:
            n = int(value)
        except ValueError:
            return 0
        return n if n > 0 else 0
    return 0


def is_runaway(requeue_count: int, threshold: int) -> bool:
    return int(requeue_count) >= int(threshold)


def job_over_cap(cost_micros: object, cap_micros: int) -> bool:
    if cap_micros <= 0:
        return False
    return coerce_cost_micros(cost_micros) > cap_micros


def retries_exhausted(attempts: int, max_retries: int) -> bool:
    return int(attempts) > int(max_retries)


def _same_utc_day(iso: str, now: datetime) -> bool:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    return then.astimezone(timezone.utc).date() == now.astimezone(timezone.utc).date()


def project_spend_micros(
    jobs: list[dict[str, Any]], *, now: datetime | None = None, daily: bool = True
) -> int:
    now = now or datetime.now(timezone.utc)
    total = 0
    for row in jobs:
        stamp = str(row.get("updated_at") or row.get("created_at") or "")
        if daily and stamp and not _same_utc_day(stamp, now):
            continue
        total += coerce_cost_micros(row.get("cost_micros"))
    return total


def budget_breached(spent: int, budget: int) -> bool:
    return budget > 0 and spent >= budget
