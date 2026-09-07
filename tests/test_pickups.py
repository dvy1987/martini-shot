"""D-5/D-6 pickups QC: real G0 scores, identity round-trip, cost estimator."""

import json
from pathlib import Path

from backend.core.config import get_settings
from backend.core.media import FFmpeg
from backend.stations.pickups.anchors import build_anchor_prompt, prev_frame_note
from backend.stations.pickups.cost import estimate_micros, within_tolerance
from backend.stations.pickups.flicker import flicker_score
from backend.stations.pickups.retry import apply_retries, next_action

G0 = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "G0"
    / "flicker_scores.json"
)
SLATE = Path(__file__).resolve().parents[1] / "fixtures" / "g1" / "slate.mp4"


def _g0_output_score(op: str) -> float:
    payload = json.loads(G0.read_text(encoding="utf-8"))
    return float(payload[op]["output"]["flicker_score"])


def test_real_g0_bg_swap_passes_spec_bar() -> None:
    score = _g0_output_score("bg-swap")
    assert next_action(score, 0.18, 0) == "pass"


def test_real_g0_score_against_tight_bar_retries_then_needs_human() -> None:
    """Uses the real G0 bg-swap output score; only the bar is tightened for the machine."""
    score = _g0_output_score("bg-swap")
    result = apply_retries(score, threshold=0.005, max_retries=2)
    assert result["final"] == "needs_human"
    assert result["retries_used"] == 2
    assert result["steps"] == [
        "retry_strengthen",
        "retry_strengthen",
        "needs_human",
    ]


def test_anchor_prompt_strengthens() -> None:
    weak = build_anchor_prompt("background_swap", "flat sky", strengthen=False)
    strong = build_anchor_prompt("background_swap", "flat sky", strengthen=True)
    assert "Keep everything else the same" in weak
    assert "identity lock" in strong
    assert strong.startswith(weak) or "flat sky" in strong


def test_cost_estimator_matches_actual_within_20_percent() -> None:
    estimate = estimate_micros(24, 1000)
    assert estimate == 24_000
    assert within_tolerance(estimate, 24_000)
    assert within_tolerance(20_000, 24_000)
    assert not within_tolerance(1, 24_000)
    assert within_tolerance(0, 0)


def test_extract_reassemble_duration_within_one_frame(tmp_path: Path) -> None:
    settings = get_settings()
    media = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
    fps = 8.0
    frames = media.extract_frames(SLATE, tmp_path / "frames", fps=fps)
    out = tmp_path / "roundtrip.mp4"
    media.reassemble(frames, out, fps=fps)
    orig = media.probe(SLATE)
    rebuilt = media.probe(out)
    assert (
        abs(float(orig["duration_s"]) - float(rebuilt["duration_s"]))
        <= (1 / fps) + 0.05
    )


def test_flicker_score_on_slate() -> None:
    settings = get_settings()
    score = flicker_score(SLATE, settings.ffmpeg_bin)
    assert score["ok"] is True
    assert float(score["flicker_score"]) < 0.18


def test_prev_frame_note() -> None:
    assert "no previous" in prev_frame_note(0)
    assert "00000" in prev_frame_note(1)


def test_negative_frame_count_estimates_zero() -> None:
    assert estimate_micros(-1, 10) == 0


