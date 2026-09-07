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


def _scene(
    *, ingested: bool = True, words: str = "Hello.", scene: str = "A cafe."
) -> dict:
    from backend.jobs.handoff import scene_bag_for_manifest

    return scene_bag_for_manifest(
        {"ingested": ingested, "spoken_words": words, "scene": scene}
    )


def test_require_scene_missing_blocks_when_unrepairable() -> None:
    validator = HandoffValidator.without_store()
    result = validator.validate(
        MANIFEST_OK,
        delivered(),
        job_id="job-x",
        require_scene=True,
    )
    assert result.passed is False
    assert "SCENE_MISSING" in result.codes
    assert "ingest" in result.orchestrator_note.lower()


def test_silence_scene_bag_passes() -> None:
    from backend.jobs.handoff import scene_bag_for_manifest

    bag = scene_bag_for_manifest(
        {"ingested": True, "spoken_words": "", "scene": "Color bars, no one speaks."}
    )
    manifest = {**MANIFEST_OK, "scene": bag}
    validator = HandoffValidator.without_store()
    result = validator.validate(
        manifest,
        delivered(),
        job_id="job-x",
        require_scene=True,
        delivered_scene=bag,
    )
    assert result.passed is True
    assert result.codes == []


def test_scene_mismatch_blocks_when_shot_has_nothing() -> None:
    bag = _scene(words="Hello.")
    other = _scene(words="Different line.")
    manifest = {**MANIFEST_OK, "scene": bag}
    validator = HandoffValidator.without_store()
    result = validator.validate(
        manifest,
        delivered(),
        job_id="job-x",
        require_scene=True,
        delivered_scene=other,
    )
    assert result.passed is False
    assert "SCENE_MISMATCH" in result.codes


def test_repairs_lost_metadata_from_shot() -> None:
    from backend.jobs.handoff import scene_bag_for_manifest
    from backend.shots import lifecycle as shots

    class _Store:
        def __init__(self) -> None:
            self.docs: dict[tuple[str, str], dict] = {}

        def get_doc(self, collection: str, doc_id: str):
            return self.docs.get((collection, doc_id))

        def set_doc(self, collection: str, doc_id: str, data: dict) -> None:
            self.docs[(collection, doc_id)] = data

        def transactional_update(self, collection: str, doc_id: str, fn) -> None:
            current = self.docs.get((collection, doc_id)) or {}
            self.docs[(collection, doc_id)] = fn(current)

    store = _Store()
    shot_id = shots.ensure_shot(store, project_id="p-1", title="clip")
    shots.record_scene_understanding(
        store,
        shot_id,
        spoken_words="The door is open.",
        has_speech=True,
        scene="A blue field.",
        cost_micros=1,
    )
    bag = scene_bag_for_manifest(
        {
            "ingested": True,
            "spoken_words": "The door is open.",
            "scene": "A blue field.",
        }
    )
    manifest = {**MANIFEST_OK, "scene": bag}
    validator = HandoffValidator(store=store)  # type: ignore[arg-type]
    result = validator.validate(
        manifest,
        delivered(),
        job_id="job-x",
        require_scene=True,
        shot_id=shot_id,
    )
    assert result.passed is True
    assert result.repaired is True
    assert result.repaired_scene is not None
    assert result.repaired_scene["spoken_words"] == "The door is open."
    assert "lost" in result.orchestrator_note.lower() or "restored" in (
        result.orchestrator_note.lower()
    )


def test_repairs_by_running_ingest_look_when_never_watched() -> None:
    from backend.shots import lifecycle as shots

    class _Store:
        def __init__(self) -> None:
            self.docs: dict[tuple[str, str], dict] = {}

        def get_doc(self, collection: str, doc_id: str):
            return self.docs.get((collection, doc_id))

        def set_doc(self, collection: str, doc_id: str, data: dict) -> None:
            self.docs[(collection, doc_id)] = data

        def transactional_update(self, collection: str, doc_id: str, fn) -> None:
            current = self.docs.get((collection, doc_id)) or {}
            self.docs[(collection, doc_id)] = fn(current)

    store = _Store()
    shot_id = shots.ensure_shot(store, project_id="p-1", title="clip")

    def fake_watch(_settings: object, _payload: bytes, _media: object):
        from backend.supervisor.station_agents.base import StationDecision

        return (
            StationDecision(
                agent="ingest_understand",
                decision="understood",
                reason="watched in repair",
                confidence="high",
                deterministic_advice="understood",
                overridden=False,
                raw={
                    "has_speech": True,
                    "spoken_words": "Hello from repair.",
                    "scene": "A doorway.",
                },
            ),
            12,
        )

    validator = HandoffValidator.without_store()
    result = validator.validate(
        MANIFEST_OK,
        delivered(),
        job_id="job-x",
        require_scene=True,
        shot_id=shot_id,
        store=store,
        settings=object(),
        payload=b"clip-bytes",
        media=object(),
        watch=fake_watch,
    )
    assert result.passed is True
    assert result.repaired is True
    assert result.repaired_scene is not None
    assert "hello from repair" in result.repaired_scene["spoken_words"].lower()
    assert "ingest" in result.orchestrator_note.lower()
    meta = shots.get_shot(store, shot_id) or {}
    assert (meta.get("scene_understanding") or {}).get("ingested") is True
