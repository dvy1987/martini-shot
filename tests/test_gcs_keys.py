"""GCS object refs: stations store gs:// URIs; the client needs object keys."""

from __future__ import annotations

import pytest

from backend.core.gcs import object_key


def test_object_key_passes_plain_keys_through() -> None:
    assert object_key("e3/ep-01.mp4") == "e3/ep-01.mp4"
    assert object_key("projects/batch/dubs/job.wav") == "projects/batch/dubs/job.wav"


def test_object_key_strips_gs_uri() -> None:
    """E-3 jobs store gs://martini-shot-media/e3/ep-01.mp4. download_bytes
    used that string as the object name and 404'd on
    martini-shot-media/gs://martini-shot-media/e3/ep-01.mp4."""
    assert object_key("gs://martini-shot-media/e3/ep-01.mp4") == "e3/ep-01.mp4"


def test_object_key_rejects_bucket_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match"):
        object_key(
            "gs://other-bucket/e3/ep-01.mp4",
            bucket="martini-shot-media",
        )


def test_object_key_rejects_empty_and_bucket_only() -> None:
    with pytest.raises(ValueError):
        object_key("")
    with pytest.raises(ValueError, match="missing object key"):
        object_key("gs://martini-shot-media")
    with pytest.raises(ValueError, match="missing object key"):
        object_key("gs://martini-shot-media/")
