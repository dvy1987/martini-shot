"""Pytest bootstrap: make the repo root importable for `backend.*` imports
regardless of how pytest is invoked (python -m pytest, plain pytest, IDE).
Also hosts the shared real-Firestore fixtures for the approval machinery
suites (H-0): per-run collections keep tests isolated (C-6.2)."""

import sys
import uuid
from pathlib import Path

import pytest

ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture()
def env():
    from backend.core.config import get_settings
    from backend.core.firestore import get_firestore

    settings = get_settings()
    assert settings.gcp_project_id, "real-service law C-6.2: GCP project required"
    return get_firestore(settings)


@pytest.fixture()
def run_id() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture()
def approvals_col(run_id) -> str:
    return f"it-approvals-{run_id}"


@pytest.fixture()
def jobs_col(run_id) -> str:
    return f"it-jobs-{run_id}"
