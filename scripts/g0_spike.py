#!/usr/bin/env python
"""G0 quality spike (plan Phase 0): real Omni video ops on the spike shots.

Two operations against gemini-omni-1.1-flash-preview on Vertex (360p draft
tier, Spend-Aware):
  1. bg_swap      — task=edit on shot-01-meadow (background replacement).
  2. scene_extend — task=extend on shot-03-clearing (natural continuation).

Outputs go to docs/evidence/G0/outputs/ (committed evidence, never shipped
as product). A deterministic flicker score (temporal-median residual on
grayscale, motion-invariant) is computed for each input and output pair.
Evidence: docs/evidence/G0/spike_ops.jsonl (C-3.4 JSONL).

Usage: .venv/Scripts/python.exe scripts/g0_spike.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "G0"
OUTPUT_DIR = EVIDENCE_DIR / "outputs"
VIDEO_MODEL = "gemini-omni-1.1-flash"
RESOLUTION = "360p"
DURATION = "8s"

OPS = [
    {
        "op_id": "G0-bg-swap-01",
        "task": "edit",
        "shot": "shot-01-meadow.mp4",
        "prompt": (
            "Replace the background environment with a rainy neon-lit city "
            "street at night. Keep the subject, its motion, and the camera "
            "movement exactly the same. Keep everything else the same."
        ),
    },
    {
        "op_id": "G0-scene-extend-01",
        "task": "extend",
        "shot": "shot-03-clearing.mp4",
        "prompt": (
            "Extend the scene: continue the action and environment exactly "
            "as established, as if the shot simply keeps rolling. "
            "Keep everything else the same."
        ),
    },
]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def extract_video_bytes(interaction: object) -> tuple[bytes | None, str | None]:
    output_video = getattr(interaction, "output_video", None)
    if output_video is None:
        return None, "no output_video on interaction"
    data = getattr(output_video, "data", None)
    uri = getattr(output_video, "uri", None)
    if isinstance(data, (bytes, bytearray)):
        return bytes(data), None
    if isinstance(data, str) and data:
        try:
            return base64.b64decode(data), None
        except Exception:  # noqa: BLE001 - raw-bytes fallback, never raises past this
            return data.encode("utf-8"), None
    if uri:
        return None, uri
    return None, "output_video has neither data nor uri"


def download_uri(uri: str, token: str) -> bytes:
    request = urllib.request.Request(uri, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except Exception:  # noqa: BLE001 - signed URLs reject auth headers
        with urllib.request.urlopen(uri, timeout=120) as response:  # signed URL path
            return response.read()


def flicker_score(path: Path) -> dict[str, object]:
    """Motion-invariant flicker: mean temporal-median residual (grayscale).

    For each interior frame t, residual = |I_t - median(I_{t-1}, I_t, I_{t+1})|.
    True flicker (frame-to-frame shimmer) breaks the temporal median; smooth
    camera/subject motion does not. Lower is better. Analysis at half width.
    """
    capture = cv2.VideoCapture(str(path))
    frames: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        small = cv2.resize(gray, (gray.shape[1] // 2, gray.shape[0] // 2))
        frames.append(small)
    capture.release()
    if len(frames) < 3:
        return {"ok": False, "error": f"only {len(frames)} frames decodable"}
    stack = np.stack(frames)
    median = np.median(np.stack([stack[:-2], stack[1:-1], stack[2:]]), axis=0)
    residual = np.abs(stack[1:-1] - median)
    return {
        "ok": True,
        "flicker_score": round(float(residual.mean()), 5),
        "p99_residual": round(float(np.percentile(residual, 99)), 5),
        "frames_analyzed": len(frames),
        "definition": "mean |I_t - median3| grayscale [0,1], half-res, lower=better",
    }


def usage_record(interaction: object) -> dict[str, object]:
    usage = getattr(interaction, "usage", None)
    if usage is None:
        return {}
    try:
        return {"total_token_count": getattr(usage, "total_token_count", None)}
    except Exception:  # noqa: BLE001 - usage object shape varies across versions
        return {}


def run_op(client: object, spec: dict[str, str], token: str) -> dict[str, object]:
    shot_path = ROOT / "fixtures" / "spike" / spec["shot"]
    print(f"[{spec['op_id']}] task={spec['task']} shot={spec['shot']} ...", flush=True)
    started = datetime.now(tz=timezone.utc)

    # Official docs path: upload via Files API, reference by URI.
    print("  uploading via Files API...", flush=True)
    video_file = client.files.upload(file=str(shot_path))
    video_file = client.files.get(name=video_file.name)
    wait_seconds = 0
    while getattr(video_file, "state", "") == "PROCESSING" and wait_seconds < 300:
        time.sleep(10)
        wait_seconds += 10
        video_file = client.files.get(name=video_file.name)
    if getattr(video_file, "state", "") == "FAILED":
        return {
            "op_id": spec["op_id"],
            "status": "upload_failed",
            "error": "Files API state FAILED",
        }
    file_uri = getattr(video_file, "uri", None)
    if not file_uri:
        return {
            "op_id": spec["op_id"],
            "status": "upload_failed",
            "error": "no URI returned",
        }

    record: dict[str, object] = {
        "op_id": spec["op_id"],
        "task": spec["task"],
        "model": VIDEO_MODEL,
        "resolution": RESOLUTION,
        "requested_duration": DURATION,
        "input_shot": spec["shot"],
        "input_file_uri": str(file_uri)[:160],
        "prompt": spec["prompt"],
        "started_utc": started.isoformat(),
    }
    try:
        for attempt in range(10):
            try:
                # Gemini API runtime (official docs): Interactions API with
                # Files-API URI reference; bare conversational payload.
                interaction = client.interactions.create(
                    model=VIDEO_MODEL,
                    input=[
                        {"type": "text", "text": spec["prompt"]},
                        {"type": "video", "uri": file_uri, "mime_type": "video/mp4"},
                    ],
                    response_modalities=["video"],
                    timeout=900,
                )
                break
            except Exception as exc:
                is_429 = "429" in str(exc)[:120]
                if is_429 and attempt < 9:
                    print(
                        f"  429 rate limit, waiting 90s (attempt {attempt + 1}/9)...",
                        flush=True,
                    )
                    time.sleep(90)
                    continue
                raise
    except Exception as exc:  # noqa: BLE001 - spike records failures verbatim
        record["status"] = "api_error"
        record["error"] = str(exc)[:500]
        return record

    status = getattr(interaction, "status", "unknown")
    record["status"] = status
    record["interaction_id"] = getattr(interaction, "id", None)
    record["usage"] = usage_record(interaction)

    if status != "completed":
        errors = getattr(interaction, "errors", None)
        record["error"] = str(errors)[:500] if errors else "status != completed"
        return record

    video_bytes, uri = extract_video_bytes(interaction)
    if video_bytes is None and uri:
        try:
            video_bytes = download_uri(uri, token)
        except Exception as exc:  # noqa: BLE001
            record["error"] = f"download failed: {str(exc)[:300]}"
            return record
    if video_bytes is None:
        return record

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{spec['op_id']}.mp4"
    out_path.write_bytes(video_bytes)
    record["output_file"] = str(out_path.relative_to(ROOT))
    record["output_bytes"] = len(video_bytes)

    input_score = flicker_score(shot_path)
    output_score = flicker_score(out_path)
    record["flicker_input"] = input_score
    record["flicker_output"] = output_score
    record["finished_utc"] = datetime.now(tz=timezone.utc).isoformat()
    return record


def main() -> int:
    env = load_env(ROOT / ".env")
    env.update(os.environ)
    project = env.get("GOOGLE_CLOUD_PROJECT", "")
    location = env.get("GOOGLE_CLOUD_LOCATION", "global")
    api_key = env.get("GEMINI_API_KEY", "")
    if not project and not api_key:
        print("GOOGLE_CLOUD_PROJECT or GEMINI_API_KEY required (.env)")
        return 1

    import shutil
    import subprocess

    from google import genai

    client = None
    gcloud = ""
    runtime = ""
    if api_key:
        # Documented Omni runtime: Gemini API with API key (ADR 0002).
        client = genai.Client(api_key=api_key)
        runtime = "gemini_api"
        print("runtime: Gemini API (API key)", flush=True)
    else:
        client = genai.Client(enterprise=True, project=project, location=location)
        runtime = "vertex"
        print("runtime: Vertex AI enterprise", flush=True)
        gcloud_exe = shutil.which("gcloud") or shutil.which("gcloud.cmd")
        if gcloud_exe is None:
            print("gcloud executable not found on PATH")
            return 1
        gcloud = subprocess.run(
            [gcloud_exe, "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    evidence_path = EVIDENCE_DIR / "spike_ops.jsonl"
    all_ok = True
    with evidence_path.open("a", encoding="utf-8") as evidence:
        for index, spec in enumerate(OPS):
            if index > 0:
                print("  spacing 90s between ops for per-minute quota...", flush=True)
                time.sleep(90)
            record = run_op(client, spec, gcloud)
            record["runtime"] = runtime
            record["recorded_utc"] = datetime.now(tz=timezone.utc).isoformat()
            evidence.write(json.dumps(record) + "\n")
            evidence.flush()
            print(json.dumps(record, indent=2), flush=True)
            if record.get("status") != "completed":
                all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
