"""A-3 RED tests: jobs/models.py — Job shape, UTC ISO-8601 (C-6.4), micro-units."""

from backend.jobs.models import Job, new_job_id


def test_job_defaults_and_roundtrip() -> None:
    job = Job(station="ingest", project_id="p-1", input_refs=["gs://b/f.mp4"])
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.cost_micros == 0
    assert job.error is None
    assert job.input_refs == ["gs://b/f.mp4"]
    data = job.to_dict()
    assert Job.from_dict(data) == job


def test_new_job_id_is_unique_and_prefixed() -> None:
    ids = {new_job_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(i.startswith("job-") for i in ids)


def test_timestamps_are_utc_iso() -> None:
    job = Job(station="ingest", project_id="p-1", input_refs=[])
    assert job.created_at.endswith("Z")
    assert "T" in job.created_at


def test_status_vocabulary_is_closed() -> None:
    job = Job(station="s", project_id="p", input_refs=[])
    for status in ("queued", "leased", "passed", "failed"):
        job.status = status  # must not raise
