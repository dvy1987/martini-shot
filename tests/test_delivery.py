"""D-4 delivery pack evaluator (AC-S5.1)."""

from backend.stations.delivery.evaluate import DEST_UNKNOWN, evaluate_delivery

HEALTHY_PROBE = {
    "format": "mov,mp4,m4a,3gp,3g2,mj2",
    "codec": "h264",
    "width": 1920,
    "height": 1080,
    "fps": 24.0,
    "bit_rate": 5_000_000,
}

VALID_CAPTION = """1
00:00:00,000 --> 00:00:02,000
Hello there
"""


def test_streaming_compliant_pack_passes() -> None:
    report = evaluate_delivery(
        destination="streaming",
        probe=HEALTHY_PROBE,
        lufs=-16.0,
        caption_text=VALID_CAPTION,
        caption_name="ok.srt",
    )
    assert report["verdict"] == "pass"
    assert report["violations"] == []


def test_streaming_hot_loudness_fails() -> None:
    report = evaluate_delivery(
        destination="streaming",
        probe=HEALTHY_PROBE,
        lufs=-10.0,
        caption_text=VALID_CAPTION,
        caption_name="ok.srt",
    )
    assert report["verdict"] == "fail"
    assert any(v["rule_id"] == "DEL-006" for v in report["violations"])


def test_caption_failure_blocks_shipment() -> None:
    report = evaluate_delivery(
        destination="streaming",
        probe=HEALTHY_PROBE,
        lufs=-16.0,
        caption_text="1\n00:00:00,000 --> 00:00:00,200\nHi\n",
        caption_name="bad.srt",
    )
    assert report["verdict"] == "fail"
    assert any(str(v["rule_id"]).startswith("CAP-") for v in report["violations"])


def test_unknown_destination_rejected() -> None:
    report = evaluate_delivery(
        destination="imax-secret",
        probe=HEALTHY_PROBE,
        lufs=-16.0,
        caption_text=None,
        caption_name=None,
    )
    assert report["verdict"] == "fail"
    assert report["violations"][0]["rule_id"] == DEST_UNKNOWN


def test_codec_fps_bitrate_and_zero_ar() -> None:
    report = evaluate_delivery(
        destination="streaming",
        probe={
            "format": "mov,mp4,m4a,3gp,3g2,mj2",
            "codec": "mpeg4",
            "width": 0,
            "height": 0,
            "fps": 12.0,
            "bit_rate": 80_000_000,
        },
        lufs=-16.0,
        caption_text=VALID_CAPTION,
        caption_name="ok.srt",
    )
    ids = {v["rule_id"] for v in report["violations"]}
    assert "DEL-002" in ids
    assert "DEL-003" in ids
    assert "DEL-004" in ids
    assert "DEL-005" in ids


def test_missing_required_captions() -> None:
    report = evaluate_delivery(
        destination="streaming",
        probe=HEALTHY_PROBE,
        lufs=-16.0,
        caption_text=None,
        caption_name=None,
    )
    assert any(v["rule_id"] == "DEL-007" for v in report["violations"])


def test_social_allows_missing_captions() -> None:
    report = evaluate_delivery(
        destination="social",
        probe={**HEALTHY_PROBE, "width": 1080, "height": 1920},
        lufs=-16.0,
        caption_text=None,
        caption_name=None,
    )
    assert report["verdict"] == "pass"


class _ProbeMedia:
    def probe(self, path):
        return {
            **HEALTHY_PROBE,
            "duration_s": 8.0,
            "has_audio": True,
            "audio_streams": 1,
        }

    def loudness_lufs(self, path) -> float:
        return -16.0


class _MemGCS:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.uploads: list[str] = []

    def download_bytes(self, key: str) -> bytes:
        return self.blobs[key]

    def upload_bytes(self, key: str, data: bytes, *, content_type: str = "") -> None:
        self.blobs[key] = data
        self.uploads.append(key)


class _MemStore:
    def __init__(self) -> None:
        self.docs: dict[tuple[str, str], dict] = {}

    def get_doc(self, collection: str, doc_id: str):
        return self.docs.get((collection, doc_id))

    def set_doc(self, collection: str, doc_id: str, data: dict) -> None:
        self.docs[(collection, doc_id)] = data


def test_delivery_writes_captions_when_missing() -> None:
    from backend.jobs.models import Job
    from backend.stations.delivery.run import run_delivery

    job = Job(
        station="delivery",
        project_id="batch",
        input_refs=["gs://b/e3/ep-01.mp4"],
        id="cyc-demo-ep-01-es-ES-delivery",
        result={
            "script": "Hola, este es un doblaje.",
            "shot_id": "shot-ep-01",
            "destination": "streaming",
        },
    )
    gcs = _MemGCS({"gs://b/e3/ep-01.mp4": b"not-a-real-mp4"})
    out = run_delivery(job, gcs, _MemStore(), _ProbeMedia(), settings=None)
    assert out.result["caption_source"] == "writer"
    assert out.result["caption_ref"]
    assert gcs.uploads
    ids = {v["rule_id"] for v in out.result["delivery"]["violations"]}
    assert "DEL-007" not in ids
    assert out.result["delivery"]["verdict"] == "pass"


def test_delivery_prefers_loudness_mix() -> None:
    from backend.jobs.models import Job
    from backend.stations.delivery.run import resolve_delivery_media

    job = Job(
        station="delivery",
        project_id="batch",
        input_refs=["gs://b/e3/ep-01.mp4"],
        result={"loudness_job_id": "cyc-demo-ep-01-es-ES-loudness"},
    )
    store = _MemStore()
    store.set_doc(
        "pc-jobs",
        "cyc-demo-ep-01-es-ES-loudness",
        {"result": {"artifact_ref": "gs://b/mixes/ep-01.wav"}},
    )
    ref, kind = resolve_delivery_media(job, store)
    assert kind == "loudness_mix"
    assert ref.endswith(".wav")
