"""TDD: walk-away rails — upload order, mandatory mix then pickups, spine notes.

Gemini looks (leftover agents, spend pricing, orchestrator) are EDD.
These tests only lock the sequence and that the billed payload is complete.
"""

from __future__ import annotations

from backend.jobs.models import Job
from backend.supervisor.adk_finishing import rank_payload
from backend.supervisor.finishing_loop import (
    CLEANUP_STATIONS,
    PROPOSE_STATIONS,
    apply_cleanup_artifacts,
    cleanup_finished,
    collect_original_refs,
    collect_spine_note,
    mandatory_cleanup_items,
    on_finishing_terminal,
    picture_mix_uri,
    stamp_ingest_watch,
)
from backend.supervisor.inspect import DEFAULT_COST_MICROS


class _Queue:
    def __init__(self) -> None:
        self.jobs: list[Job] = []

    def submit(self, job: Job) -> None:
        self.jobs.append(job)


class _Store:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def list_where(self, _collection: str, _field: str, _value: object) -> list[dict]:
        return list(self.rows)


def test_originals_follow_ingest_created_at_not_firestore_shuffle() -> None:
    store = _Store(
        [
            {
                "station": "ingest",
                "status": "passed",
                "created_at": "2026-09-07T12:00:02.000Z",
                "input_refs": ["gs://b/c.mp4"],
            },
            {
                "station": "ingest",
                "status": "passed",
                "created_at": "2026-09-07T12:00:00.000Z",
                "input_refs": ["gs://b/a.mp4"],
            },
            {
                "station": "ingest",
                "status": "passed",
                "created_at": "2026-09-07T12:00:01.000Z",
                "input_refs": ["gs://b/b.mp4"],
            },
            {
                "station": "loudness",
                "status": "passed",
                "created_at": "2026-09-07T11:00:00.000Z",
                "input_refs": ["gs://b/noise.mp4"],
            },
        ]
    )
    assert collect_original_refs(store, "p") == [
        "gs://b/a.mp4",
        "gs://b/b.mp4",
        "gs://b/c.mp4",
    ]


def test_originals_can_be_bound_to_an_explicit_ingest_batch_order() -> None:
    store = _Store(
        [
            {
                "id": "old",
                "station": "ingest",
                "status": "passed",
                "created_at": "2026-09-07T11:00:00.000Z",
                "input_refs": ["gs://b/old.mp4"],
            },
            {
                "id": "job-b",
                "station": "ingest",
                "status": "passed",
                "created_at": "2026-09-07T12:00:00.000Z",
                "input_refs": ["gs://b/b.mp4"],
            },
            {
                "id": "job-a",
                "station": "ingest",
                "status": "passed",
                "created_at": "2026-09-07T12:00:01.000Z",
                "input_refs": ["gs://b/a.mp4"],
            },
        ]
    )
    assert collect_original_refs(store, "p", ["job-a", "job-b"]) == [
        "gs://b/a.mp4",
        "gs://b/b.mp4",
    ]


def test_mandatory_cleanup_is_loudness_then_pickups_per_shot_in_upload_order() -> None:
    items = mandatory_cleanup_items(
        shots=[
            ("shot-b", "gs://b/b.mp4", 1),
            ("shot-a", "gs://b/a.mp4", 0),
        ],
        scene_by_shot={
            "shot-a": {
                "ingested": True,
                "spoken_words": "Hello.",
                "scene": "A doorway.",
            },
            "shot-b": {
                "ingested": True,
                "spoken_words": "",
                "scene": "Wind on a field.",
            },
        },
    )
    stations = [row["station"] for row in items]
    shots = [row["shot_id"] for row in items]
    assert stations == ["loudness", "pickups", "loudness", "pickups"]
    assert shots == ["shot-a", "shot-a", "shot-b", "shot-b"]
    assert items[0]["blocked_by"] == []
    assert items[1]["blocked_by"] == ["loudness::shot-a"]
    assert items[2]["blocked_by"] == ["loudness::shot-a"]
    assert items[3]["blocked_by"] == ["loudness::shot-b"]
    assert items[0]["spoken_words"] == "Hello."
    assert items[2]["spoken_words"] == ""
    assert items[0]["phase"] == "cleanup"
    assert "extend" not in stations
    assert items[0]["cost_estimate_micros"] == DEFAULT_COST_MICROS["loudness"]
    assert items[1]["cost_estimate_micros"] == DEFAULT_COST_MICROS["pickups"]


