"""TDD: dispatch next ranked work; tick green; budget parks the rest."""

from __future__ import annotations

from backend.jobs.models import Job
from backend.supervisor.finishing_loop import (
    dispatch_next,
    on_finishing_terminal,
)


class _Queue:
    def __init__(self) -> None:
        self.jobs: list[Job] = []

    def submit(self, job: Job) -> None:
        self.jobs.append(job)


def _item(**kwargs: object) -> dict:
    station = str(kwargs["station"])
    return {
        "id": str(kwargs.get("id") or station),
        "station": station,
        "status": str(kwargs.get("status") or "waiting"),
        "impact": str(kwargs.get("impact") or "high"),
        "kind": str(kwargs.get("kind") or "defect"),
        "summary": station,
        "shot_id": str(kwargs.get("shot_id") or "shot-a"),
        "source_uri": "gs://b/c.mp4",
        "cost_estimate_micros": int(kwargs.get("cost") or 80_000),
        "proposal": {"kind": "station_job", "station": station, "args": {}},
    }


def test_dispatch_starts_what_fits_and_parks_the_rest() -> None:
    queue = _Queue()
    doc = {
        "budget_micros": 100_000,
        "spent_micros": 0,
        "items": [
            _item(station="loudness", cost=80_000),
            _item(station="extend", cost=3_000_000, impact="medium"),
        ],
    }
    out = dispatch_next(doc, queue=queue, project_id="p")
    assert out["items"][0]["status"] == "queued"
    assert out["items"][1]["status"] == "waiting"
    assert len(queue.jobs) == 1
    assert queue.jobs[0].station == "loudness"


def test_after_green_tick_next_waiting_job_starts() -> None:
    queue = _Queue()
    doc = {
        "budget_micros": 5_000_000,
        "spent_micros": 0,
        "items": [
            _item(id="j1", station="loudness", status="queued", cost=80_000),
            _item(
                id="w2",
                station="extend",
                status="waiting",
                cost=100_000,
                impact="medium",
            ),
        ],
    }
    doc["items"][0]["job_id"] = "job-loud"
    finished = Job(
        id="job-loud",
        station="loudness",
        project_id="p",
        input_refs=["gs://b/c.mp4"],
        status="passed",
        cost_micros=80_000,
    )
    out = on_finishing_terminal(doc, finished, queue=queue, project_id="p")
    assert out["items"][0]["status"] == "passed"
    assert out["spent_micros"] == 80_000
    assert out["items"][1]["status"] == "queued"
    assert queue.jobs[0].station == "extend"


def test_budget_gone_leaves_waiting_for_human() -> None:
    queue = _Queue()
    doc = {
        "budget_micros": 80_000,
        "spent_micros": 80_000,
        "items": [
            _item(id="j1", station="loudness", status="passed", cost=80_000),
            _item(id="w2", station="extend", status="waiting", cost=100_000),
        ],
    }
    out = dispatch_next(doc, queue=queue, project_id="p")
    assert out["items"][1]["status"] == "waiting"
    assert queue.jobs == []


def test_dispatch_waits_on_orchestrator_dependency() -> None:
    queue = _Queue()
    doc = {
        "budget_micros": 10_000_000,
        "spent_micros": 0,
        "items": [
            _item(id="loudness::shot-a", station="loudness", cost=80_000),
            _item(
                id="extend::shot-a",
                station="extend",
                cost=100_000,
                impact="medium",
            ),
        ],
    }
    doc["items"][1]["blocked_by"] = ["loudness::shot-a"]
    out = dispatch_next(doc, queue=queue, project_id="p")
    assert out["items"][0]["status"] == "queued"
    assert out["items"][1]["status"] == "waiting"
    assert [job.station for job in queue.jobs] == ["loudness"]
    doc["items"][0]["status"] = "passed"
    doc["items"][0]["job_id"] = "job-loud"
    queue2 = _Queue()
    out2 = dispatch_next(doc, queue=queue2, project_id="p")
    assert out2["items"][1]["status"] == "queued"
    assert queue2.jobs[0].station == "extend"


def test_one_generative_in_flight_per_shot() -> None:
    queue = _Queue()
    doc = {
        "budget_micros": 10_000_000,
        "spent_micros": 0,
        "items": [
            _item(id="r", station="relight", cost=100_000, kind="improvement"),
            _item(id="e", station="extend", cost=100_000, impact="medium"),
        ],
    }
    out = dispatch_next(doc, queue=queue, project_id="p")
    started = [i["station"] for i in out["items"] if i["status"] == "queued"]
    parked = [i["station"] for i in out["items"] if i["status"] == "waiting"]
    assert started == ["relight"]
    assert parked == ["extend"]
    assert len(queue.jobs) == 1


def test_items_from_rank_keep_waiting_until_dispatch() -> None:
    from backend.supervisor.finishing_loop import items_from_rank
    from backend.supervisor.inspect import validate_inspect_note
    from backend.supervisor.rank import rank_notes

    loud = validate_inspect_note(
        {
            "station": "loudness",
            "agent": "loudness_strategy",
            "status": "needs_work",
            "impact": "high",
            "kind": "defect",
            "summary": "unhearable",
            "cost_estimate_micros": 80_000,
            "proposal": {"kind": "station_job", "station": "loudness", "args": {}},
            "shot_id": "shot-a",
        }
    )
    ranked = rank_notes([loud], shot_order={"shot-a": 0})
    items = items_from_rank(ranked, source_by_shot={"shot-a": "gs://b/c.mp4"})
    assert items[0]["status"] == "waiting"
    assert items[0]["source_uri"] == "gs://b/c.mp4"
    assert items[0]["proposal"]["station"] == "loudness"
