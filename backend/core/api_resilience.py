"""ONE shared API-resilience layer for every outbound call in the product
(owner directive 2026-09-07: rate-limit hygiene is systemic, not per-site).

Policy:
- TRANSIENT: HTTP 429 (rate limited) and 5xx (server-side) plus network-level
  failures (URLError, timeouts, connection errors). Retried with jittered
  exponential backoff, honoring the server's Retry-After when present
  (capped so a pathological value cannot stall a job).
- NON-TRANSIENT: everything else fails LOUD immediately (C-1.1) — client
  bugs (4xx) and validation errors are never retried.
- IDEMPOTENCE RULE: only idempotent calls (GETs, synthesize, renders —
  operations whose retry cannot double-post) may be wrapped. Non-idempotent
  writes (Grafana annotations, incident creation, queue mutations) are the
  CALLER's responsibility and are deliberately NOT auto-retried here.
- Call sites: backend/core/generative.py (all raw HTTP), backend/supervisor/
  otel_ai.py (the instrumented Gemini call). New outbound call sites MUST
  route through call_with_resilience — a per-site ad-hoc retry loop is a
  review-rejected pattern."""

from __future__ import annotations

import random
import time
import urllib.error
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})


def backoff_seconds(
    attempt: int,
    retry_after: str | None,
    *,
    base: float = 1.0,
    cap: float = 30.0,
    jitter: float = 0.25,
) -> float:
    """Backoff decision (pure): exponential `base * 2**attempt` with
    symmetric jitter, overridden by a valid Retry-After (capped)."""
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    if retry_after is not None:
        try:
            value = float(retry_after)
            if value > 0:
                return min(value, cap)
        except ValueError:
            pass
    target = base * (2**attempt)
    spread = target * jitter
    wait = target + random.uniform(-spread, spread)
    return max(min(wait, cap), cap * 0.01)


def default_transient(exc: Exception) -> bool:
    """Rate limits, server errors, and network failures are transient."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in TRANSIENT_HTTP_STATUSES
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError))


def default_retry_after(exc: Exception) -> str | None:
    """The server's own retry guidance, when the error carries headers."""
    headers = getattr(exc, "headers", None)
    if headers is not None:
        try:
            return headers.get("Retry-After")
        except Exception:
            return None
    return None


def call_with_resilience(
    fn: Callable[[], T],
    *,
    is_transient: Callable[[Exception], bool] = default_transient,
    retry_after: Callable[[Exception], str | None] = default_retry_after,
    attempts: int = 4,
    base: float = 1.0,
    cap: float = 30.0,
    jitter: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run fn() under the resilience policy. Transient failures retry up
    to `attempts` total tries; the last error propagates (fail loud, the
    caller's error handling stays exact). Non-transient failures raise
    immediately. `sleep` is injectable for tests."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if not is_transient(exc) or attempt == attempts - 1:
                raise
            sleep(
                backoff_seconds(
                    attempt, retry_after(exc), base=base, cap=cap, jitter=jitter
                )
            )
    raise AssertionError("unreachable: attempts loop always returns or raises")
