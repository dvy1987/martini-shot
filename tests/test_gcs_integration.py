"""A-2 RED tests: core/gcs.py — REAL GCS round-trip in the dev bucket (plan A-2
DoD: integration test creates/uploads/downloads/deletes real objects). Zero
mocks (C-1.2): the bucket is the real `martini-shot-media` on the real project.
"""

import uuid

import pytest

from backend.core.config import get_settings
from backend.core.gcs import GCSMedia, get_gcs

pytestmark = pytest.mark.integration


@pytest.fixture()
def media() -> GCSMedia:
    settings = get_settings()
    assert settings.gcp_project_id, (
        "GCP_PROJECT_ID must be configured (real-service law C-6.2)"
    )
    assert settings.gcs_bucket, "GCS_BUCKET must be configured"
    return get_gcs(settings)


def test_upload_download_delete_roundtrip(media: GCSMedia) -> None:
    key = f"integration-test/{uuid.uuid4().hex}.txt"
    payload = b"martini-shot a2 integration probe"
    try:
        assert media.exists(key) is False
        media.upload_bytes(key, payload, content_type="text/plain")
        assert media.exists(key) is True
        assert media.download_bytes(key) == payload
    finally:
        media.delete(key)
    assert media.exists(key) is False


def test_signed_download_url_is_https_and_bound_to_key(media: GCSMedia) -> None:
    url = media.signed_download_url("does-not-need-to-exist.bin", expires_minutes=10)
    assert url.startswith("https://storage.googleapis.com/")
    assert "does-not-need-to-exist.bin" in url
    assert "Signature=" in url
