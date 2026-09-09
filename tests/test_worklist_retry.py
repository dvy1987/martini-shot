"""TDD: operator retry — stalled Execute/Delivery items resume from their
exact stall point.

Retry resets failed, budget-paused, AND needs_human worklist items back to
waiting so dispatch re-runs ONLY those steps: same proposal, same source
clip (which already carries any passed upstream artifacts). A human may
have already fixed whatever raised needs_human out of band; retry lets the
rest of the run continue instead of leaving that step stuck forever. Only
passed work is left alone.

Route tests run the real install_finish_routes wiring against in-memory
persistence (same labeled-test-double pattern as test_finishing_flow.py);
no live services are billed here.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.events import EventHub
from backend.api.finish import install_finish_routes
from backend.supervisor.finishing_loop import (
    accept_stalled_item,
    retry_stalled_item,
    retry_stalled_items,
)


def _item(
    item_id: str,
    station: str,
    status: str,
    *,
    shot_id: str = "shot-1",
    source_uri: str = "gs://b/a.mp4",
    job_id: str | None = None,
    blocked_by: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": item_id,
        "station": station,
        "status": status,
        "impact": "high",
        "kind": "defect",
        "summary": f"{station} work",
        "shot_id": shot_id,
        "source_uri": source_uri,
        "cost_estimate_micros": 1_000_000,
        "proposal": {"kind": "station_job", "station": station, "args": {}},
        "blocked_by": list(blocked_by or []),
        "phase": "propose",
    }
    if job_id is not None:
        row["job_id"] = job_id
    row.update(extra)
    return row


def test_retry_resets_failed_paused_and_needs_human_items_to_waiting() -> None:
    doc = {
        "project_id": "p",
        "budget_micros": 50_000_000,
        "spent_micros": 1_000_000,
        "items": [
            _item("loudness::shot-1", "loudness", "passed", job_id="job-pass"),
            _item(
                "relight::shot-1",
                "relight",
                "failed",
                job_id="job-fail",
                retries=0,
            ),
            _item("pickups::shot-2", "pickups", "paused", job_id="job-paused"),
            _item("extend::shot-3", "extend", "needs_human", job_id="job-human"),
        ],
    }

    updated = retry_stalled_items(doc)

    by_id = {str(row["id"]): row for row in updated["items"]}
    assert by_id["relight::shot-1"]["status"] == "waiting"
    assert by_id["relight::shot-1"]["retries"] == 1
    assert by_id["relight::shot-1"]["retry_of"] == "job-fail"
    assert by_id["relight::shot-1"].get("job_id") is None
    assert by_id["pickups::shot-2"]["status"] == "waiting"
    assert by_id["pickups::shot-2"]["retries"] == 1
    # A human may have already fixed what needs_human was waiting on —
    # retry gives that fix a chance to carry the run forward.
    assert by_id["extend::shot-3"]["status"] == "waiting"
    assert by_id["extend::shot-3"]["retries"] == 1
    assert by_id["extend::shot-3"]["retry_of"] == "job-human"
    # Passed work is the only thing never touched.
    assert by_id["loudness::shot-1"]["status"] == "passed"
    assert by_id["loudness::shot-1"]["job_id"] == "job-pass"


def test_retry_keeps_the_stall_point_source_and_proposal() -> None:
    """A failed pickups step re-runs on the mix loudness already produced."""
    doc = {
        "project_id": "p",
        "budget_micros": 50_000_000,
        "spent_micros": 0,
        "items": [
            _item(
                "pickups::shot-1",
                "pickups",
                "failed",
                source_uri="gs://b/mix-shot-1.wav",
                job_id="job-pick",
            ),
        ],
    }

    updated = retry_stalled_items(doc)

    row = updated["items"][0]
    assert row["source_uri"] == "gs://b/mix-shot-1.wav"
    assert row["proposal"] == {"kind": "station_job", "station": "pickups", "args": {}}


def test_retry_counts_repeat_attempts() -> None:
    doc = {
        "project_id": "p",
        "budget_micros": 50_000_000,
        "spent_micros": 0,
        "items": [
            _item(
                "relight::shot-1",
                "relight",
                "failed",
                job_id="job-fail-2",
                retries=1,
                retry_of="job-fail-1",
            ),
        ],
    }

    updated = retry_stalled_items(doc)

    row = updated["items"][0]
    assert row["retries"] == 2
    assert row["retry_of"] == "job-fail-2"


def test_retry_stalled_item_resets_only_the_job_it_names() -> None:
    """The table view offers Retry per row now, not just for the whole
    worklist — it must never touch a second stalled item just because it
    also happens to be failed."""
    doc = {
        "project_id": "p",
        "budget_micros": 50_000_000,
        "spent_micros": 0,
        "items": [
            _item("relight::shot-1", "relight", "failed", job_id="job-fail-1"),
            _item("pickups::shot-4", "pickups", "needs_human", job_id="job-fail-2"),
        ],
    }

    updated = retry_stalled_item(doc, "job-fail-2")

    by_id = {str(row["id"]): row for row in updated["items"]}
    assert by_id["pickups::shot-4"]["status"] == "waiting"
    assert by_id["pickups::shot-4"]["retries"] == 1
    assert by_id["pickups::shot-4"]["retry_of"] == "job-fail-2"
    assert by_id["pickups::shot-4"].get("job_id") is None
    # The unrelated failed row is left exactly alone.
    assert by_id["relight::shot-1"]["status"] == "failed"
    assert by_id["relight::shot-1"]["job_id"] == "job-fail-1"


def test_retry_stalled_item_raises_when_no_item_references_the_job() -> None:
    doc = {"project_id": "p", "budget_micros": 1, "spent_micros": 0, "items": []}

    try:
        retry_stalled_item(doc, "job-missing")
    except LookupError:
        pass
    else:
        raise AssertionError("expected a LookupError")


def test_retry_stalled_item_raises_when_the_item_is_not_stalled() -> None:
    doc = {
        "project_id": "p",
        "budget_micros": 1,
        "spent_micros": 0,
        "items": [_item("loudness::shot-1", "loudness", "passed", job_id="job-pass")],
    }

    try:
        retry_stalled_item(doc, "job-pass")
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError")


def test_accept_stalled_item_marks_it_passed_without_touching_the_job() -> None:
    """Accept unblocks the run but never rewrites the AI's own verdict —
    the job doc's needs_human/failed history stays honest; only the
    worklist item (which governs dispatch) moves to passed."""
    doc = {
        "project_id": "p",
        "budget_micros": 1,
        "spent_micros": 0,
        "items": [
            _item(
                "pickups::shot-4",
                "pickups",
                "needs_human",
                job_id="job-shaky",
                shot_id="shot-4",
            ),
        ],
    }

    updated = accept_stalled_item(doc, "job-shaky")

    row = updated["items"][0]
    assert row["status"] == "passed"
    assert row["accepted_by_operator"] is True
    assert isinstance(row["accepted_at"], str) and row["accepted_at"]
    # Still points at the same (flagged) job — accept never retries.
    assert row["job_id"] == "job-shaky"


def test_accept_stalled_item_also_accepts_a_plain_failure() -> None:
    doc = {
        "project_id": "p",
        "budget_micros": 1,
        "spent_micros": 0,
        "items": [_item("relight::shot-1", "relight", "failed", job_id="job-fail")],
    }

    updated = accept_stalled_item(doc, "job-fail")

    assert updated["items"][0]["status"] == "passed"


def test_accept_stalled_item_refuses_a_budget_pause() -> None:
    """Paused is a budget throttle, not a quality judgment a human can
    wave through — accepting it would silently hide a spend problem."""
    doc = {
        "project_id": "p",
        "budget_micros": 1,
        "spent_micros": 0,
        "items": [_item("pickups::shot-2", "pickups", "paused", job_id="job-paused")],
    }

    try:
        accept_stalled_item(doc, "job-paused")
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError")


def test_accept_stalled_item_raises_when_no_item_references_the_job() -> None:
    doc = {"project_id": "p", "budget_micros": 1, "spent_micros": 0, "items": []}

    try:
        accept_stalled_item(doc, "job-missing")
    except LookupError:
        pass
    else:
        raise AssertionError("expected a LookupError")


class _Queue:
    def __init__(self) -> None:
        self.jobs: list[Any] = []

    def submit(self, job: Any) -> None:
        self.jobs.append(job)


class _Store:
    def __init__(self, docs: dict[str, dict[str, Any]], rows: list[dict[str, Any]]):
        self.docs = docs
        self.rows = rows

    def get_doc(self, _collection: str, doc_id: str) -> dict[str, Any] | None:
        return self.docs.get(doc_id)

    def set_doc(
        self, _collection: str, doc_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.docs[doc_id] = payload
        return payload

    def list_where(
        self, _collection: str, _field: str, _value: object
    ) -> list[dict[str, Any]]:
        return list(self.rows)


class _Settings:
    api_key = "test-key"  # pragma: allowlist secret
    grafana_stack_url = ""


def _client(docs: dict[str, dict[str, Any]], rows: list[dict[str, Any]]):
    queue = _Queue()
    store = _Store(docs, rows)
    app = FastAPI()
    install_finish_routes(
        app,
        queue=queue,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        hub=EventHub(),
        settings=_Settings(),  # type: ignore[arg-type]
    )
    return TestClient(app), queue, store


def _stalled_worklist() -> dict[str, Any]:
    return {
        "project_id": "p",
        "budget_micros": 50_000_000,
        "spent_micros": 2_000_000,
        "status": "idle",
        "original_refs": ["gs://b/a.mp4"],
        "items": [
            _item("loudness::shot-1", "loudness", "passed", job_id="job-pass"),
            _item(
                "relight::shot-1",
                "relight",
                "failed",
                job_id="job-fail",
                blocked_by=["loudness::shot-1"],
            ),
            _item(
                "delivery::shot-1",
                "delivery",
                "failed",
                job_id="job-deliv",
                blocked_by=["relight::shot-1"],
            ),
        ],
    }


def test_retry_route_redispatches_only_the_stalled_steps() -> None:
    client, queue, store = _client({"p": _stalled_worklist()}, [])

    response = client.post("/api/v1/projects/p/worklist/retry")

    assert response.status_code == 200
    doc = response.json()
    by_id = {str(row["id"]): row for row in doc["items"]}
    assert by_id["loudness::shot-1"]["status"] == "passed"
    # The stalled relight re-dispatched first; delivery stays blocked on it
    # exactly as in a live run — it re-runs from its own stall point next.
    assert by_id["relight::shot-1"]["status"] == "queued"
    assert by_id["relight::shot-1"]["retries"] == 1
    assert by_id["delivery::shot-1"]["status"] == "waiting"
    assert len(queue.jobs) == 1
    assert queue.jobs[0].station == "relight"
    assert doc["status"] == "running"
    # Persisted and published for the board.
    assert store.docs["p"]["items"][1]["status"] == "queued"


def test_retry_route_also_redispatches_needs_human_items() -> None:
    """A human may have fixed the thing needs_human was waiting on; retry
    lets that fix carry the run forward instead of leaving it stuck."""
    worklist = _stalled_worklist()
    worklist["items"][1]["status"] = "needs_human"

    client, queue, _store = _client({"p": worklist}, [])

    response = client.post("/api/v1/projects/p/worklist/retry")

    assert response.status_code == 200
    doc = response.json()
    by_id = {str(row["id"]): row for row in doc["items"]}
    assert by_id["relight::shot-1"]["status"] == "queued"
    assert by_id["relight::shot-1"]["retries"] == 1
    assert len(queue.jobs) == 1
    assert queue.jobs[0].station == "relight"


def test_retry_route_404s_without_a_worklist() -> None:
    client, _queue, _store = _client({}, [])

    response = client.post("/api/v1/projects/p/worklist/retry")

    assert response.status_code == 404


def test_retry_route_retries_a_stalled_item_even_while_another_is_active() -> None:
    """A failed relight is retryable even while an unrelated delivery job
    on the same worklist is still queued — retry never touches active
    items, so there is nothing to double-dispatch."""
    worklist = _stalled_worklist()
    worklist["items"].append(
        _item(
            "delivery::shot-2",
            "delivery",
            "queued",
            shot_id="shot-2",
            job_id="job-other-delivery",
        )
    )
    client, queue, _store = _client({"p": worklist}, [])

    response = client.post("/api/v1/projects/p/worklist/retry")

    assert response.status_code == 200
    doc = response.json()
    by_id = {str(row["id"]): row for row in doc["items"]}
    assert by_id["relight::shot-1"]["status"] == "queued"
    assert by_id["delivery::shot-2"]["status"] == "queued"
    assert by_id["delivery::shot-2"]["job_id"] == "job-other-delivery"
    assert len(queue.jobs) == 1
    assert queue.jobs[0].station == "relight"


def test_retry_route_refuses_before_the_work_plan_exists() -> None:
    worklist = _stalled_worklist()
    worklist["status"] = "inspecting"
    client, _queue, _store = _client({"p": worklist}, [])

    response = client.post("/api/v1/projects/p/worklist/retry")

    assert response.status_code == 409


def test_retry_route_is_a_truthful_noop_when_nothing_is_stalled() -> None:
    worklist = _stalled_worklist()
    for row in worklist["items"]:
        row["status"] = "passed"
    client, queue, _store = _client({"p": worklist}, [])

    response = client.post("/api/v1/projects/p/worklist/retry")

    assert response.status_code == 200
    assert queue.jobs == []
    assert response.json()["status"] == "idle"


def test_retry_item_route_retries_only_the_row_it_names() -> None:
    """The table view's per-row Retry button — must not touch a second
    stalled row just because it is also failed."""
    worklist = _stalled_worklist()
    worklist["items"].append(
        _item(
            "pickups::shot-4",
            "pickups",
            "needs_human",
            shot_id="shot-4",
            job_id="job-shaky",
        )
    )
    client, queue, store = _client({"p": worklist}, [])

    response = client.post("/api/v1/projects/p/worklist/retry/job-shaky")

    assert response.status_code == 200
    doc = response.json()
    by_id = {str(row["id"]): row for row in doc["items"]}
    assert by_id["pickups::shot-4"]["status"] == "queued"
    assert by_id["pickups::shot-4"]["retries"] == 1
    # The other, unrelated failed row from the fixture is untouched.
    assert by_id["relight::shot-1"]["status"] == "failed"
    assert queue.jobs[0].station == "pickups"
    assert store.docs["p"]["items"][-1]["status"] == "queued"


def test_retry_item_route_404s_when_the_job_is_not_in_the_worklist() -> None:
    client, _queue, _store = _client({"p": _stalled_worklist()}, [])

    response = client.post("/api/v1/projects/p/worklist/retry/no-such-job")

    assert response.status_code == 404


def test_retry_item_route_409s_when_the_row_is_not_stalled() -> None:
    client, _queue, _store = _client({"p": _stalled_worklist()}, [])

    response = client.post("/api/v1/projects/p/worklist/retry/job-pass")

    assert response.status_code == 409


def test_retry_item_route_404s_without_a_worklist() -> None:
    client, _queue, _store = _client({}, [])

    response = client.post("/api/v1/projects/p/worklist/retry/job-fail")

    assert response.status_code == 404


def test_accept_item_route_unblocks_a_dependent_row() -> None:
    """Accepting the flagged relight lets the delivery row waiting on it
    dispatch — the whole point of Accept is to let the run continue."""
    worklist = _stalled_worklist()
    worklist["items"][1]["status"] = "needs_human"  # relight::shot-1
    worklist["items"][2]["status"] = (
        "waiting"  # delivery::shot-1, still queued behind it
    )
    client, queue, store = _client({"p": worklist}, [])

    response = client.post("/api/v1/projects/p/worklist/accept/job-fail")

    assert response.status_code == 200
    doc = response.json()
    by_id = {str(row["id"]): row for row in doc["items"]}
    assert by_id["relight::shot-1"]["status"] == "passed"
    assert by_id["relight::shot-1"]["accepted_by_operator"] is True
    # Accept never retries — the job it points at is still the flagged one.
    assert by_id["relight::shot-1"]["job_id"] == "job-fail"
    # Delivery was only blocked on relight; it is now free to dispatch.
    assert by_id["delivery::shot-1"]["status"] == "queued"
    assert queue.jobs[0].station == "delivery"
    assert store.docs["p"]["items"][1]["accepted_by_operator"] is True


def test_accept_item_route_404s_when_the_job_is_not_in_the_worklist() -> None:
    client, _queue, _store = _client({"p": _stalled_worklist()}, [])

    response = client.post("/api/v1/projects/p/worklist/accept/no-such-job")

    assert response.status_code == 404


def test_accept_item_route_409s_when_the_row_is_not_acceptable() -> None:
    """A queued/active row, or a plain budget pause, is not something a
    human accepts — those aren't quality judgments to wave through."""
    client, _queue, _store = _client({"p": _stalled_worklist()}, [])

    response = client.post("/api/v1/projects/p/worklist/accept/job-pass")

    assert response.status_code == 409


def test_accept_item_route_404s_without_a_worklist() -> None:
    client, _queue, _store = _client({}, [])

    response = client.post("/api/v1/projects/p/worklist/accept/job-fail")

    assert response.status_code == 404
