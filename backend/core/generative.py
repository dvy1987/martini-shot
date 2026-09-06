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

import base64
import json
import math
import subprocess
import urllib.request
from typing import Any

from backend.core.config import Settings
from backend.core.models import OMNI_MODEL, TTS_API_BASE, TTS_VOICE_FAMILY, VEO_MODEL

# Vertex list prices (2026-09): Omni 1.1 Flash ~$0.10/s of output at 720p;
# 360p drafts are ~1/3 of that. Integer micro-units (C-6.4), ceil per second.
PRICE_PER_SECOND_MICROS = {"720p": 100_000, "360p": 33_334}

# Google Cloud TTS Chirp 3 HD list price (2026-09): $30 per 1M characters.
PRICE_PER_CHAR_MICROS = 30.0


def estimate_tts_cost_micros(chars: int) -> int:
    """Chirp 3 HD cost estimate (C-6.4): integer micros over input characters."""
    return int(chars * PRICE_PER_CHAR_MICROS)


def _gcloud_access_token() -> str:
    """ADC token via the gcloud CLI (same auth path as the Veo adapter)."""
    import shutil

    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud is None:
        raise RuntimeError("gcloud executable not found on PATH")
    token = subprocess.run(
        [gcloud, "auth", "application-default", "print-access-token"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty access token")
    return token


def tts_synthesize(
    settings: Settings,
    *,
    ssml: str,
    language_code: str,
    voice_name: str | None = None,
) -> dict[str, Any]:
    """REAL Google Cloud TTS synthesis (Chirp 3 HD, A10/E-2). SSML in
    (`<speak>…<prosody rate="…">…`), LINEAR16 WAV bytes out — the raw audio
    the dub QC measures. Billed per character; cost estimate rides along.
    Raises on any API error (fail loud, C-1.1)."""
    voice = voice_name or f"{language_code}-{TTS_VOICE_FAMILY}"
    body = {
        "input": {"ssml": ssml},
        "voice": {"languageCode": language_code, "name": voice},
        "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
    }
    token = _gcloud_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        # Local ADC requires an explicit quota project for
        # texttospeech.googleapis.com (403 SERVICE_DISABLED otherwise).
        "x-goog-user-project": settings.gcp_project_id,
    }
    # Transient 5xxs observed on 2026-09-06 — bounded retry with backoff.
    import time
    import urllib.error

    for attempt in range(3):
        request = urllib.request.Request(
            f"{TTS_API_BASE}/text:synthesize",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as resp:
                payload = json.load(resp)
            break
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == 2:
                raise
            time.sleep(2**attempt)
        except urllib.error.URLError:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    audio_b64 = str(payload.get("audioContent") or "")
    if not audio_b64:
        raise RuntimeError("tts synthesize returned no audio content")
    return {
        "audio_bytes": base64.b64decode(audio_b64),
        "voice": voice,
        "language_code": language_code,
        "chars": len(ssml),
        "cost_estimate_micros": estimate_tts_cost_micros(len(ssml)),
    }


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
