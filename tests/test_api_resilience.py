"""TDD for the shared call_with_resilience executor: every outbound API
call in the product routes through ONE resilience policy — transient
failures (429/5xx/network) retry with jittered exponential backoff
honoring Retry-After; non-transient failures fail loud immediately
(C-1.1); non-idempotent calls are the CALLER's responsibility to not
wrap (the layer cannot know which POSTs double-post)."""

from __future__ import annotations

import urllib.error

import pytest

from backend.core.api_resilience import (
    TRANSIENT_HTTP_STATUSES,
    call_with_resilience,
    default_retry_after,
    default_transient,
)


class FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code: int, headers: dict[str, str] | None = None) -> None:
        super().__init__(
            url="https://fake",
            code=code,
            msg=f"HTTP {code}",
            hdrs=headers or {},
            fp=None,
        )


def test_transient_status_vocabulary() -> None:
    assert 429 in TRANSIENT_HTTP_STATUSES
    assert 503 in TRANSIENT_HTTP_STATUSES
    # Client bugs (400/401/403/404) are never retried — fail loud.
    assert 400 not in TRANSIENT_HTTP_STATUSES
    assert 403 not in TRANSIENT_HTTP_STATUSES


def test_default_transient_classifies_http_errors() -> None:
    assert default_transient(FakeHTTPError(429))
    assert default_transient(FakeHTTPError(503))
    assert not default_transient(FakeHTTPError(400))
    assert not default_transient(ValueError("nope"))


def test_default_retry_after_reads_headers() -> None:
    assert default_retry_after(FakeHTTPError(429, {"Retry-After": "9"})) == "9"
    assert default_retry_after(FakeHTTPError(429)) is None
    assert default_retry_after(ValueError("x")) is None


def test_succeeds_first_try_no_sleeps() -> None:
    sleeps: list[float] = []
    result = call_with_resilience(lambda: "ok", sleep=sleeps.append, base=1.0)
    assert result == "ok"
    assert sleeps == []


def test_retries_transient_then_succeeds() -> None:
    sleeps: list[float] = []
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise FakeHTTPError(503)
        return "recovered"

    result = call_with_resilience(flaky, sleep=sleeps.append, base=1.0, jitter=0.0)
    assert result == "recovered"
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]  # exponential, no jitter


def test_exhaustion_raises_the_last_error() -> None:
    sleeps: list[float] = []

    def always_429() -> None:
        raise FakeHTTPError(429, {"Retry-After": "3"})

    with pytest.raises(FakeHTTPError):
        call_with_resilience(
            always_429, sleep=sleeps.append, attempts=3, base=1.0, jitter=0.0
        )
    assert sleeps == [3.0, 3.0]  # Retry-After honored on every wait


def test_non_transient_fails_loud_immediately() -> None:
    sleeps: list[float] = []
    calls: list[int] = []

    def bad_request() -> None:
        calls.append(1)
        raise FakeHTTPError(400)

    with pytest.raises(FakeHTTPError):
        call_with_resilience(bad_request, sleep=sleeps.append)
    assert len(calls) == 1  # no retry on a client bug
    assert sleeps == []


def test_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError):
        call_with_resilience(lambda: 1, attempts=0)


def test_custom_transient_predicate() -> None:
    calls: list[int] = []

    def sdk_style() -> int:
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("429 RESOURCE_EXHAUSTED from the SDK")
        return 7

    result = call_with_resilience(
        sdk_style,
        sleep=lambda _s: None,
        is_transient=lambda exc: "429" in str(exc),
        base=1.0,
        jitter=0.0,
    )
    assert result == 7
    assert len(calls) == 2
