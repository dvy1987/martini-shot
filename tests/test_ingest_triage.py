"""TDD for the Ingest Triage station agent (A10-3) + read-only batch state."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.supervisor.batch_state import read_ingest_batch_state
from backend.supervisor.station_agents.base import StationDecisionError
from backend.supervisor.station_agents.ingest_triage import (
    DECISIONS,
    SUGGESTION,
    build_prompt,
    decide_ingest_triage,
    parse_triage_decision,
    suggestion_for_report,
)

REPORT: dict[str, Any] = {
    "job_id": "cyc-b1-ep-04-en-ingest",
    "source_ref": "sources/tape-3/ep-04.mp4",
    "verdict": "quarantined",
    "reason_code": "corrupt_decode",
    "probe": {"duration_s": 0.0, "has_audio": False, "codec": "h264"},
    "checksum_sha256": "ab" * 32,
}

SIBLINGS: list[dict[str, Any]] = [
    {
        "episode_id": "ep-01",
        "status": "pass",
        "error": None,
        "source_ref": "sources/tape-3/ep-01.mp4",
    },
    {
        "episode_id": "ep-02",
        "status": "quarantined",
        "error": "corrupt_decode",
        "source_ref": "sources/tape-3/ep-02.mp4",
    },
    {
        "episode_id": "ep-03",
        "status": "quarantined",
        "error": "corrupt_decode",
        "source_ref": "sources/tape-3/ep-03.mp4",
    },
    {
        "episode_id": "ep-05",
        "status": "pass",
        "error": None,
        "source_ref": "sources/tape-3/ep-05.mp4",
    },
]


def test_suggestion_maps_reason_codes() -> None:
    assert SUGGESTION["empty_payload"] == "re_ingest"
    assert SUGGESTION["corrupt_probe"] == "re_ingest"
    assert SUGGESTION["corrupt_decode"] == "re_ingest"
    assert SUGGESTION["missing_audio"] == "reject"
    # Unknown reason -> conservative escalation.
    assert suggestion_for_report({"reason_code": "weird"}) == "needs_human"


def test_prompt_contains_report_and_batch_context() -> None:
    prompt = build_prompt(REPORT, SIBLINGS)
    assert "corrupt_decode" in prompt
    assert "tape-3/ep-04.mp4" in prompt
    # Batch correlation is first-class: siblings and their failures visible.
    assert "ep-02" in prompt and "ep-03" in prompt
    assert "2 of 4" in prompt  # deterministic anomaly summary
    # The upstream-cause rule is explicit: correlate, escalate once.
    assert "upstream" in prompt.lower()
    assert "re_ingest|salvage|reject|needs_human" in prompt


def test_parse_valid_decision() -> None:
    text = json.dumps(
        {
            "agent": "ingest_triage",
            "decision": "needs_human",
            "batch_correlation": "upstream_cause",
            "reason": "5 of 8 episodes from tape-3 fail decode identically",
            "confidence": "high",
        }
    )
    decision = parse_triage_decision(text, REPORT)
    assert decision.decision == "needs_human"
    assert DECISIONS[0] == "re_ingest"


def test_parse_tolerates_fences() -> None:
    text = (
        "```json\n"
        + json.dumps(
            {
                "agent": "ingest_triage",
                "decision": "re_ingest",
                "batch_correlation": "none",
                "reason": "isolated decode failure",
                "confidence": "medium",
            }
        )
        + "\n```"
    )
    decision = parse_triage_decision(text, REPORT)
    assert decision.decision == "re_ingest"


def test_parse_fails_loud_on_bad_enum() -> None:
    text = json.dumps(
        {
            "agent": "ingest_triage",
            "decision": "maybe",
            "batch_correlation": "none",
            "reason": "x",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_triage_decision(text, REPORT)


def test_parse_fails_loud_on_missing_reason() -> None:
    text = json.dumps(
        {
            "agent": "ingest_triage",
            "decision": "re_ingest",
            "batch_correlation": "none",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_triage_decision(text, REPORT)


def test_decide_uses_one_metered_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(_settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        return {
            "text": json.dumps(
                {
                    "agent": "ingest_triage",
                    "decision": "needs_human",
                    "batch_correlation": "upstream_cause",
                    "reason": "identical decode failures across tape-3",
                    "confidence": "high",
                }
            ),
            "model": "gemini-3.7-flash",
            "cost_micros": 1234,
        }

    monkeypatch.setattr("backend.supervisor.otel_ai.run_agent_call", fake_call)
    decision, cost = decide_ingest_triage(object(), report=REPORT, batch_state=SIBLINGS)
    assert cost == 1234
    assert len(calls) == 1
    assert "corrupt_decode" in calls[0]["prompt"]
    assert decision.decision == "needs_human"


class _FakeStore:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.queries: list[tuple[str, str, Any]] = []

    def list_where(
        self, collection: str, field: str, value: object
    ) -> list[dict[str, Any]]:
        self.queries.append((collection, field, value))
        return [d for d in self.docs if d.get("result", {}).get("batch_id") == value]


def test_read_ingest_batch_state_is_read_only_and_normalized() -> None:
    docs = [
        {
            "id": "cyc-b1-ep-01-en-ingest",
            "station": "ingest",
            "status": "pass",
            "error": None,
            "result": {"batch_id": "b1", "episode_id": "ep-01", "batch": {}},
        },
        {
            "id": "cyc-b1-ep-02-en-ingest",
            "station": "ingest",
            "status": "quarantined",
            "error": "corrupt_decode",
            "result": {
                "batch_id": "b1",
                "episode_id": "ep-02",
                "input_refs": ["sources/tape-3/ep-02.mp4"],
            },
        },
        {
            "id": "cyc-b1-ep-01-en-dub",
            "station": "dub",
            "status": "pass",
            "error": None,
            "result": {"batch_id": "b1", "episode_id": "ep-01"},
        },
    ]
    store = _FakeStore(docs)
    rows = read_ingest_batch_state(store, "b1")
    # Read-only: exactly one query, no writes.
    assert store.queries == [("pc-jobs", "result.batch_id", "b1")]
    # Ingest jobs only, normalized to the triage view.
    assert [r["episode_id"] for r in rows] == ["ep-01", "ep-02"]
    assert rows[1]["error"] == "corrupt_decode"
    assert rows[1]["source_ref"] == "sources/tape-3/ep-02.mp4"