def test_cleanup_not_finished_while_a_pickup_is_waiting() -> None:
    items = mandatory_cleanup_items(
        shots=[("shot-a", "gs://b/a.mp4", 0)],
        scene_by_shot={
            "shot-a": {"ingested": True, "spoken_words": "", "scene": "Bars."}
        },
    )
    items[0]["status"] = "passed"
    assert cleanup_finished(items) is False
    items[1]["status"] = "passed"
    assert cleanup_finished(items) is True


def test_cleanup_finished_requires_cleanup_rows() -> None:
    assert cleanup_finished([]) is False
    assert (
        cleanup_finished(
            [
                {
                    "station": "extend",
                    "status": "waiting",
                    "phase": "propose",
                }
            ]
        )
        is False
    )


def test_picture_mix_uri_only_for_picture_artifacts() -> None:
    picture = Job(
        station="loudness",
        project_id="p",
        input_refs=["gs://b/a.mp4"],
        status="passed",
        result={"artifact_ref": "gs://b/mix.mp4"},
    )
    wav = Job(
        station="loudness",
        project_id="p",
        input_refs=["gs://b/a.mp4"],
        status="passed",
        result={"artifact_ref": "gs://b/mix.wav"},
    )
    assert picture_mix_uri(picture) == "gs://b/mix.mp4"
    assert picture_mix_uri(wav) is None


def test_loudness_pass_points_pickups_at_picture_mix_and_stamps_continuation() -> None:
    items = mandatory_cleanup_items(
        shots=[
            ("shot-a", "gs://b/a.mp4", 0),
            ("shot-b", "gs://b/b.mp4", 1),
        ],
        scene_by_shot={
            "shot-a": {"ingested": True, "spoken_words": "Hi.", "scene": "Cafe."},
            "shot-b": {"ingested": True, "spoken_words": "Bye.", "scene": "Street."},
        },
    )
    items[0]["status"] = "queued"
    items[0]["job_id"] = "job-loud-a"
    doc = {"items": items, "shot_order": {"shot-a": 0, "shot-b": 1}, "spent_micros": 0}
    job = Job(
        id="job-loud-a",
        station="loudness",
        project_id="p",
        input_refs=["gs://b/a.mp4"],
        status="passed",
        cost_micros=80_000,
        result={
            "worklist_item": "loudness::shot-a",
            "artifact_ref": "gs://b/a-mix.mp4",
            "target_lufs": -16.0,
            "dialogue_band_lufs": -20.5,
            "room_band_lufs": -24.0,
            "scene_class": "normal-with-dialogue",
            "shot_id": "shot-a",
        },
    )
    apply_cleanup_artifacts(doc, job)
    pick_a = next(row for row in doc["items"] if row["id"] == "pickups::shot-a")
    loud_b = next(row for row in doc["items"] if row["id"] == "loudness::shot-b")
    assert pick_a["source_uri"] == "gs://b/a-mix.mp4"
    assert loud_b["proposal"]["args"].get("previous_target_lufs") == -16.0
    assert loud_b["proposal"]["args"].get("previous_dialogue_band_lufs") == -20.5
    assert loud_b["proposal"]["args"].get("previous_room_band_lufs") == -24.0
    assert (
        loud_b["proposal"]["args"].get("previous_scene_class") == "normal-with-dialogue"
    )
    assert loud_b["proposal"]["args"].get("continuation") is True


def test_propose_stations_exclude_ingest_loudness_pickups() -> None:
    assert "ingest" not in PROPOSE_STATIONS
    assert "loudness" not in PROPOSE_STATIONS
    assert "pickups" not in PROPOSE_STATIONS
    assert "extend" in PROPOSE_STATIONS
    assert "dub" in PROPOSE_STATIONS
    assert set(CLEANUP_STATIONS) == {"loudness", "pickups"}


def test_rank_payload_includes_empty_spine_explicitly() -> None:
    payload = rank_payload(
        remaining_micros=1_000,
        shot_order={"shot-a": 0},
        candidates=[{"id": "extend::shot-a", "station": "extend"}],
        scene_by_shot={"shot-a": {"spoken_words": "Hello.", "scene": "A door."}},
        orchestrator_spine=[],
    )
    assert payload["orchestrator_spine"] == []
    assert payload["scene_by_shot"]["shot-a"]["spoken_words"] == "Hello."


