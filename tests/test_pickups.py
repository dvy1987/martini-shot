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
