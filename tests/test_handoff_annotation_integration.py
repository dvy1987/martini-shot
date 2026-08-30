"""A-5 RED tests (AC-S0b.1, integration): a blocked transition must write a
REAL annotation to Firestore referencing the job_id (C-4.3 audit trail).
Zero mocks — the Grafana mirror lands with B-2; the spine record is real.
"""

import uuid

import pytest

from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.jobs.handoff import HandoffValidator

pytestmark = pytest.mark.integration

MANIFEST = {
    "version": 1,
    "project_id": "it-h",
    "from_station": "ingest",
    "to_station": "loudness",
    "files": [{"ref": "gs://b/missing.mp4", "sha256": "a" * 64, "bytes": 1}],
}


def test_blocked_transition_writes_annotation_with_job_id() -> None:
    settings = get_settings()
    assert settings.gcp_project_id, "real-service law C-6.2"
    store = get_firestore(settings)
    validator = HandoffValidator(store)
    job_id = f"job-it-{uuid.uuid4().hex[:8]}"

    result = validator.validate(MANIFEST, [], job_id=job_id)
    assert result.passed is False
    assert result.annotation_id is not None

    doc = store.get_doc("pc-annotations", result.annotation_id)
    assert doc is not None
    assert doc["job_id"] == job_id
    assert "MISSING_FILE" in doc["codes"]
    assert doc["type"] == "handoff.blocked"
    assert doc["at"].endswith("Z")

    store.delete_doc("pc-annotations", result.annotation_id)
    assert store.get_doc("pc-annotations", result.annotation_id) is None


def test_passing_transition_writes_no_annotation() -> None:
    settings = get_settings()
    store = get_firestore(settings)
    validator = HandoffValidator(store)
    ok_manifest = {
        **MANIFEST,
        "files": [{"ref": "gs://b/ok.mp4", "sha256": "a" * 64, "bytes": 1}],
    }
    result = validator.validate(
        ok_manifest,
        [{"ref": "gs://b/ok.mp4", "sha256": "a" * 64, "bytes": 1}],
        job_id=f"job-it-{uuid.uuid4().hex[:8]}",
    )
    assert result.passed is True
    assert result.annotation_id is None
