"""TDD for the Loudness Strategist station agent (A10-3)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.supervisor.batch_state import read_loudness_season_state
from backend.supervisor.station_agents.base import StationDecisionError
from backend.supervisor.station_agents.loudness_strategy import (
    build_prompt,
    decide_loudness_strategy,
    parse_strategy_decision,
    suggestion_for_report,
)

REPORT: dict[str, Any] = {
    "job_id": "cyc-b1-ep-04-en-loudness",
    "episode_id": "ep-04",
    "source_ref": "sources/tape-1/ep-04.mp4",
    "lufs_integrated": -16.1,
    "true_peak_dbtp": -2.0,
    "verdict_streaming": "pass",
    "verdict_broadcast": "fail_hot",
    "stem_diagnosis": "balanced",
    "dialogue_band_lufs": -17.0,
    "music_band_lufs": -17.5,
}

SEASON: list[dict[str, Any]] = [
    {"episode_id": "ep-01", "lufs": -16.2},
    {"episode_id": "ep-02", "lufs": -16.0},
    {"episode_id": "ep-03", "lufs": -16.4},
]


def test_suggestion_maps_measurements() -> None:
    # Pass + balanced stems -> accept.
    assert suggestion_for_report(REPORT) == "accept"
    # True-peak over ceiling -> limiter, regardless of stems.
    peak = {
        **REPORT,
        "lufs_integrated": -16.0,
        "true_peak_dbtp": -0.4,
        "verdict_streaming": "fail_true_peak",
    }
    assert suggestion_for_report(peak) == "apply_limiter"
    # Imbalanced stems win over an integrated pass (rebalance, re-measure).
    hot = {**REPORT, "stem_diagnosis": "dialogue_hot"}
    assert suggestion_for_report(hot) == "fix_stem"
    # Quiet + music_hot -> fix_stem.
    quiet = {
        **REPORT,
        "lufs_integrated": -27.8,
        "verdict_streaming": "fail_quiet",
        "stem_diagnosis": "music_hot",
    }
    assert suggestion_for_report(quiet) == "fix_stem"
    # Meter garbage -> conservative escalation.
    assert suggestion_for_report({"verdict_streaming": "meter_error"}) == "accept"


def test_prompt_contains_measurements_and_season() -> None:
    prompt = build_prompt(REPORT, SEASON)
    assert "-16.1" in prompt  # integrated LUFS
    assert "dialogue_hot|music_hot" in prompt  # stem vocabulary
    assert "ep-01" in prompt and "-16.2" in prompt  # sibling rows
    assert "coherence" in prompt.lower()  # season-coherence rule stated
    assert "accept|fix_stem|apply_limiter" in prompt
    assert "choose needs_human" not in prompt.lower()


def test_parse_valid_decision() -> None:
    text = json.dumps(
        {
            "agent": "loudness_strategy",
            "decision": "apply_limiter",
            "streaming_route": "block",
            "broadcast_route": "block",
            "reason": "integrated 2 LU hot against season median -16.2",
            "confidence": "high",
        }
    )
    decision = parse_strategy_decision(text, REPORT)
    assert decision.decision == "apply_limiter"


def test_parse_will_not_accept_an_explosion_sitting_at_talk_level() -> None:
    """Live miss scene-05: classified explosion but accepted because -16
    matched the old TV target. A bang at talk level must be mixed louder."""
    bang = {
        **REPORT,
        "lufs_integrated": -16.0,
        "verdict_streaming": "pass",
        "stem_diagnosis": "balanced",
    }
    text = json.dumps(
        {
            "agent": "loudness_strategy",
            "decision": "accept",
            "streaming_route": "accept",
            "broadcast_route": "block",
            "scene_class": "loud-no-dialogue",
            "target_lufs": -9.0,
            "reason": "integrated matches streaming -16",
            "confidence": "high",
        }
    )
    assert parse_strategy_decision(text, bang).decision == "apply_limiter"


def test_parse_tolerates_fences() -> None:
    text = (
        "```json\n"
        + json.dumps(
            {
                "agent": "loudness_strategy",
                "decision": "accept",
                "streaming_route": "accept",
                "broadcast_route": "block",
                "reason": "within tolerance of target and season",
                "confidence": "medium",
            }
        )
        + "\n```"
    )
    assert parse_strategy_decision(text, REPORT).decision == "accept"


def test_parse_fails_loud_on_bad_decision() -> None:
    text = json.dumps(
        {
            "agent": "loudness_strategy",
            "decision": "normalize_everything",
            "reason": "x",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_strategy_decision(text, REPORT)


def test_parse_fails_loud_on_missing_reason() -> None:
    text = json.dumps(
        {
            "agent": "loudness_strategy",
            "decision": "accept",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_strategy_decision(text, REPORT)


def test_decide_uses_one_metered_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(_settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        return {
            "text": json.dumps(
                {
                    "agent": "loudness_strategy",
                    "decision": "accept",
                    "streaming_route": "accept",
                    "broadcast_route": "block",
                    "reason": "passes streaming target; coherent with season",
                    "confidence": "high",
                }
            ),
            "model": "gemini-3.7-flash",
            "cost_micros": 1400,
        }

    monkeypatch.setattr("backend.supervisor.otel_ai.run_agent_call", fake_call)
    decision, cost = decide_loudness_strategy(
        object(), report=REPORT, season_state=SEASON
    )
    assert cost == 1400
    assert len(calls) == 1
    assert "coherence" in calls[0]["prompt"].lower()
    assert decision.decision == "accept"


class _FakeStore:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.queries: list[tuple[str, str, Any]] = []

    def list_where(
        self, collection: str, field: str, value: object
    ) -> list[dict[str, Any]]:
        self.queries.append((collection, field, value))
        return [d for d in self.docs if d.get("result", {}).get("batch_id") == value]


def test_read_loudness_season_state_is_read_only_and_normalized() -> None:
    docs = [
        {
            "id": "cyc-b1-ep-01-en-loudness",
            "station": "loudness",
            "status": "pass",
            "result": {"batch_id": "b1", "episode_id": "ep-01", "lufs": -16.2},
        },
        {
            "id": "cyc-b1-ep-02-en-loudness",
            "station": "loudness",
            "status": "needs_human",
            "result": {"batch_id": "b1", "episode_id": "ep-02", "lufs": -11.0},
        },
        {
            "id": "cyc-b1-ep-01-en-ingest",
            "station": "ingest",
            "status": "pass",
            "result": {"batch_id": "b1", "episode_id": "ep-01"},
        },
        {
            # A loudness job that never measured (no lufs) is skipped.
            "id": "cyc-b1-ep-03-en-loudness",
            "station": "loudness",
            "status": "queued",
            "result": {"batch_id": "b1", "episode_id": "ep-03"},
        },
    ]
    store = _FakeStore(docs)
    rows = read_loudness_season_state(store, "b1")
    assert store.queries == [("pc-jobs", "result.batch_id", "b1")]
    assert rows == [
        {"episode_id": "ep-01", "lufs": -16.2},
        {"episode_id": "ep-02", "lufs": -11.0},
    ]
