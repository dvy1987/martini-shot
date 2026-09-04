#!/usr/bin/env python
"""Veo extend probe (D-9 fallback path, G0 probe methodology).

Omni video on Vertex began refusing with `recitation` on 2026-09-04 evening
(inputs+prompts that completed at 13:35 the same day). The Interactions API
does not serve the pinned Veo ID, so this probe tests Veo's OWN surface
(predictLongRunning) for video-input extension on each (model, location)
combo the G0 sweep proved callable. A validation 400/404 costs nothing and
fails fast; the first ACCEPTED combo renders a real extension.

Spend: <=1 render x <=8s x fast-tier price (~$0.40 worst case) — inside the
<=$5 eval envelope. Evidence: docs/evidence/D-9/veo_extend_probe.json.
Usage: .venv/Scripts/python.exe scripts/veo_extend_probe.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EVIDENCE = ROOT / "docs" / "evidence" / "D-9"
SOURCE = "gs://martini-shot-media/probes720/shot-03-clearing-720p.mp4"
PROMPT = (
    "Extend this video. The scene continues exactly as established, "
    "as if the shot simply keeps rolling. Keep everything else the same."
)
COMBOS = [
    ("veo-3.1-fast-generate-001", "global"),
    ("veo-3.1-generate-001", "global"),
    ("veo-3.1-fast-generate-001", "us-central1"),
    ("veo-3.1-generate-preview", "global"),
]


def token() -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud is None:
        raise RuntimeError("gcloud executable not found on PATH")
    return subprocess.run(
        [gcloud, "auth", "application-default", "print-access-token"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main() -> int:
    bearer = token()
    results: dict = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "purpose": "Veo extend fallback: does the pinned Veo model accept video input?",
        "source": SOURCE,
        "combos": [],
    }
    accepted = None
    for model, location in COMBOS:
        url = (
            f"https://aiplatform.googleapis.com/v1/projects/"
            f"{project_id()}/locations/{location}/publishers/google/"
            f"models/{model}:predictLongRunning"
        )
        body = {
            "instances": [
                {
                    "prompt": PROMPT,
                    "video": {"gcsUri": SOURCE, "mimeType": "video/mp4"},
                }
            ],
            "parameters": {
                "sampleCount": 1,
                # video_extension on veo-3.1-fast-generate-001 supports
                # exactly 7s (operation error: "supported durations are [7]").
                "durationSeconds": 7,
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        entry: dict = {"model": model, "location": location}
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            entry["status"] = "accepted"
            entry["operation"] = str(payload.get("name", ""))[:160]
            accepted = (model, location, str(payload.get("name", "")), bearer)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            entry["status"] = "rejected"
            entry["http"] = exc.code
            entry["error"] = detail
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)[:300]
        results["combos"].append(entry)
        print(json.dumps(entry), flush=True)
        if accepted:
            break

    if accepted:
        model, location, op_name, bearer_token = accepted
        print(f"POLLING {model} @ {location}...", flush=True)
        video_uri = poll_operation(op_name, bearer_token, model, location)
        if video_uri:
            data = urllib.request.urlopen(video_uri, timeout=300).read()
            out = EVIDENCE / "outputs"
            out.mkdir(parents=True, exist_ok=True)
            path = out / "veo-extend-probe.mp4"
            path.write_bytes(data)
            results["output_file"] = str(path.relative_to(ROOT))
            results["output_bytes"] = len(data)
            from scripts.omni_probe import flicker_score

            score = flicker_score(path)
            results["flicker_output"] = score.get("flicker_score")
            print(f"SAVED {path} flicker={score.get('flicker_score')}", flush=True)
        else:
            results["poll_error"] = "operation finished without a video URI"

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "veo_extend_probe.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    return 0 if accepted and results.get("output_bytes") else 1


def project_id() -> str:
    from backend.core.config import get_settings

    return get_settings().gcp_project_id


def poll_operation(
    op_name: str, bearer: str, model: str, location: str, timeout_s: int = 900
) -> str | None:
    """Poll a Veo LRO; return the output video URI when done."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        url = (
            f"https://aiplatform.googleapis.com/v1/projects/"
            f"{project_id()}/locations/{location}/publishers/google/"
            f"models/{model}:fetchPredictOperation"
        )
        request = urllib.request.Request(
            url,
            data=json.dumps({"operationName": op_name}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"  poll error: {str(exc)[:160]}", flush=True)
            time.sleep(15)
            continue
        if payload.get("done"):
            videos = (
                (payload.get("response") or {}).get("videos")
                or (payload.get("response") or {}).get("generatedSamples")
                or []
            )
            for video in videos:
                uri = video.get("gcsUri") or video.get("uri")
                if uri:
                    return str(uri)
            filtered = (payload.get("response") or {}).get("raiMediaFilteredReasons")
            print(f"  done without video: {str(filtered)[:200]}", flush=True)
            return None
        time.sleep(15)
    print("  timeout waiting for Veo operation", flush=True)
    return None


if __name__ == "__main__":
    import urllib.error

    sys.exit(main())
