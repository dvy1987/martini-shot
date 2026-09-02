"""EventHub SSE envelope (type / at / payload)."""

from backend.api.events import EventHub


def test_publish_carries_type_at_payload() -> None:
    hub = EventHub()
    queue = hub.subscribe("g1")
    hub.publish("g1", "job.updated", {"job_id": "job-x"})
    event = queue.get_nowait()
    assert event["type"] == "job.updated"
    assert isinstance(event["at"], str) and event["at"].endswith("Z")
    assert event["payload"] == {"job_id": "job-x"}
    hub.unsubscribe("g1", queue)
    hub.unsubscribe("g1", queue)  # missing subscriber is a no-op