def test_rank_payload_carries_handoff_spine_notes() -> None:
    payload = rank_payload(
        remaining_micros=1_000,
        shot_order={"shot-a": 0},
        candidates=[],
        orchestrator_spine=[
            {
                "shot_id": "shot-a",
                "station": "loudness",
                "note": (
                    "Ingest look had not run. Ran ingest understand now "
                    "and wrote spoken words and scene description onto the shot."
                ),
                "spoken_words": "The door is open.",
                "scene": "A blue field.",
            }
        ],
    )
    assert payload["orchestrator_spine"][0]["shot_id"] == "shot-a"
    assert "wrote" in payload["orchestrator_spine"][0]["note"].lower()


def test_terminal_copies_handoff_note_onto_spine() -> None:
    items = mandatory_cleanup_items(
        shots=[("shot-a", "gs://b/a.mp4", 0)],
        scene_by_shot={
            "shot-a": {"ingested": True, "spoken_words": "Hi.", "scene": "Cafe."}
        },
    )
    items[0]["status"] = "queued"
    items[0]["job_id"] = "job-loud"
    doc = {
        "items": items,
        "budget_micros": 10_000_000,
        "spent_micros": 0,
        "orchestrator_spine": [],
    }
    job = Job(
        id="job-loud",
        station="loudness",
        project_id="p",
        input_refs=["gs://b/a.mp4"],
        status="passed",
        cost_micros=80_000,
        result={
            "worklist_item": "loudness::shot-a",
            "handoff_orchestrator_note": "Metadata was lost in transit; restored from the shot.",
            "spoken_words": "Hi.",
            "scene": "Cafe.",
            "shot_id": "shot-a",
        },
    )
    note = collect_spine_note(job)
    assert note is not None
    assert "lost in transit" in note["note"].lower()
    out = on_finishing_terminal(doc, job, queue=_Queue(), project_id="p")
    assert any(
        "lost in transit" in str(row.get("note") or "").lower()
        for row in (out.get("orchestrator_spine") or [])
    )


def test_on_finishing_terminal_does_not_start_extend_during_cleanup() -> None:
    queue = _Queue()
    items = mandatory_cleanup_items(
        shots=[("shot-a", "gs://b/a.mp4", 0)],
        scene_by_shot={
            "shot-a": {"ingested": True, "spoken_words": "", "scene": "Bars."}
        },
    )
    items[0]["status"] = "queued"
    items[0]["job_id"] = "job-loud"
    doc = {
        "items": items,
        "budget_micros": 10_000_000,
        "spent_micros": 0,
        "proposals_started": False,
    }
    job = Job(
        id="job-loud",
        station="loudness",
        project_id="p",
        input_refs=["gs://b/a.mp4"],
        status="passed",
        cost_micros=80_000,
        result={"worklist_item": "loudness::shot-a", "shot_id": "shot-a"},
    )
    out = on_finishing_terminal(doc, job, queue=queue, project_id="p")
    assert [row["station"] for row in out["items"]] == ["loudness", "pickups"]
    assert out["items"][1]["status"] == "queued"
    assert queue.jobs[0].station == "pickups"
    assert cleanup_finished(out["items"]) is False


def test_stamp_ingest_watch_writes_notes_onto_the_file_check_job() -> None:
    class Store:
        def __init__(self) -> None:
            self.doc = {"result": {"probe": {"duration_s": 4}}}

        def transactional_update(
            self, collection: str, doc_id: str, mutate: object
        ) -> None:
            assert collection == "pc-jobs"
            assert doc_id == "job-1"
            self.doc = mutate(self.doc)  # type: ignore[operator]

    store = Store()
    stamp_ingest_watch(
        store,
        "job-1",
        {"ingested": True, "spoken_words": "", "scene": "A doorway."},
    )
    assert store.doc["result"]["ingested"] is True
    assert store.doc["result"]["spoken_words"] == ""
    assert store.doc["result"]["scene"] == "A doorway."
    assert store.doc["result"]["probe"]["duration_s"] == 4
