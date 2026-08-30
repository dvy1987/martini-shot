"""A-5 RED tests: jobs/handoff.py — Turnover-manifest gate at station
transitions, silent mode (spec S0b, AC-S0b.1). Pure-logic checks here; the
annotation write goes to REAL Firestore in the integration module.
"""

import hashlib
from pathlib import Path

from backend.jobs.handoff import HandoffValidator, sha256_file

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "spike" / "shot-01-meadow.mp4"
)

MANIFEST_OK = {
    "version": 1,
    "project_id": "p-1",
    "from_station": "ingest",
    "to_station": "loudness",
    "files": [
        {"ref": "gs://b/shot-01.mp4", "sha256": "a" * 64, "bytes": 100},
    ],
}


def delivered(ref: str = "gs://b/shot-01.mp4", sha: str = "a" * 64) -> list[dict]:
    return [{"ref": ref, "sha256": sha, "bytes": 100}]


def test_complete_manifest_passes() -> None:
    validator = HandoffValidator.without_store()
    result = validator.validate(MANIFEST_OK, delivered(), job_id="job-x")
    assert result.passed is True
    assert result.codes == []


def test_missing_file_blocks_with_reason_code() -> None:
    validator = HandoffValidator.without_store()
    result = validator.validate(
        MANIFEST_OK, delivered(ref="gs://b/other.mp4"), job_id="job-x"
    )
    assert result.passed is False
    assert "MISSING_FILE" in result.codes
    assert "gs://b/shot-01.mp4" in result.blocked_files


def test_checksum_mismatch_blocks() -> None:
    validator = HandoffValidator.without_store()
    result = validator.validate(MANIFEST_OK, delivered(sha="b" * 64), job_id="job-x")
    assert result.passed is False
    assert "CHECKSUM_MISMATCH" in result.codes


def test_count_mismatch_blocks() -> None:
    validator = HandoffValidator.without_store()
    manifest = {
        **MANIFEST_OK,
        "files": [
            {"ref": "gs://b/a.mp4", "sha256": "a" * 64, "bytes": 1},
            {"ref": "gs://b/b.mp4", "sha256": "a" * 64, "bytes": 1},
        ],
    }
    result = validator.validate(manifest, delivered(), job_id="job-x")
    assert result.passed is False
    assert "COUNT_MISMATCH" in result.codes


def test_malformed_manifest_blocks() -> None:
    validator = HandoffValidator.without_store()
    result = validator.validate({"version": 99}, delivered(), job_id="job-x")
    assert result.passed is False
    assert "MANIFEST_INVALID" in result.codes


def test_sha256_file_matches_hashlib() -> None:
    assert sha256_file(FIXTURE) == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
