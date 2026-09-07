"""TDD: must-hear/must-see rank with defect-before-taste and generative mutex."""

from __future__ import annotations

from backend.supervisor.inspect import validate_inspect_note
from backend.supervisor.rank import budget_cut, rank_notes


def _note(**kwargs: object):
    station = str(kwargs["station"])
    payload = {
        "station": station,
        "agent": str(kwargs.get("agent") or station),
        "status": "needs_work",
        "impact": str(kwargs["impact"]),
        "kind": str(kwargs.get("kind") or "defect"),
        "summary": str(kwargs.get("summary") or "x"),
        "cost_estimate_micros": int(kwargs.get("cost_estimate_micros") or 100_000),
        "proposal": kwargs.get(
            "proposal",
            {"kind": "station_job", "station": station, "args": {}},
        ),
        "shot_id": str(kwargs.get("shot_id") or "shot-a"),
    }
    return validate_inspect_note(payload)


def test_high_beats_medium_beats_low() -> None:
    low = _note(station="pickups", impact="low", kind="improvement")
    medium = _note(station="delivery", impact="medium", kind="defect")
    high = _note(station="loudness", impact="high", kind="defect")
    ordered = rank_notes([low, medium, high], shot_order={"shot-a": 0}).ordered
    assert [n.station for n in ordered] == ["loudness", "delivery", "pickups"]


def test_empty_never_ranks() -> None:
    from backend.supervisor.inspect import empty_note

    high = _note(station="loudness", impact="high")
    ordered = rank_notes(
        [empty_note("coverage"), high], shot_order={"shot-a": 0}
    ).ordered
    assert [n.station for n in ordered] == ["loudness"]


def test_ok_leave_it_never_ranks_or_becomes_a_candidate() -> None:
    from backend.supervisor.rank_impl import _candidates

    leave = validate_inspect_note(
        {
            "station": "extend",
            "agent": "extend",
            "status": "ok",
            "impact": "none",
            "kind": "none",
            "summary": "Shot already lands",
            "cost_estimate_micros": 0,
            "shot_id": "shot-a",
        }
    )
    must = _note(
        station="extend",
        impact="medium",
        kind="defect",
        summary="Dies mid-thought",
        shot_id="shot-b",
    )
    ordered = rank_notes([leave, must], shot_order={"shot-a": 0, "shot-b": 1}).ordered
    assert [n.shot_id for n in ordered] == ["shot-b"]
    ids = [row["id"] for row in _candidates([leave, must])]
    assert ids == ["extend::shot-b"]


def test_defect_before_improvement_in_the_same_band() -> None:
    taste = _note(
        station="relight",
        impact="high",
        kind="improvement",
        summary="faces in shadow",
    )
    quiet = _note(station="loudness", impact="high", kind="defect")
    ordered = rank_notes([taste, quiet], shot_order={"shot-a": 0}).ordered
    assert [n.station for n in ordered] == ["loudness", "relight"]


def test_earlier_shot_before_later_in_the_same_band() -> None:
    later = _note(station="loudness", impact="high", shot_id="shot-b")
    earlier = _note(station="delivery", impact="high", shot_id="shot-a")
    ordered = rank_notes(
        [later, earlier], shot_order={"shot-a": 0, "shot-b": 1}
    ).ordered
    assert [n.shot_id for n in ordered] == ["shot-a", "shot-b"]


def test_cheaper_first_when_band_kind_and_shot_match() -> None:
    omni = _note(
        station="pickups",
        impact="medium",
        cost_estimate_micros=2_000_000,
    )
    mix = _note(
        station="loudness",
        impact="medium",
        cost_estimate_micros=80_000,
    )
    ordered = rank_notes([omni, mix], shot_order={"shot-a": 0}).ordered
    assert [n.station for n in ordered] == ["loudness", "pickups"]


def test_one_generative_picture_edit_per_shot() -> None:
    relight = _note(station="relight", impact="high", kind="improvement")
    extend = _note(station="extend", impact="medium", kind="improvement")
    mix = _note(station="loudness", impact="high", kind="defect")
    result = rank_notes(
        [relight, extend, mix],
        shot_order={"shot-a": 0},
    )
    dispatched = [n.station for n in result.ordered]
    assert "loudness" in dispatched
    generative = [s for s in dispatched if s in {"relight", "extend"}]
    assert len(generative) == 1
    assert "extend" in [n.station for n in result.waiting] or "relight" in [
        n.station for n in result.waiting
    ]


def test_budget_cut_parks_remainder_as_waiting_not_needs_human() -> None:
    a = _note(station="loudness", impact="high", cost_estimate_micros=80_000)
    b = _note(station="extend", impact="medium", cost_estimate_micros=3_000_000)
    take, wait = budget_cut([a, b], remaining_micros=100_000)
    assert [n.station for n in take] == ["loudness"]
    assert [n.station for n in wait] == ["extend"]


def test_low_dropped_when_it_would_starve_remaining_high() -> None:
    low = _note(
        station="camera_language",
        impact="low",
        kind="improvement",
        cost_estimate_micros=3_000_000,
    )
    high = _note(
        station="loudness",
        impact="high",
        cost_estimate_micros=80_000,
        shot_id="shot-b",
    )
    ordered = rank_notes(
        [low, high],
        shot_order={"shot-a": 0, "shot-b": 1},
        remaining_micros=3_000_000,
    ).ordered
    assert ordered[0].station == "loudness"
