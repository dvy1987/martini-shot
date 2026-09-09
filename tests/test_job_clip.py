"""Resolve before/after clip refs and operator-facing names for a job."""

from backend.jobs.clip import (
    clip_metadata,
    clip_name,
    job_has_after_change,
    resolve_clip_ref,
)
from backend.jobs.models import Job


def test_clip_name_uses_the_file_name_not_the_job_id() -> None:
    assert (
        clip_name("projects/show-1/ingest/job-abc/test-clip01.mp4") == "test-clip01.mp4"
    )
    assert clip_name("gs://bucket/shows/night/take-02.mov") == "take-02.mov"


def test_before_ref_is_the_input_clip() -> None:
    job = Job(
        station="loudness",
        project_id="p1",
        input_refs=["projects/p1/ingest/job-1/cafe.mp4"],
        result={"artifact_ref": "gs://bucket/mixes/cafe-loud.mp4"},
    )
    assert resolve_clip_ref(job, "before") == "projects/p1/ingest/job-1/cafe.mp4"
    assert resolve_clip_ref(job, "after") == "gs://bucket/mixes/cafe-loud.mp4"


def test_upload_after_is_the_arriving_file() -> None:
    job = Job(station="ingest", project_id="p1", input_refs=["projects/p1/a.mp4"])
    job.status = "passed"
    assert resolve_clip_ref(job, "after") == "projects/p1/a.mp4"


def test_ingest_check_is_not_an_after_change_until_metadata_lands() -> None:
    queued = Job(station="ingest", project_id="p1", input_refs=["projects/p1/a.mp4"])
    assert job_has_after_change(queued) is False
    passed = Job(
        station="ingest",
        project_id="p1",
        input_refs=["projects/p1/a.mp4"],
        result={"probe": {"duration_s": 10.0, "codec": "h264"}},
    )
    passed.status = "passed"
    assert job_has_after_change(passed) is True
    assert clip_metadata(passed)["codec"] == "h264"


def test_clip_metadata_includes_scene_and_spoken_words() -> None:
    job = Job(
        station="ingest",
        project_id="p1",
        input_refs=["projects/p1/a.mp4"],
        result={"scene": "A quiet cafe.", "spoken_words": "Two coffees."},
    )
    meta = clip_metadata(job)
    assert meta["scene"] == "A quiet cafe."
    assert meta["spoken_words"] == "Two coffees."


def test_watch_notes_are_filled_from_the_shot_when_the_ingest_job_lacks_them() -> None:
    from backend.jobs.clip import clip_body, project_watch_notes

    job = Job(
        station="ingest",
        project_id="p1",
        input_refs=["projects/p1/a.mp4"],
        id="job-abc",
        result={"probe": {"duration_s": 4.0}},
    )
    job.status = "passed"

    class _Store:
        def list_where(self, collection: str, field: str, value: str) -> list[dict]:
            if collection == "pc-shots":
                return [
                    {
                        "project_id": "p1",
                        "title": "projects/p1/a.mp4",
                        "scene_understanding": {
                            "ingested": True,
                            "scene": "A quiet cafe.",
                            "spoken_words": "Two coffees.",
                        },
                    }
                ]
            return []

    extra = project_watch_notes(job, _Store())
    body = clip_body(job, "after", extra=extra)
    assert body["metadata"]["scene"] == "A quiet cafe."
    assert body["metadata"]["spoken_words"] == "Two coffees."
    assert body["metadata"]["duration_s"] == 4.0


def test_clip_body_points_at_the_lab_media_path() -> None:
    job = Job(
        station="ingest",
        project_id="p1",
        input_refs=["projects/p1/a.mp4"],
        id="job-abc",
    )
    from backend.jobs.clip import clip_body

    body = clip_body(job, "before")
    assert body["url"] == "/api/v1/jobs/job-abc/clip/before/media"
    assert body["clip_name"] == "a.mp4"


def test_clip_body_uses_a_hosted_signed_url_when_gcs_can_sign() -> None:
    job = Job(
        station="ingest",
        project_id="p1",
        input_refs=["projects/p1/a.mp4"],
        id="job-abc",
    )

    class _GCS:
        def signed_download_url(self, key: str, *, expires_minutes: int = 60) -> str:
            assert key == "projects/p1/a.mp4"
            assert expires_minutes == 60
            return f"https://storage.googleapis.com/martini-shot-media/{key}?X-Goog-Signature=test"

    from backend.jobs.clip import clip_body

    body = clip_body(job, "before", gcs=_GCS())
    assert body["url"].startswith("https://storage.googleapis.com/")
    assert "/clip/" not in body["url"]


def test_same_artifact_without_new_metadata_is_no_change() -> None:
    job = Job(
        station="pickups",
        project_id="p1",
        input_refs=["projects/p1/a.mp4"],
        result={"artifact_ref": "projects/p1/a.mp4"},
    )
    job.status = "passed"
    assert job_has_after_change(job) is False
