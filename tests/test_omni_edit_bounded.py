"""omni_edit_bounded: Omni's edit task has a real, previously-undocumented
server-side duration cap (2026-09-09 demo failure: "Editing duration 14
exceeds maximum duration 10" broke Relight mid-demo). Owner directive:
chop clips over the cap into segments, call Omni on each SEQUENTIALLY
with a gap between calls, then reassemble the edited segments into one
clip. Real ffmpeg does the chunking/reassembly (deterministic, TDD); the
Omni call itself is injected (same pattern as render_pickup_repair) so
these tests run with no network access and no billing.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from backend.core.config import Settings, get_settings
from backend.core.generative import omni_edit_bounded
from backend.core.media import FFmpeg

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "spike"


class _MemGCS:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.uploads: list[str] = []

    def download_bytes(self, key: str) -> bytes:
        return self.blobs[key]

    def upload_bytes(self, key: str, data: bytes, *, content_type: str = "") -> None:
        del content_type
        self.blobs[key] = data
        self.uploads.append(key)


@pytest.fixture()
def media() -> FFmpeg:
    settings = get_settings()
    return FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)


@pytest.fixture()
def settings() -> Settings:
    real = get_settings()
    return Settings(
        gcp_project_id=real.gcp_project_id,
        gcs_bucket="b",
        ffmpeg_bin=real.ffmpeg_bin,
        ffprobe_bin=real.ffprobe_bin,
    )


def test_short_clip_skips_chunking_entirely(media: FFmpeg, settings: Settings) -> None:
    src = FIXTURES / "shot-01-meadow.mp4"
    gcs = _MemGCS({"gs://b/src.mp4": src.read_bytes()})
    calls: list[dict[str, Any]] = []

    def fake_omni_edit(_settings: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"video_bytes": b"one-shot", "model": "omni", "interaction_id": "i1"}

    out = omni_edit_bounded(
        settings,
        gcs,
        media,
        input_uri="gs://b/src.mp4",
        prompt="relight warm",
        scratch_prefix="projects/p/_omni_scratch/job-1",
        max_duration_s=30.0,
        omni_edit=fake_omni_edit,
    )
    assert len(calls) == 1
    assert calls[0]["input_uri"] == "gs://b/src.mp4"  # untouched, no scratch upload
    assert out["video_bytes"] == b"one-shot"
    assert not gcs.uploads


def test_long_clip_is_chunked_sequentially_with_a_gap(
    media: FFmpeg, settings: Settings, tmp_path: Path
) -> None:
    src = FIXTURES / "shot-02-grove.mp4"  # real fixture (C-1.3), ~10s
    total = media.probe(src)["duration_s"]
    expected_chunks = math.ceil(total / 5.0)
    gcs = _MemGCS({"gs://b/src.mp4": src.read_bytes()})

    # Fake Omni "renders" by handing back a fixed short clip regardless of
    # segment content — proves the orchestration/reassembly, not the model.
    stub_clip = tmp_path / "stub.mp4"
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
            "testsrc=duration=2:size=64x64:rate=8",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            str(stub_clip),
        ],
        timeout=30,
    )
    assert result.returncode == 0
    stub_bytes = stub_clip.read_bytes()

    calls: list[dict[str, Any]] = []
    sleeps: list[float] = []

    def fake_omni_edit(_settings: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "video_bytes": stub_bytes,
            "model": "omni",
            "interaction_id": f"i{len(calls)}",
            "total_token_count": 10,
        }

    import backend.core.generative as generative_mod

    monkeypatch_sleep = generative_mod.time.sleep

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    generative_mod.time.sleep = fake_sleep  # type: ignore[assignment]
    try:
        out = omni_edit_bounded(
            settings,
            gcs,
            media,
            input_uri="gs://b/src.mp4",
            prompt="relight warm",
            scratch_prefix="projects/p/_omni_scratch/job-2",
            max_duration_s=5.0,
            gap_s=2.0,
            omni_edit=fake_omni_edit,
        )
    finally:
        generative_mod.time.sleep = monkeypatch_sleep  # type: ignore[assignment]

    assert expected_chunks >= 2, "fixture too short to exercise chunking"
    assert len(calls) == expected_chunks
    assert out["chunked"] is True
    assert out["chunk_count"] == expected_chunks
    # Sequential with a gap: (n-1) sleeps, each the configured gap.
    assert sleeps == [2.0] * (expected_chunks - 1)
    # Each chunk went to its own scratch object, uploaded before the call.
    assert len(gcs.uploads) == expected_chunks
    assert len({c["input_uri"] for c in calls}) == expected_chunks
    for c in calls:
        assert c["input_uri"].startswith("gs://b/projects/p/_omni_scratch/job-2/")
    assert out["interaction_id"] == ",".join(
        f"i{n}" for n in range(1, expected_chunks + 1)
    )
    assert out["total_token_count"] == 10 * expected_chunks
    # Reassembled output covers ~ the stub length x chunk count (2s each).
    reassembled = tmp_path / "out.mp4"
    reassembled.write_bytes(out["video_bytes"])
    rebuilt = media.probe(reassembled)
    assert abs(rebuilt["duration_s"] - 2.0 * expected_chunks) <= 0.5
