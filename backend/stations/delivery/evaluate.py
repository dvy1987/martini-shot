"""Delivery pack evaluator (S5 / D-4): YAML profiles + loudness + captions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.stations.delivery.captions import Violation, check_captions
from backend.stations.loudness.verdict import verdict as loudness_verdict

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
DEST_UNKNOWN = "DEST-UNKNOWN"
RULE_CONTAINER = "DEL-001"
RULE_CODEC = "DEL-002"
RULE_AR = "DEL-003"
RULE_FPS = "DEL-004"
RULE_BITRATE = "DEL-005"
RULE_LOUDNESS = "DEL-006"
RULE_CAPTIONS = "DEL-007"


def load_profile(destination: str) -> dict[str, Any]:
    path = PROFILES_DIR / f"{destination}.yaml"
    if not path.is_file():
        raise KeyError(DEST_UNKNOWN)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise KeyError(DEST_UNKNOWN)
    return data


def _aspect(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "0:0"
    a, b = width, height
    while b:
        a, b = b, a % b
    return f"{width // a}:{height // a}"


def evaluate_delivery(
    *,
    destination: str,
    probe: dict[str, Any],
    lufs: float | None,
    caption_text: str | None,
    caption_name: str | None,
) -> dict[str, Any]:
    try:
        profile = load_profile(destination)
    except KeyError:
        return {
            "destination": destination,
            "verdict": "fail",
            "violations": [
                {
                    "rule_id": DEST_UNKNOWN,
                    "message": f"unknown destination {destination}",
                }
            ],
        }
    violations: list[dict[str, str | int | None]] = []
    fmt = str(probe.get("format") or "")
    if profile.get("container") and profile["container"] not in fmt:
        violations.append(
            {
                "rule_id": RULE_CONTAINER,
                "message": f"container {fmt!r} vs {profile['container']}",
            }
        )
    codec = str(probe.get("codec") or "")
    if profile.get("codec") and codec not in {profile["codec"], "avc1"}:
        violations.append(
            {"rule_id": RULE_CODEC, "message": f"codec {codec!r} vs {profile['codec']}"}
        )
    ar = _aspect(int(probe.get("width") or 0), int(probe.get("height") or 0))
    if profile.get("ar") and ar != str(profile["ar"]):
        violations.append(
            {"rule_id": RULE_AR, "message": f"ar {ar} vs {profile['ar']}"}
        )
    fps = float(probe.get("fps") or 0.0)
    if fps < float(profile.get("fps_min") or 0) or fps > float(
        profile.get("fps_max") or 120
    ):
        violations.append(
            {"rule_id": RULE_FPS, "message": f"fps {fps} outside profile range"}
        )
    bitrate_kbps = int(probe.get("bit_rate") or 0) / 1000
    cap = float(profile.get("bitrate_max_kbps") or 0)
    if cap and bitrate_kbps > cap:
        violations.append(
            {
                "rule_id": RULE_BITRATE,
                "message": f"bitrate {bitrate_kbps:.0f} kbps > {cap}",
            }
        )
    target = float(profile.get("loudness_target_lufs") or -16)
    if lufs is not None:
        loud = loudness_verdict(lufs, target=target)
        if loud != "pass":
            violations.append(
                {"rule_id": RULE_LOUDNESS, "message": f"loudness {lufs} ({loud})"}
            )
    if profile.get("captions_required"):
        if not caption_text:
            violations.append(
                {"rule_id": RULE_CAPTIONS, "message": "captions required but missing"}
            )
        else:
            caps: list[Violation] = check_captions(
                caption_text, caption_name or "captions.srt"
            )
            for item in caps:
                violations.append(
                    {
                        "rule_id": item.rule_id,
                        "message": item.message,
                        "cue_index": item.cue_index,
                    }
                )
    return {
        "destination": destination,
        "verdict": "pass" if not violations else "fail",
        "violations": violations,
        "profile": profile,
    }
