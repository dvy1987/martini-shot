"""TDD: loudness strategy deterministic suggestion (2026-10-02 eval sweep).

loud-04/05/08 lesson: the fallthrough accepted meter garbage, and stem
imbalance must outrank integrated/quiet verdicts."""

from __future__ import annotations

from backend.supervisor.station_agents.loudness_strategy import (
    suggestion_for_report,
)


def test_balanced_pass_accepts() -> None:
    assert (
        suggestion_for_report(
            {"stem_diagnosis": "balanced", "verdict_streaming": "pass"}
        )
        == "accept"
    )


def test_balanced_fail_quiet_is_limiter() -> None:
    assert (
        suggestion_for_report(
            {"stem_diagnosis": "balanced", "verdict_streaming": "fail_quiet"}
        )
        == "apply_limiter"
    )


def test_stem_imbalance_outranks_streaming_pass() -> None:
    """loud-04: integrated pass is not ear-pass — dialogue_hot is fix_stem."""
    assert (
        suggestion_for_report(
            {"stem_diagnosis": "dialogue_hot", "verdict_streaming": "pass"}
        )
        == "fix_stem"
    )


def test_stem_imbalance_outranks_fail_quiet() -> None:
    """loud-05: a blanket limiter pass would blast the already-hot band."""
    assert (
        suggestion_for_report(
            {"stem_diagnosis": "music_hot", "verdict_streaming": "fail_quiet"}
        )
        == "fix_stem"
    )


def test_meter_error_is_never_accept() -> None:
    """loud-08: accepting unmeasured audio is a fake all-good. Best effort
    is a mix toward target with routes blocked downstream."""
    assert (
        suggestion_for_report(
            {"stem_diagnosis": "unknown", "verdict_streaming": "meter_error"}
        )
        == "apply_limiter"
    )
    assert (
        suggestion_for_report({"stem_diagnosis": "unknown", "verdict_streaming": None})
        == "apply_limiter"
    )
