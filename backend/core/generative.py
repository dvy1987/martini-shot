"""Thin adapter over the Google media-model family (A5: thin adapters,
thick system). Omni video on the Vertex Agent Platform Interactions API is
the PRIMARY video path; Veo stays the fallback (decision log 2026-09-04,
evidence docs/evidence/G0/omni_probe_2026-09-04.json).

Proven call shape (the one that survived every probe failure):
- media by gs:// URI (Vertex runtime)
- op named via generation_config.video_config.task ("extend"/"edit")
- NO response_format — aspect_ratio there is rejected for extend/edit tasks
  and poisoned every earlier attempt
- prompts in the docs' simple style; elaborate instructions caused a
  generation refusal
"""

from __future__ import annotations

import json
import math
from typing import Any

from backend.core.config import Settings
from backend.core.models import OMNI_MODEL, VEO_MODEL

# Vertex list prices (2026-09): Omni 1.1 Flash ~$0.10/s of output at 720p;
# 360p drafts are ~1/3 of that. Integer micro-units (C-6.4), ceil per second.
PRICE_PER_SECOND_MICROS = {"720p": 100_000, "360p": 33_334}


def estimate_extend_cost_micros(duration_s: float, *, resolution: str = "720p") -> int:
    """Draft-first cost estimate (C-6.4): integer micros, ceil per second."""
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")
    if resolution not in PRICE_PER_SECOND_MICROS:
        raise ValueError(
            f"unknown resolution {resolution!r} "
            f"(table: {sorted(PRICE_PER_SECOND_MICROS)})"
        )
    per_second = PRICE_PER_SECOND_MICROS[resolution]
    return int(math.ceil(duration_s) * per_second)


def build_extend_prompt(shot_title: str) -> str:
    """Docs' extend guidance: keep it simple; the scene continues as
    established. Elaborate directions caused a generation refusal."""
    return (
        "Extend this video. The scene continues exactly as established, "
        "as if the shot simply keeps rolling. "
        "Keep everything else the same."
    )


def omni_extend(
    settings: Settings,
    *,
    input_uri: str,
    prompt: str,
    task: str = "extend",
    timeout_s: int = 900,
) -> dict[str, Any]:
    """One real Omni interaction (billed). Returns video bytes + usage.
    Not an HTTP path (C-6.5): stations run this inside lease-queue jobs."""
    from google import genai

    client = genai.Client(
        enterprise=True,
        project=settings.gcp_project_id,
        location="global",
    )
    interaction = client.interactions.create(
        model=OMNI_MODEL,
        input=[
            {"type": "text", "text": prompt},
            {"type": "video", "uri": input_uri, "mime_type": "video/mp4"},
        ],
        generation_config={"video_config": {"task": task}},
        timeout=timeout_s,
    )
    status = str(getattr(interaction, "status", "unknown"))
    if status != "completed":
        errors = getattr(interaction, "errors", None)
        raise RuntimeError(f"omni interaction {status}: {str(errors)[:300]}")
    video_bytes = _extract_video(interaction)
    if not video_bytes:
        raise RuntimeError("omni interaction completed with no video output")
    usage = getattr(interaction, "usage", None)
    return {
        "video_bytes": video_bytes,
        "interaction_id": str(getattr(interaction, "id", "")),
        "total_token_count": getattr(usage, "total_token_count", None),
    }


def _extract_video(interaction: Any) -> bytes | None:
    """Video out of an SDK interaction object (output_video, possibly a
    signed URI) — mirrors the probe's proven extraction."""
    import base64
    import urllib.request

    output_video = getattr(interaction, "output_video", None)
    if output_video is None:
        return None
    data = getattr(output_video, "data", None)
    if isinstance(data, (bytes, bytearray)) and data:
        return bytes(data)
    if isinstance(data, str) and data:
        try:
            return base64.b64decode(data)
        except Exception:
            return data.encode("utf-8")
    uri = getattr(output_video, "uri", None)
    if uri:
        try:
            with urllib.request.urlopen(str(uri), timeout=180) as response:
                return response.read()
        except Exception:
            return None
    return None


# -- Veo fallback (predictLongRunning — the Interactions API does not serve
#    the pinned Veo ID; proven 2026-09-04: veo-3.1-fast-generate-001 accepts
#    video_extension with a 720p source, 7s duration, mime type required).

VEO_LOCATION = "global"
VEO_EXTENSION_DURATION_S = 7  # video_extension supports exactly [7]


def extract_veo_video(payload: dict[str, Any]) -> bytes | str:
    """Video out of a completed Veo LRO: inline base64 bytes or a GCS URI.
    An LRO error or an RAI-filtered response raises (fail loud, C-1.1)."""
    if payload.get("error"):
        raise RuntimeError(f"veo operation failed: {str(payload['error'])[:300]}")
    response = payload.get("response") or {}
    videos = response.get("videos") or []
    for video in videos:
        b64 = video.get("bytesBase64Encoded")
        if b64:
            import base64

            return base64.b64decode(b64)
        uri = video.get("gcsUri") or video.get("uri")
        if uri:
            return str(uri)
    if response.get("raiMediaFilteredCount"):
        raise RuntimeError(
            "veo response filtered by safety: "
            f"{str(response.get('raiMediaFilteredReasons'))[:200]}"
        )
    raise RuntimeError(f"veo operation completed without video: {str(payload)[:200]}")


def veo_extend(
    settings: Settings,
    *,
    input_uri: str,
    prompt: str,
    timeout_s: int = 900,
) -> dict[str, Any]:
    """One real Veo video-extension render (billed): predictLongRunning +
    fetchPredictOperation polling. Returns video bytes (fetched when Veo
    returns a GCS URI) + the model id. Not an HTTP path (C-6.5)."""
    import shutil
    import subprocess
    import time
    import urllib.request

    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud is None:
        raise RuntimeError("gcloud executable not found on PATH")
    token = subprocess.run(
        [gcloud, "auth", "application-default", "print-access-token"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    base = (
        f"https://aiplatform.googleapis.com/v1/projects/{settings.gcp_project_id}"
        f"/locations/{VEO_LOCATION}/publishers/google/models/{VEO_MODEL}"
    )

    def _call(url: str, body: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method=method,
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            return dict(json.loads(response.read().decode("utf-8")))

    operation = _call(
        f"{base}:predictLongRunning",
        {
            "instances": [
                {
                    "prompt": prompt,
                    "video": {"gcsUri": input_uri, "mimeType": "video/mp4"},
                }
            ],
            "parameters": {
                "sampleCount": 1,
                "durationSeconds": VEO_EXTENSION_DURATION_S,
            },
        },
    )
    op_name = str(operation.get("name") or "")
    if not op_name:
        raise RuntimeError(f"veo predictLongRunning returned no operation: {operation}")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        payload = _call(f"{base}:fetchPredictOperation", {"operationName": op_name})
        if payload.get("done"):
            video = extract_veo_video(payload)
            if isinstance(video, str):
                with urllib.request.urlopen(video, timeout=300) as response:
                    video = response.read()
            return {
                "video_bytes": video,
                "interaction_id": op_name,
                "model": VEO_MODEL,
            }
        time.sleep(15)
    raise RuntimeError(f"veo operation timed out after {timeout_s}s")