class _MemoryGCS:
    """Test double for the GCS download/upload surface (tests/ only)."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.uploads: list[tuple[str, bytes, str]] = []

    def download_bytes(self, key: str) -> bytes:
        del key
        return self.payload

    def upload_bytes(self, key: str, data: bytes, *, content_type: str = "") -> None:
        self.uploads.append((key, data, content_type))


def _decision(name: str) -> object:
    from backend.supervisor.station_agents.base import StationDecision

    return StationDecision(
        agent="pickups_vision_qc",
        decision=name,
        reason=f"test {name}",
        confidence="high",
        deterministic_advice=name,
        overridden=False,
    )


def test_live_pickups_asks_vision_qc_and_skips_repair_when_clean() -> None:
    """Contract: the worker must SEE frames via Pickups Vision QC. A clean
    clip must pass without billing a generative repair."""
    from backend.jobs.models import Job
    from backend.stations.pickups.run import run_pickups

    media = FFmpeg(get_settings().ffmpeg_bin, get_settings().ffprobe_bin)
    judged: list[object] = []

    def judge(_settings: object, *, report: dict, images: list) -> tuple[object, int]:
        judged.append({"report": report, "n_images": len(images)})
        assert images, "vision QC must receive real frame extracts"
        assert all(blob and mime for blob, mime in images)
        return _decision("accept"), 900

    repairs: list[object] = []

    def repair(_settings: object, **kwargs: object) -> dict:
        repairs.append(kwargs)
        raise AssertionError("clean clip must not generate")

    job = Job(station="pickups", project_id="p-qc", input_refs=["slate.mp4"])
    done = run_pickups(
        job,
        _MemoryGCS(SLATE.read_bytes()),
        media,
        judge=judge,
        repair=repair,
    )
    assert len(judged) == 1
    assert judged[0]["n_images"] >= 1
    assert repairs == []
    assert done.result["agent"]["decision"] == "accept"
    assert done.result["repaired"] is False
    assert done.status != "needs_human"


def test_live_pickups_repairs_on_retry_then_passes() -> None:
    """Contract: retry_with_stronger_anchors must call Omni/Veo repair, not
    re-score the same identity round-trip."""
    from backend.jobs.models import Job
    from backend.stations.pickups.run import run_pickups

    media = FFmpeg(get_settings().ffmpeg_bin, get_settings().ffprobe_bin)
    slate = SLATE.read_bytes()
    calls = {"judge": 0, "repair": 0}

    def judge(_settings: object, *, report: dict, images: list) -> tuple[object, int]:
        del report, images
        calls["judge"] += 1
        if calls["judge"] == 1:
            return _decision("retry_with_stronger_anchors"), 1100
        return _decision("accept"), 1100

    def repair(_settings: object, **kwargs: object) -> dict:
        calls["repair"] += 1
        prompt = str(kwargs.get("prompt") or "")
        assert "identity lock" in prompt
        return {
            "video_bytes": slate,
            "model": "gemini-omni-1.1-flash-preview",
            "omni_fallback": False,
            "omni_error": "",
        }

    job = Job(
        station="pickups",
        project_id="p-fix",
        input_refs=["slate.mp4"],
        result={"op": "background_swap", "hint": "rainy neon street"},
    )
    gcs = _MemoryGCS(slate)
    done = run_pickups(job, gcs, media, judge=judge, repair=repair)
    assert calls["repair"] == 1
    assert calls["judge"] == 2
    assert done.result["repaired"] is True
    assert done.result["agent"]["decision"] == "accept"
    assert gcs.uploads, "repaired clip must be stored"
    assert done.status != "needs_human"


def test_live_pickups_two_repairs_then_needs_human() -> None:
    from backend.jobs.models import Job
    from backend.stations.pickups.run import run_pickups

    media = FFmpeg(get_settings().ffmpeg_bin, get_settings().ffprobe_bin)
    slate = SLATE.read_bytes()

    def judge(_settings: object, *, report: dict, images: list) -> tuple[object, int]:
        del report, images
        return _decision("retry_with_stronger_anchors"), 800

    repairs = {"n": 0}

    def repair(_settings: object, **kwargs: object) -> dict:
        del kwargs
        repairs["n"] += 1
        return {
            "video_bytes": slate,
            "model": "veo-3.1-fast-generate-001",
            "omni_fallback": True,
            "omni_error": "recitation",
        }

    job = Job(station="pickups", project_id="p-nh", input_refs=["k"])
    done = run_pickups(job, _MemoryGCS(slate), media, judge=judge, repair=repair)
    assert repairs["n"] == 2
    assert done.status == "needs_human"
    assert done.result["repaired"] is True


def test_pickup_repair_uses_veo_when_omni_fails() -> None:
    from backend.stations.pickups.repair import render_pickup_repair

    def boom(_settings: object, **kwargs: object) -> dict:
        del kwargs
        raise RuntimeError("omni recitation")

    def veo(_settings: object, **kwargs: object) -> dict:
        del kwargs
        return {"video_bytes": b"veo-clip", "model": "veo-3.1-fast-generate-001"}

    out = render_pickup_repair(
        object(),
        input_uri="gs://b/src.mp4",
        prompt="fix frames",
        omni_edit=boom,
        veo_extend=veo,
    )
    assert out["omni_fallback"] is True
    assert "recitation" in out["omni_error"]
    assert out["video_bytes"] == b"veo-clip"
