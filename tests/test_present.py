"""G1 presenter: lease-queue status names → /api/v1 Job contract."""

from backend.api.present import approval_to_api, job_to_api, project_to_api
from backend.jobs.models import Job


def test_leased_job_is_running_on_the_wire() -> None:
    job = Job(station="ingest", project_id="g1", input_refs=["k"], id="job-abc")
    job.status = "leased"
    body = job_to_api(job)
    assert body["job_id"] == "job-abc"
    assert body["status"] == "running"


def test_passed_job_is_pass_and_carries_checksum() -> None:
    job = Job(station="ingest", project_id="g1", input_refs=["k"])
    job.status = "passed"
    job.checksum_sha256 = "abc"
    body = job_to_api(job)
    assert body["status"] == "pass"
    assert body["checksum_sha256"] == "abc"
    assert body["error"] is None


def test_failed_job_wraps_error_envelope() -> None:
    job = Job(station="ingest", project_id="g1", input_refs=["k"])
    job.status = "failed"
    job.error = "object missing"
    body = job_to_api(job)
    assert body["status"] == "fail"
    assert body["error"] == {"code": "job_failed", "message": "object missing"}


def test_project_health_failing_when_any_job_failed() -> None:
    failed = Job(station="ingest", project_id="g1", input_refs=[])
    failed.status = "failed"
    body = project_to_api(
        project_id="g1",
        title="Gate G1",
        created_at="2026-09-01T00:00:00Z",
        jobs=[failed],
    )
    assert body["health"] == "failing"
    assert body["station_counts"] == {"ingest": 1}


def test_approval_presenter_keeps_kind_and_proposed_status() -> None:
    body = approval_to_api(
        {
            "approval_id": "ap-1",
            "project_id": "g1",
            "kind": "spend",
            "title": "Hourly cap",
            "created_at": "2026-09-01T00:00:00Z",
            "status": "proposed",
            "cost_delta_micros": 4000,
        }
    )
    assert body["approval_id"] == "ap-1"
    assert body["kind"] == "spend"
    assert body["status"] == "proposed"
    assert body["cost_delta_micros"] == 4000
