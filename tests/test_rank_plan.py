"""TDD: orchestrator plan — intelligence ranks; code only refuses invented work."""

from __future__ import annotations

from backend.supervisor.inspect import empty_note, validate_inspect_note
from backend.supervisor.rank import apply_orchestrator_plan, note_key, parse_rank_json


def _note(**kwargs: object):
    station = str(kwargs["station"])
    return validate_inspect_note(
        {
            "station": station,
            "agent": str(kwargs.get("agent") or station),
            "status": "needs_work",
            "impact": str(kwargs.get("impact") or "high"),
            "kind": str(kwargs.get("kind") or "defect"),
            "summary": str(kwargs.get("summary") or "x"),
            "cost_estimate_micros": int(kwargs.get("cost_estimate_micros") or 100_000),
            "proposal": {"kind": "station_job", "station": station, "args": {}},
            "shot_id": str(kwargs.get("shot_id") or "shot-a"),
        }
    )


def test_plan_follows_orchestrator_order_not_band_sort() -> None:
    dolly = _note(station="camera_language", impact="low", kind="improvement")
    mix = _note(station="loudness", impact="high", kind="defect")
    pickup = _note(station="pickups", impact="medium", kind="improvement")
    plan = apply_orchestrator_plan(
        [dolly, mix, pickup],
        {
            "order": [
                "loudness::shot-a",
                "pickups::shot-a",
                "camera_language::shot-a",
            ],
            "reason": "hear the scene, then clean flicker, craft last",
        },
    )
    assert [n.station for n in plan.ordered] == [
        "loudness",
        "pickups",
        "camera_language",
    ]
    assert "hear the scene" in plan.reason


def test_plan_records_dependencies() -> None:
    mix = _note(station="loudness", impact="high")
    extend = _note(station="extend", impact="medium", kind="improvement")
    plan = apply_orchestrator_plan(
        [mix, extend],
        {
            "order": ["loudness::shot-a", "extend::shot-a"],
            "dependencies": [
                {
                    "before": "loudness::shot-a",
                    "after": "extend::shot-a",
                    "reason": "match hearable dialogue before generating more of it",
                }
            ],
            "reason": "mix then extend",
        },
    )
    assert plan.blocked_by[note_key(extend)] == [note_key(mix)]


def test_plan_cannot_invent_a_station() -> None:
    mix = _note(station="loudness", impact="high")
    plan = apply_orchestrator_plan(
        [mix],
        {
            "order": ["trailer_bench::shot-a", "loudness::shot-a"],
            "reason": "illegal invent",
        },
    )
    assert [n.station for n in plan.ordered] == ["loudness"]


def test_plan_cannot_dispatch_empty() -> None:
    mix = _note(station="loudness", impact="high")
    plan = apply_orchestrator_plan(
        [empty_note("coverage"), mix],
        {
            "order": ["coverage::shot-a", "loudness::shot-a"],
            "reason": "empty is not work",
        },
    )
    assert [n.station for n in plan.ordered] == ["loudness"]


def test_forgotten_needs_work_is_appended_not_lost() -> None:
    mix = _note(station="loudness", impact="high")
    extend = _note(station="extend", impact="medium", kind="improvement")
    plan = apply_orchestrator_plan(
        [mix, extend],
        {"order": ["loudness::shot-a"], "reason": "forgot extend"},
    )
    assert [n.station for n in plan.ordered] == ["loudness", "extend"]


def test_parse_rank_json_extracts_object() -> None:
    payload = parse_rank_json(
        'noise\n{"order": ["loudness::shot-a"], "reason": "ok"}\n'
    )
    assert payload["order"] == ["loudness::shot-a"]
