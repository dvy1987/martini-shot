"""Ingest watch: spoken words + scene description on the shot.

File check still runs first. Gemini only watches a healthy clip. Both
fields are shot metadata. The orchestrator and later stations read them.
"""

from __future__ import annotations

import json

from backend.jobs.models import Job
from backend.shots import lifecycle as shots
from backend.stations.ingest.classify import REASON_EMPTY, classify_payload
from backend.supervisor.station_agents.ingest_understand import (
    build_prompt,
    parse_understand_decision,
    scene_understanding_from_shot,
)


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


class _GCS:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs

    def download_bytes(self, key: str) -> bytes:
        return self.blobs[key]


def test_silent_agent_cannot_invent_spoken_words() -> None:
    text = json.dumps(
        {
            "agent": "ingest_understand",
            "decision": "understood",
            "has_speech": False,
            "spoken_words": "Hello from a cafe that is not in this clip",
            "scene": "A solid blue frame",
            "reason": "I guessed dialogue",
            "confidence": "high",
        }
    )
    decision = parse_understand_decision(text)
    assert decision.raw.get("has_speech") is False
    assert decision.raw.get("spoken_words") == ""
    assert "blue" in str(decision.raw.get("scene") or "").lower()


def test_speech_keeps_the_line() -> None:
    text = json.dumps(
        {
            "agent": "ingest_understand",
            "decision": "understood",
            "has_speech": True,
            "spoken_words": "Hello, this is Martini Shot.",
            "scene": "Solid blue picture",
            "reason": "heard the line",
            "confidence": "high",
        }
    )
    decision = parse_understand_decision(text)
    assert decision.raw.get("has_speech") is True
    assert "martini" in str(decision.raw.get("spoken_words") or "").lower()


def test_prompt_asks_for_words_and_scene() -> None:
    prompt = build_prompt()
    lower = prompt.lower()
    assert "spoken" in lower
    assert "scene" in lower
    assert "do not invent" in lower or "not invent" in lower


def test_understanding_is_shot_metadata() -> None:
    store = _Store()
    shot_id = shots.ensure_shot(store, project_id="p1", title="ep-01")
    doc = shots.record_scene_understanding(
        store,
        shot_id,
        spoken_words="The door is open.",
        has_speech=True,
        scene="A blue field, no people.",
        cost_micros=1200,
    )
    shot = shots.get_shot(store, shot_id) or {}
    meta = shot["scene_understanding"]
    assert meta["spoken_words"] == "The door is open."
    assert meta["has_speech"] is True
    assert "blue" in meta["scene"]
    assert doc == meta
    loaded = scene_understanding_from_shot(store, shot_id)
    assert loaded is not None
    assert loaded["has_speech"] is True


def test_no_speech_metadata_clears_words() -> None:
    store = _Store()
    shot_id = shots.ensure_shot(store, project_id="p1", title="ep-01")
    shots.record_scene_understanding(
        store,
        shot_id,
        spoken_words="should be dropped",
        has_speech=False,
        scene="Color bars.",
        cost_micros=0,
    )
    meta = scene_understanding_from_shot(store, shot_id) or {}
    assert meta["has_speech"] is False
    assert meta["spoken_words"] == ""


def test_quarantine_does_not_watch_the_clip() -> None:
    from backend.stations.ingest.run import run_ingest

    class _BoomMedia:
        def probe(self, path):  # pragma: no cover - must not run
            raise AssertionError("quarantine must not probe empty")

        def decode_clean(self, path):  # pragma: no cover
            raise AssertionError("quarantine must not decode empty")

    job = Job(
        station="ingest",
        project_id="p1",
        input_refs=["gs://b/empty.mp4"],
        result={"shot_id": "shot-x"},
    )
    out = run_ingest(
        job,
        _GCS({"gs://b/empty.mp4": b""}),
        media=_BoomMedia(),  # type: ignore[arg-type]
        store=_Store(),
        settings=object(),
    )
    assert out.status == "quarantined"
    assert out.error == REASON_EMPTY
    assert "scene_understanding" not in (out.result or {})


def test_planning_prompt_carries_shot_scene_metadata() -> None:
    from backend.supervisor.station_agents.orchestrator import build_planning_prompt

    prompt = build_planning_prompt(
        {
            "episode_id": "ep-01",
            "language": "es-ES",
            "script": "",
            "context": {
                "scene_understanding": {
                    "spoken_words": "Hola.",
                    "has_speech": True,
                    "scene": "A woman waves from a doorway.",
                }
            },
        },
        default_chain=["ingest", "dub", "loudness", "delivery"],
    )
    lower = prompt.lower()
    assert "hola" in lower
    assert "doorway" in lower or "woman" in lower
    assert "scene" in lower


def test_empty_payload_still_classifies_before_any_watch() -> None:
    class _NoMedia:
        pass

    verdict, reason, probe = classify_payload(b"", _NoMedia())  # type: ignore[arg-type]
    assert verdict == "quarantined"
    assert reason == REASON_EMPTY
    assert probe == {}
