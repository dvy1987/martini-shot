"""Adversarial Spend Control: money must not be gamed (D-7 mandatory)."""

from backend.stations.spend.detect import coerce_cost_micros, project_spend_micros


def test_negative_cost_cannot_shrink_spend() -> None:
    assert coerce_cost_micros(-50_000_000) == 0
    assert coerce_cost_micros("-12") == 0
    assert coerce_cost_micros("nope") == 0
    assert coerce_cost_micros(None) == 0
    assert coerce_cost_micros(12.9) == 12


def test_negative_rows_do_not_credit_the_budget() -> None:
    jobs = [
        {"cost_micros": 100, "updated_at": "2026-09-01T10:00:00Z"},
        {"cost_micros": -999999, "updated_at": "2026-09-01T10:01:00Z"},
    ]
    from datetime import datetime, timezone

    spent = project_spend_micros(
        jobs, now=datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    )
    assert spent == 100


def test_bool_and_bad_timestamps_are_ignored() -> None:
    assert coerce_cost_micros(True) == 0
    jobs = [{"cost_micros": 50, "updated_at": "not-a-date"}]
    from datetime import datetime, timezone

    spent = project_spend_micros(
        jobs, now=datetime(2026, 9, 1, 12, tzinfo=timezone.utc), daily=True
    )
    assert spent == 0
