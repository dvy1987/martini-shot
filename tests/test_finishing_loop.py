"""TDD: pause mid-job and assemble originals + passed only."""

from __future__ import annotations

from backend.jobs.models import Job
from backend.supervisor.finishing_loop import assemble_final, pause_inflight


def test_assemble_keeps_originals_and_only_passed_jobs() -> None:
    originals = ["gs://bucket/projects/p/ingest/job-1/a.mp4"]
    passed = Job(
        station="loudness",
        project_id="p",
        input_refs=originals,
        status="passed",
        result={"artifact_ref": "gs://bucket/projects/p/loudness/mix.wav"},
    )
    failed = Job(
        station="extend",
        project_id="p",
        input_refs=originals,
        status="failed",
        result={"artifact_ref": "gs://bucket/projects/p/extend/half.mp4"},
    )
    paused = Job(
        station="relight",
        project_id="p",
        input_refs=originals,
        status="leased",
        result={"artifact_ref": "gs://bucket/projects/p/relight/partial.mp4"},
    )
    refs = assemble_final(
        original_refs=originals,
        jobs=[passed, failed, paused],
    )
    assert originals[0] in refs
    assert "gs://bucket/projects/p/loudness/mix.wav" in refs
    assert "gs://bucket/projects/p/extend/half.mp4" not in refs
    assert "gs://bucket/projects/p/relight/partial.mp4" not in refs


def test_pause_inflight_excludes_unfinished_from_final() -> None:
    originals = ["gs://bucket/src.mp4"]
    inflight = Job(
        station="extend",
        project_id="p",
        input_refs=originals,
        status="leased",
        result={"artifact_ref": "gs://bucket/half.mp4"},
    )
    paused = pause_inflight([inflight], remaining_micros=0)
    assert paused[0].status == "throttled"
    assert paused[0].error == "paused: finishing budget exhausted"
    refs = assemble_final(original_refs=originals, jobs=paused)
    assert refs == originals


def test_source_uri_survives_pause() -> None:
    originals = ["gs://bucket/projects/p/ingest/keep-me.mp4"]
    inflight = Job(
        station="corrections",
        project_id="p",
        input_refs=originals,
        status="leased",
    )
    paused = pause_inflight([inflight], remaining_micros=0)
    assert paused[0].input_refs == originals
    assert assemble_final(original_refs=originals, jobs=paused) == originals
