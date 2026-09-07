"""TDD: finishing InspectNote contract (walk-away loop)."""

from __future__ import annotations

import json

import pytest

from backend.stations.run import STATION_NAMES
from backend.supervisor.inspect import (
    InspectNoteError,
    attendance_rows,
    empty_note,
    validate_inspect_note,
)
from backend.supervisor.inspect_impl import run_inspect
from backend.supervisor.inspect_registry import ROSTER, inspector_for


def test_roster_matches_worker_stations() -> None:
    assert ROSTER == STATION_NAMES
    assert len(ROSTER) == 11


def test_empty_note_is_blank_not_all_good() -> None:
    note = empty_note("coverage")
    assert note.status == "empty"
    assert note.impact == "none"
    assert note.kind == "none"
    assert note.summary == ""
    assert note.proposal == {}
    assert note.cost_estimate_micros == 0


def test_attendance_always_has_every_roster_station() -> None:
    rows = attendance_rows([])
    assert [row.station for row in rows] == list(ROSTER)
    assert all(row.status == "empty" for row in rows)


def test_attendance_keeps_real_notes_in_roster_order() -> None:
    loud = validate_inspect_note(
        {
            "station": "loudness",
            "agent": "loudness_strategy",
            "status": "needs_work",
            "impact": "high",
            "kind": "defect",
            "summary": "Dialogue is unhearable at -25 LUFS",
            "cost_estimate_micros": 80_000,
            "proposal": {"kind": "station_job", "station": "loudness", "args": {}},
        }
    )
    rows = attendance_rows([loud])
    by_station = {row.station: row for row in rows}
    assert by_station["loudness"].status == "needs_work"
    assert by_station["extend"].status == "empty"


def test_impact_includes_medium() -> None:
    note = validate_inspect_note(
        {
            "station": "extend",
            "agent": "extend_qc",
            "status": "needs_work",
            "impact": "medium",
            "kind": "improvement",
            "summary": "Shot dies mid-gesture",
            "cost_estimate_micros": 3_000_000,
            "proposal": {
                "kind": "station_job",
                "station": "extend",
                "args": {"prompt": "Keep rolling through the line"},
            },
        }
    )
    assert note.impact == "medium"


def test_quality_improvement_is_needs_work() -> None:
    note = validate_inspect_note(
        {
            "station": "relight",
            "agent": "relight",
            "status": "needs_work",
            "impact": "high",
            "kind": "improvement",
            "summary": "Lighting is consistent but faces are in shadow",
            "cost_estimate_micros": 3_000_000,
            "proposal": {
                "kind": "station_job",
                "station": "relight",
                "args": {"preset": "practical_lamp"},
            },
        }
    )
    assert note.kind == "improvement"
    assert note.status == "needs_work"


def test_garbage_payload_fails_loud() -> None:
    with pytest.raises(InspectNoteError):
        validate_inspect_note({"station": "loudness", "status": "needs_work"})


def test_empty_cannot_carry_a_proposal() -> None:
    with pytest.raises(InspectNoteError, match="empty"):
        validate_inspect_note(
            {
                "station": "loudness",
                "agent": "loudness_strategy",
                "status": "empty",
                "impact": "none",
                "kind": "none",
                "summary": "all good",
                "cost_estimate_micros": 0,
                "proposal": {"kind": "station_job", "station": "loudness", "args": {}},
            }
        )


def test_spend_cannot_invent_creative_work() -> None:
    with pytest.raises(InspectNoteError, match="spend"):
        validate_inspect_note(
            {
                "station": "spend",
                "agent": "spend_steward",
                "status": "needs_work",
                "impact": "low",
                "kind": "improvement",
                "summary": "should relight this",
                "cost_estimate_micros": 1,
                "proposal": {
                    "kind": "station_job",
                    "station": "relight",
                    "args": {"preset": "noir"},
                },
            }
        )


def test_unregistered_station_has_no_inspector() -> None:
    assert inspector_for("not_a_station") is None


def test_relight_inspect_prompt_asks_about_dark_faces() -> None:
    from backend.supervisor.station_agents.relight import build_inspect_prompt

    text = build_inspect_prompt({"clip_uri": "gs://bucket/clip.mp4"})
    lowered = text.lower()
    assert "faces" in lowered
    assert "dark" in lowered or "shadow" in lowered


def test_parse_dark_faces_as_high_improvement() -> None:
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "relight",
                "agent": "relight",
                "status": "needs_work",
                "impact": "high",
                "kind": "improvement",
                "summary": "Faces unreadable in consistent shadow",
                "cost_estimate_micros": 3000000,
                "proposal": {
                    "kind": "station_job",
                    "station": "relight",
                    "args": {"preset": "practical_lamp"},
                },
            }
        ),
        "relight",
    )
    assert note.kind == "improvement"
    assert note.impact == "high"


def test_visual_inspect_without_frames_is_empty_not_a_guess() -> None:
    class _Cache:
        def parts_for(self, station: str, clip_uri: str) -> tuple[None, None, str]:
            return None, None, "no frames"

    note = run_inspect(
        "relight",
        settings=object(),
        context={"clip_uri": "gs://bucket/clip.mp4"},
        preview_cache=_Cache(),
    )
    assert note.status == "empty"
    assert note.summary == ""
