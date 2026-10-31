"""TDD: vision-judge metric parsing + aggregation (pickups_vision_judge,
pickups_artifact_rate gates). Pure logic only — the live call is billed."""

from __future__ import annotations

import json

import pytest

from backend.evals.vision_judge import (
    parse_judge_payload,
    summarize_judgments,
    vision_summary,
)


def test_parse_clean_payload() -> None:
    parsed = parse_judge_payload(
        json.dumps({"vision_judge": 4.6, "artifact_frames": [3], "reason": "ok"}),
        n_frames=10,
    )
    assert parsed["vision_judge"] == 4.6
    assert parsed["artifact_frames"] == [3]
    assert parsed["artifact_rate"] == 0.1


def test_parse_tolerates_fences_and_dedupes() -> None:
    text = '```json\n{"vision_judge": 5, "artifact_frames": [1, 1, 2]}\n```'
    parsed = parse_judge_payload(text, n_frames=4)
    assert parsed["vision_judge"] == 5.0
    assert parsed["artifact_frames"] == [1, 2]
    assert parsed["artifact_rate"] == 0.5


def test_parse_rejects_out_of_scale() -> None:
    with pytest.raises(ValueError, match="outside 1-5"):
        parse_judge_payload(
            json.dumps({"vision_judge": 7, "artifact_frames": []}), n_frames=2
        )


def test_parse_rejects_bad_index_and_missing_fields() -> None:
    with pytest.raises(ValueError, match="out of range"):
        parse_judge_payload(
            json.dumps({"vision_judge": 4, "artifact_frames": [9]}), n_frames=3
        )
    with pytest.raises(ValueError, match="not JSON"):
        parse_judge_payload("not json at all", n_frames=3)
    with pytest.raises(ValueError, match="must be a list"):
        parse_judge_payload(
            json.dumps({"vision_judge": 4, "artifact_frames": "none"}), n_frames=3
        )


def test_summarize_passes_clear_records() -> None:
    records = [
        {"expected": "clear", "vision_judge": 4.6, "artifact_rate": 0.0},
        {"expected": "clear", "vision_judge": 4.4, "artifact_rate": 0.05},
    ]
    summary = summarize_judgments(records)
    assert summary["pass"] is True
    assert summary["mean_vision_judge"] == 4.5
    assert summary["artifact_rate"] == 0.025
    assert summary["mean_case_accuracy"] == 1.0


def test_summarize_detects_defective_and_gates_clear() -> None:
    records = [
        {"expected": "defective", "vision_judge": 2.0, "artifact_rate": 0.5},
        {"expected": "clear", "vision_judge": 5.0, "artifact_rate": 0.0},
    ]
    summary = summarize_judgments(records)
    assert summary["pass"] is True
    assert summary["mean_case_accuracy"] == 1.0
    assert summary["mean_vision_judge"] == 5.0

    slipped = summarize_judgments(
        [
            {"expected": "defective", "vision_judge": 4.8, "artifact_rate": 0.0},
            {"expected": "clear", "vision_judge": 5.0, "artifact_rate": 0.0},
        ]
    )
    assert slipped["pass"] is False
    assert "detection_accuracy_gate" in slipped["fail_reason"]


def test_summarize_fails_gate_and_missing_records() -> None:
    breached = summarize_judgments(
        [
            {"expected": "clear", "vision_judge": 3.0, "artifact_rate": 0.2},
            {"expected": "clear", "vision_judge": 4.9, "artifact_rate": 0.0},
        ]
    )
    assert breached["pass"] is False
    assert "vision_judge_gate" in breached["fail_reason"]
    assert "artifact_rate_gate" in breached["fail_reason"]

    with_missing = summarize_judgments(
        [
            {"expected": "clear", "vision_judge": 4.8, "artifact_rate": 0.0},
            {"expected": "clear", "error": "APIError 429"},
        ]
    )
    assert with_missing["pass"] is False
    assert "missing_vision_judge" in with_missing["fail_reason"]
    assert "detection_accuracy_gate" in with_missing["fail_reason"]

    empty = summarize_judgments([])
    assert empty["pass"] is False
    assert empty["fail_reason"] == "no_records"


def test_vision_summary_gates_every_render() -> None:
    clean = vision_summary([{"vision_judge": 5.0}, {"vision_judge": 4.4}])
    assert clean["mean_vision_judge"] == 4.7
    assert clean["n_judged"] == 2
    assert clean["vision_fail_reason"] == ""

    breached = vision_summary([{"vision_judge": 3.5}, {"vision_judge": 4.0}])
    assert breached["mean_vision_judge"] == 3.75
    assert breached["vision_fail_reason"] == "vision_judge_gate"

    unjudged = vision_summary(
        [{"vision_judge": 4.8}, {"error": "429 RESOURCE_EXHAUSTED"}]
    )
    assert unjudged["n_judged"] == 1
    assert "missing_vision_judge" in unjudged["vision_fail_reason"]

    empty = vision_summary([])
    assert empty["mean_vision_judge"] == 0.0
    assert empty["vision_fail_reason"] == "missing_vision_judge,vision_judge_gate"
