"""Scene-aware loudness: pick a fitting level per scene, then mix.

Whisper is one example. An explosion, a crash of pans, a shout, or a
sudden disruption should sit louder than talk. Dialogue stays easy to
hear. The show stays in one loudness family. The meter still wins on
the number; this suite locks the TARGET table, the ffmpeg apply, the
dub-preferring input, and the orchestrator stamp.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.core.config import get_settings
from backend.core.media import FFmpeg
from backend.jobs.models import Job
from backend.stations.loudness.run import resolve_audio_ref, run_loudness
from backend.stations.loudness.scene import (
    SCENE_CLASSES,
    SPEECH_FLOOR_LUFS,
    clamp_agent_target,
    scene_target_lufs,
    season_median_lufs,
)
from backend.supervisor.orchestrator import batch_job_id, build_batch_jobs


def _media() -> FFmpeg:
    settings = get_settings()
    return FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)


def _sine_wav(media: FFmpeg, path: Path, *, seconds: float, volume_db: float) -> None:
    """Labeled synthetic INPUT (C-1.3): a sine at a known gain."""
    result = media._run(
        [
            media.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={seconds}",
            "-af",
            f"volume={volume_db}dB",
            str(path),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:400])


def test_scene_classes_cover_quiet_talk_and_loud_events() -> None:
    assert SCENE_CLASSES == (
        "silence",
        "whisper",
        "dialogue",
        "shout",
        "impact",
        "explosion",
    )


def test_whisper_is_quieter_than_talk_and_still_audible() -> None:
    whisper = scene_target_lufs("whisper")
    talk = scene_target_lufs("dialogue")
    assert whisper < talk
    assert whisper >= SPEECH_FLOOR_LUFS


def test_explosion_and_impact_are_louder_than_talk() -> None:
    talk = scene_target_lufs("dialogue")
    assert scene_target_lufs("shout") > talk
    assert scene_target_lufs("impact") > scene_target_lufs("shout")
    assert scene_target_lufs("explosion") > scene_target_lufs("impact")


def test_unknown_scene_class_fails_loud() -> None:
    with pytest.raises(ValueError, match="unknown scene class"):
        scene_target_lufs("whatever")


def test_speech_stays_near_the_show_median() -> None:
    median = season_median_lufs([-16.2, -16.0, -16.4])
    assert median == pytest.approx(-16.2)
    # A wild agent-side miss still cannot yank dialogue 20 LU off the show.
    pulled = scene_target_lufs("dialogue", season_median=median)
    assert abs(pulled - median) <= 8.0


def test_agent_may_nudge_two_lu_not_rewrite_the_table() -> None:
    table = scene_target_lufs("explosion")
    assert clamp_agent_target(table + 0.5, table) == pytest.approx(table + 0.5)
    assert clamp_agent_target(table + 9.0, table) == pytest.approx(table + 2.0)
    whisper = scene_target_lufs("whisper")
    assert clamp_agent_target(-40.0, whisper) >= SPEECH_FLOOR_LUFS


def test_apply_loudnorm_refuses_silent_slate() -> None:
    media = _media()
    slate = Path(__file__).resolve().parents[1] / "fixtures" / "g1" / "slate.mp4"
    with pytest.raises(RuntimeError, match="unmeterable"):
        media.apply_loudnorm(
            slate, slate.with_name("slate-mixed.mp4"), integrated_lufs=-16.0
        )


def test_apply_loudnorm_brings_a_quiet_tone_to_target(tmp_path: Path) -> None:
    media = _media()
    src = tmp_path / "quiet.wav"
    dst = tmp_path / "mixed.wav"
    _sine_wav(media, src, seconds=3.0, volume_db=-40.0)
    before = media.loudness_report(src)["lufs"]
    assert before < -25.0
    media.apply_loudnorm(src, dst, integrated_lufs=-16.0, true_peak_dbtp=-1.5)
    after = media.loudness_report(dst)["lufs"]
    assert abs(after - (-16.0)) <= 1.5


def test_resolve_audio_ref_prefers_the_dub_artifact() -> None:
    job = Job(
        station="loudness",
        project_id="batch",
        input_refs=["gs://b/e3/ep-01.mp4"],
        result={"dub_job_id": "cyc-demo-ep-01-es-ES-dub"},
    )

    class _Store:
        def get_doc(self, collection: str, doc_id: str) -> dict[str, Any] | None:
            assert collection == "pc-jobs"
            assert doc_id == "cyc-demo-ep-01-es-ES-dub"
            return {
                "status": "passed",
                "result": {
                    "artifact_ref": "gs://b/projects/batch/dubs/cyc-demo-ep-01-es-ES-dub.es-ES.wav"
                },
            }

    ref, kind = resolve_audio_ref(job, _Store())
    assert kind == "dub"
    assert ref.endswith(".wav")


def test_resolve_audio_ref_falls_back_to_picture_when_dub_missing() -> None:
    job = Job(
        station="loudness",
        project_id="batch",
        input_refs=["gs://b/e3/ep-01.mp4"],
        result={"dub_job_id": "cyc-demo-ep-01-es-ES-dub"},
    )

    class _Store:
        def get_doc(self, collection: str, doc_id: str) -> dict[str, Any] | None:
            return None

    ref, kind = resolve_audio_ref(job, _Store())
    assert kind == "picture"
    assert ref == "gs://b/e3/ep-01.mp4"


def test_orchestrator_stamps_dub_job_id_on_loudness() -> None:
    items = [
        {
            "batch_id": "demo",
            "episode_id": "ep-01",
            "source_ref": "gs://b/e3/ep-01.mp4",
            "shot_id": "shot-ep-01",
            "language": "es-ES",
            "script": "Hola.",
            "project_id": "batch",
        }
    ]
    jobs = build_batch_jobs(items)
    loud = next(j for j in jobs if j.station == "loudness")
    dub_id = batch_job_id("demo", "ep-01", "es-ES", "dub")
    assert loud.result["dub_job_id"] == dub_id
    # Picture URI stays on input_refs (ingest/delivery still need it);
    # the station resolves the dub at run time.
    assert loud.input_refs == ["gs://b/e3/ep-01.mp4"]


def test_strategy_prompt_names_loud_and_quiet_scenes() -> None:
    from backend.supervisor.station_agents.loudness_strategy import build_prompt

    report = {
        "job_id": "j1",
        "episode_id": "ep-01",
        "lufs_integrated": -25.3,
        "true_peak_dbtp": -3.0,
        "verdict_streaming": "fail_quiet",
        "verdict_broadcast": "fail_quiet",
        "stem_diagnosis": "balanced",
        "dialogue_band_lufs": -26.0,
        "music_band_lufs": -26.5,
    }
    prompt = build_prompt(report, [{"episode_id": "ep-00", "lufs": -16.1}])
    for word in ("whisper", "explosion", "impact", "shout", "dialogue", "silence"):
        assert word in prompt.lower()
    assert "scene_class" in prompt
    assert "listen" in prompt.lower()


def test_decide_forwards_audio_when_the_station_has_a_wav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.supervisor.station_agents.loudness_strategy import (
        decide_loudness_strategy,
    )

    calls: list[dict[str, Any]] = []

    def fake_call(_settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        return {
            "text": json.dumps(
                {
                    "agent": "loudness_strategy",
                    "decision": "apply_limiter",
                    "streaming_route": "block",
                    "broadcast_route": "block",
                    "scene_class": "explosion",
                    "target_lufs": -9.0,
                    "reason": "a sudden bang; mix louder than talk, do not squash it",
                    "confidence": "high",
                }
            ),
            "model": "gemini-3.7-flash",
            "cost_micros": 1800,
        }

    monkeypatch.setattr("backend.supervisor.otel_ai.run_agent_call", fake_call)
    wav = b"RIFF" + b"\x00" * 12
    decision, cost = decide_loudness_strategy(
        object(),
        report={
            "job_id": "j1",
            "episode_id": "ep-01",
            "lufs_integrated": -16.0,
            "true_peak_dbtp": -2.0,
            "verdict_streaming": "pass",
            "verdict_broadcast": "fail_hot",
            "stem_diagnosis": "balanced",
            "dialogue_band_lufs": -16.5,
            "music_band_lufs": -16.8,
        },
        season_state=[],
        audio=(wav, "audio/wav"),
    )
    assert cost == 1800
    assert calls[0]["audio"] == (wav, "audio/wav")
    assert decision.decision == "apply_limiter"
    assert decision.raw["scene_class"] == "explosion"


class _MemGCS:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.uploads: list[tuple[str, bytes]] = []

    def download_bytes(self, key: str) -> bytes:
        return self.blobs[key]

    def upload_bytes(self, key: str, data: bytes, *, content_type: str = "") -> None:
        self.blobs[key] = data
        self.uploads.append((key, data))


class _MemStore:
    def __init__(self, docs: dict[tuple[str, str], dict[str, Any]]) -> None:
        self.docs = docs
        self.writes: list[tuple[str, str, dict[str, Any]]] = []

    def get_doc(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        return self.docs.get((collection, doc_id))

    def set_doc(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        self.docs[(collection, doc_id)] = data
        self.writes.append((collection, doc_id, data))


def test_station_mixes_a_quiet_dub_instead_of_flagging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The product: too-quiet dub → listen → mix → re-measure. Not needs_human."""
    media = _media()
    quiet = tmp_path / "dub.wav"
    _sine_wav(media, quiet, seconds=3.0, volume_db=-40.0)
    wav = quiet.read_bytes()
    gcs = _MemGCS({"gs://b/dubs/ep-01.es-ES.wav": wav})
    store = _MemStore(
        {
            ("pc-jobs", "cyc-demo-ep-01-es-ES-dub"): {
                "status": "passed",
                "result": {"artifact_ref": "gs://b/dubs/ep-01.es-ES.wav"},
            }
        }
    )

    def fake_decide(_settings: Any, **_kwargs: Any) -> tuple[Any, int]:
        from backend.supervisor.station_agents.base import StationDecision

        return (
            StationDecision(
                agent="loudness_strategy",
                decision="apply_limiter",
                reason="quiet dialogue; mix up to talk level",
                confidence="high",
                deterministic_advice="apply_limiter",
                overridden=False,
                raw={"scene_class": "dialogue", "target_lufs": -16.0},
            ),
            1200,
        )

    monkeypatch.setattr(
        "backend.supervisor.station_agents.loudness_strategy.decide_loudness_strategy",
        fake_decide,
    )
    job = Job(
        station="loudness",
        project_id="batch",
        input_refs=["gs://b/e3/ep-01.mp4"],
        id="cyc-demo-ep-01-es-ES-loudness",
        result={
            "batch_id": "demo",
            "episode_id": "ep-01",
            "language": "es-ES",
            "shot_id": "shot-ep-01",
            "dub_job_id": "cyc-demo-ep-01-es-ES-dub",
        },
    )
    settings = get_settings()
    out = run_loudness(job, gcs, media, store=store, settings=settings)
    assert out.status != "needs_human"
    assert out.result["scene_class"] == "dialogue"
    assert abs(float(out.result["lufs"]) - (-16.0)) <= 1.5
    assert out.result.get("artifact_ref")
    assert gcs.uploads, "mixed audio must be written, not only measured"
    assert out.cost_micros == 1200
