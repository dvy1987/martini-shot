"""A-2 RED tests: core/firestore.py — REAL Firestore round-trip on a temp doc
(plan A-2 DoD: integration test creates/reads/deletes a real document).
Zero mocks (C-1.2): real Firestore Native database on the real project.
"""

import time
import uuid

import pytest

from backend.core.config import get_settings
from backend.core.firestore import FirestoreStore, get_firestore

pytestmark = pytest.mark.integration


@pytest.fixture()
def store() -> FirestoreStore:
    settings = get_settings()
    assert settings.gcp_project_id, (
        "GCP_PROJECT_ID must be configured (real-service law C-6.2)"
    )
    return get_firestore(settings)


def test_set_get_delete_temp_doc(store: FirestoreStore) -> None:
    doc_id = f"it-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    collection = "integration-test"
    doc = {"station": "integration", "cost_micros": 0, "at": "2026-08-30T00:00:00Z"}
    try:
        store.set_doc(collection, doc_id, doc)
        read_back = store.get_doc(collection, doc_id)
        assert read_back is not None
        assert read_back["station"] == "integration"
        assert read_back["cost_micros"] == 0
    finally:
        store.delete_doc(collection, doc_id)
    assert store.get_doc(collection, doc_id) is None


def test_get_missing_doc_returns_none(store: FirestoreStore) -> None:
    assert store.get_doc("integration-test", "never-existed-xyz") is None
