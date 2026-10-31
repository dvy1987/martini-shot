"""TDD: per-render vision QC producer (2026-10-03).

The product never produced eval_scores.vision_judge, so `vision is None`
passed the draft bars forever. Every render now gets one billed judge
look (one retry on transient failure); an unjudgeable render is
needs_human — never a fake score (C-1.1, C-3.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.stations import vision_qc


def _write_fake_frames(work: Path, count: int) -> list[Path]:
    """Real tiny JPEG-ish files — the judge flow reads frame bytes."""
    paths = []
    for i in range(1, count + 1):
        p = work / f"f_{i:03d}.jpg"
        p.write_bytes(b"\xff\xd8fake")
        paths.append(p)
    return paths


def test_decision_table() -> None:
    assert vision_qc.vision_qc_decision(None) == "needs_human"
    assert vision_qc.vision_qc_decision(3.9) == "needs_human"
    assert vision_qc.vision_qc_decision(4.0) == "pass"
    assert vision_qc.vision_qc_decision(4.6) == "pass"


def test_qc_reason_names_what_tripped() -> None:
    """2026-10-03: job docs stored only the decision string — diagnosing a
    flag meant reading station code. The reason rides on the result."""
    gates = {"flicker_gate": 0.02, "spike_gate": 0.02, "vision_gate": 4.0}

    # Spike breach names the spike, with the numbers.
    reason = vision_qc.qc_reason(0.0105, 0.0532, None, **gates)
    assert "spike" in reason and "0.0532" in reason and "0.02" in reason

    # Vision breach names the score.
    reason = vision_qc.qc_reason(0.0105, 0.01, 3.1, **gates)
    assert "vision" in reason and "3.1" in reason

    # Unmeasured vision says so plainly.
    reason = vision_qc.qc_reason(0.0105, 0.01, None, **gates)
    assert "unmeasured" in reason

    # Pass names all three clears.
    reason = vision_qc.qc_reason(0.0031, 0.008, 4.6, **gates)
    assert "flicker" in reason and "spike" in reason and "vision" in reason


def test_judge_returns_score_and_cost(monkeypatch) -> None:
    calls: list[str] = []

    def fake_judge(settings: Any, gcs: Any, artifact_ref: str) -> dict[str, Any]:
        calls.append(artifact_ref)
        return {
            "vision_judge": 4.6,
            "artifact_rate": 0.0,
            "reason": "clean",
            "frames": 6,
            "cost_micros": 9500,
        }

    monkeypatch.setattr(vision_qc, "judge_render_artifact", fake_judge)
    out = vision_qc.judge_render(
        settings=None,
        gcs=None,
        artifact_ref="gs://b/x.mp4",
        job_id="j1",
        station="relight",
        project_id="p1",
    )
    assert out is not None
    assert out["vision_judge"] == 4.6
    assert out["artifact_rate"] == 0.0
    assert out["judge_cost_micros"] == 9500
    assert calls == ["gs://b/x.mp4"]


def test_transient_failure_retries_once(monkeypatch) -> None:
    calls: list[int] = []

    def flaky(settings: Any, gcs: Any, artifact_ref: str) -> dict[str, Any]:
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("vertex 504")
        return {
            "vision_judge": 4.2,
            "artifact_rate": 0.05,
            "reason": "ok",
            "frames": 6,
            "cost_micros": 9500,
        }

    monkeypatch.setattr(vision_qc, "judge_render_artifact", flaky)
    monkeypatch.setattr(vision_qc.time, "sleep", lambda _s: None)
    out = vision_qc.judge_render(
        settings=None,
        gcs=None,
        artifact_ref="gs://b/x.mp4",
        job_id="j1",
        station="relight",
        project_id="p1",
    )
    assert out is not None and out["vision_judge"] == 4.2
    assert len(calls) == 2


def test_spike_verdict_cut_does_not_breach(monkeypatch) -> None:
    """2026-10-03 smoke finding: a hard scene cut spikes the single-frame
    metric (transition-blend frame), and 3/3 real renders tripped the
    0.02 spike gate on LEGITIMATE cuts. The spike escalates to ONE
    targeted judge look at the spike frame; 'cut' is not a breach."""
    from backend.stations.draft_first import FLICKER_BAR

    assert FLICKER_BAR == 0.02  # the gate this composition sits beside
    assert (
        vision_qc.draft_spike_decision(spike=0.0326, spike_gate=0.02, spike_kind="cut")
        == "ok"
    )
    assert (
        vision_qc.draft_spike_decision(
            spike=0.0326, spike_gate=0.02, spike_kind="corruption"
        )
        == "needs_human"
    )
    # A failed/absent verdict is worst-case (C-3.5) — never a pass.
    assert (
        vision_qc.draft_spike_decision(spike=0.0326, spike_gate=0.02, spike_kind=None)
        == "needs_human"
    )
    assert (
        vision_qc.draft_spike_decision(spike=0.01, spike_gate=0.02, spike_kind=None)
        == "ok"
    )


def test_judge_spike_frame_calls_with_three_frames(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_call(settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        captured["images"] = kwargs.get("images")
        captured["prompt"] = prompt
        return {
            "text": json.dumps(
                {"spike_kind": "cut", "note": "clean scene cut to a butterfly"}
            ),
            "cost_micros": 5654,
        }

    monkeypatch.setattr(vision_qc, "run_agent_call", fake_call)
    monkeypatch.setattr(vision_qc, "_ffmpeg_bin", lambda _settings: "ffmpeg")
    monkeypatch.setattr(
        vision_qc,
        "extract_frames_at",
        lambda clip, ffmpeg_bin, work, count: _write_fake_frames(work, count),
    )

    def fake_download(settings: Any, gcs: Any, artifact_ref: str, work: Path) -> Path:
        return work / "clip.mp4"

    monkeypatch.setattr(vision_qc, "download_artifact", fake_download)
    out = vision_qc.judge_spike_frame(
        settings=None,
        gcs=None,
        artifact_ref="gs://b/x.mp4",
        spike_frame_index=48,
        job_id="j1",
        station="extend",
        project_id="p1",
        work_dir=Path("scratch"),  # ignored by the patched extract
    )
    assert out is not None
    assert out["spike_kind"] == "cut"
    assert out["judge_cost_micros"] == 5654
    assert len(captured["images"]) == 3  # spike frame ± 1


def test_non_transient_failure_is_needs_human_none(monkeypatch) -> None:
    """A failed look is not a judgment: worst-case None, never a score."""

    def broken(settings: Any, gcs: Any, artifact_ref: str) -> dict[str, Any]:
        raise ValueError("judge payload not JSON: garbage")

    calls: list[int] = []
    monkeypatch.setattr(vision_qc, "judge_render_artifact", broken)
    monkeypatch.setattr(
        vision_qc.time, "sleep", lambda _s: calls.append(-1)
    )  # must NOT be reached for non-transient
    out = vision_qc.judge_render(
        settings=None,
        gcs=None,
        artifact_ref="gs://b/x.mp4",
        job_id="j1",
        station="relight",
        project_id="p1",
    )
    assert out is None
    assert calls == []  # no cooldown sleep for a non-transient failure
