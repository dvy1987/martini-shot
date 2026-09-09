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
import logging
import math
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from backend.core.api_resilience import call_with_resilience
from backend.core.config import Settings
from backend.core.models import OMNI_MODEL, TTS_API_BASE, TTS_VOICE_FAMILY, VEO_MODEL

log = logging.getLogger("pc.generative")


def _resilient_urlopen(request: urllib.request.Request, timeout: float) -> bytes:
    """Shared resilience wrapper (owner directive 2026-09-07): the whole
    urlopen+read is ONE try-unit, so a mid-read transient failure also
    retries. Only idempotent calls may pass through here."""

    def _open() -> bytes:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    return call_with_resilience(_open)


# Vertex list prices (2026-09): Omni 1.1 Flash ~$0.10/s of output at 720p;
# 360p drafts are ~1/3 of that. Integer micro-units (C-6.4), ceil per second.
PRICE_PER_SECOND_MICROS = {"720p": 100_000, "360p": 33_334}

# Google Cloud TTS Chirp 3 HD list price (2026-09): $30 per 1M characters.
PRICE_PER_CHAR_MICROS = 30.0

# Real, previously-undocumented Omni "edit" server-side constraint
# (2026-09-09 demo failure: "Editing duration 14 exceeds maximum duration
# 10"). omni_edit_bounded chunks anything longer than this.
OMNI_EDIT_MAX_DURATION_S = 10.0
# Gap between sequential per-chunk calls so back-to-back edits on the same
# source clip don't trip a rate limit (owner directive 2026-09-09).
OMNI_EDIT_CHUNK_GAP_S = 2.0


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
    speaking_rate: float = 1.0,
) -> dict[str, Any]:
    """REAL Google Cloud TTS synthesis (Chirp 3 HD, A10/E-2). SSML in
    (`<speak>…`), LINEAR16 WAV bytes out — the raw audio the dub QC
    measures. speaking_rate scales playback speed server-side
    (audioConfig.speakingRate) — the time-fit lever for dub pacing.
    Billed per character; cost estimate rides along.
    Raises on any API error (fail loud, C-1.1)."""
    voice = voice_name or f"{language_code}-{TTS_VOICE_FAMILY}"
    body = {
        "input": {"ssml": ssml},
        "voice": {"languageCode": language_code, "name": voice},
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": 24000,
            "speakingRate": speaking_rate,
        },
    }
    token = _gcloud_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        # Local ADC requires an explicit quota project for
        # texttospeech.googleapis.com (403 SERVICE_DISABLED otherwise).
        "x-goog-user-project": settings.gcp_project_id,
    }
    request = urllib.request.Request(
        f"{TTS_API_BASE}/text:synthesize",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    payload = json.loads(_resilient_urlopen(request, timeout=120))
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


def _omni_client(settings: Settings, *, timeout_s: int) -> Any:
    """Vertex Omni client. HTTP timeout is milliseconds; video ops exceed
    the SDK's 120s default (D-10 quality eval recorded a write timeout).

    Passing an httpx client disables google-auth AuthorizedSession, whose
    120s write timeout aborted live-action Omni extends (2026-09-07).
    """
    import httpx
    from google import genai
    from google.genai import types

    http_timeout = httpx.Timeout(timeout_s, connect=60.0)
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location="global",
        http_options=types.HttpOptions(
            timeout=timeout_s * 1000,
            httpx_client=httpx.Client(timeout=http_timeout),
        ),
    )


def is_omni_transport_timeout(exc: BaseException) -> bool:
    """True when Omni's HTTP client aborted a long video call (not recitation)."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return "timeout" in text or "timed out" in text


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
    client = _omni_client(settings, timeout_s=timeout_s)
    last: BaseException | None = None
    for attempt in range(1, 4):
        try:
            interaction = client.interactions.create(
                model=OMNI_MODEL,
                input=[
                    {"type": "text", "text": prompt},
                    {"type": "video", "uri": input_uri, "mime_type": "video/mp4"},
                ],
                generation_config={"video_config": {"task": task}},
                timeout=timeout_s,
            )
            break
        except Exception as exc:
            last = exc
            if not is_omni_transport_timeout(exc) or attempt == 3:
                raise
            log.warning(
                "omni extend transport timeout attempt %s/3; retrying",
                attempt,
            )
    else:
        raise RuntimeError(f"omni extend failed: {last}")
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
        "model": OMNI_MODEL,
        "interaction_id": str(getattr(interaction, "id", "")),
        "total_token_count": getattr(usage, "total_token_count", None),
    }


def omni_edit(
    settings: Settings,
    *,
    input_uri: str,
    prompt: str,
    reference_uris: tuple[str, ...] = (),
    timeout_s: int = 900,
) -> dict[str, Any]:
    """One real Omni "edit" interaction (billed): the shared render call for
    every Stage 1a bounded-edit op (D-10 Corrections, E-1 Relight, D-12
    Coverage, D-16 Camera Language). `reference_uris` carries extra subject
    or neighboring-shot images/video the model may consult but must not
    copy verbatim (A5 <IMAGE_REF_N>/<VIDEO_REF_N> tags). Not an HTTP path
    (C-6.5): stations run this inside lease-queue jobs."""
    client = _omni_client(settings, timeout_s=timeout_s)
    content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {"type": "video", "uri": input_uri, "mime_type": "video/mp4"},
    ]
    for _index, ref_uri in enumerate(reference_uris, start=1):
        mime = "video/mp4" if ref_uri.endswith(".mp4") else "image/jpeg"
        kind = "video" if mime == "video/mp4" else "image"
        content.append({"type": kind, "uri": ref_uri, "mime_type": mime})
    interaction = client.interactions.create(
        model=OMNI_MODEL,
        input=content,
        generation_config={"video_config": {"task": "edit"}},
        timeout=timeout_s,
    )
    status = str(getattr(interaction, "status", "unknown"))
    if status != "completed":
        errors = getattr(interaction, "errors", None)
        raise RuntimeError(f"omni edit interaction {status}: {str(errors)[:300]}")
    video_bytes = _extract_video(interaction)
    if not video_bytes:
        raise RuntimeError("omni edit interaction completed with no video output")
    usage = getattr(interaction, "usage", None)
    return {
        "video_bytes": video_bytes,
        "model": OMNI_MODEL,
        "interaction_id": str(getattr(interaction, "id", "")),
        "total_token_count": getattr(usage, "total_token_count", None),
    }


def omni_edit_bounded(
    settings: Settings,
    gcs: Any,
    media: Any,
    *,
    input_uri: str,
    prompt: str,
    scratch_prefix: str,
    reference_uris: tuple[str, ...] = (),
    timeout_s: int = 900,
    max_duration_s: float = OMNI_EDIT_MAX_DURATION_S,
    gap_s: float = OMNI_EDIT_CHUNK_GAP_S,
    omni_edit: Callable[..., dict[str, Any]] = omni_edit,
) -> dict[str, Any]:
    """omni_edit, but chop-and-reassemble when the source exceeds Omni's
    real, server-enforced edit duration cap (owner directive 2026-09-09,
    after "Editing duration 14 exceeds maximum duration 10" broke Relight
    mid-demo): split into <=max_duration_s segments, call Omni on each
    SEQUENTIALLY with a gap between calls (avoid tripping a rate limit),
    then concat the edited segments back into one clip. Short clips take
    the single-call path unchanged. `scratch_prefix` is a GCS key prefix
    the caller owns (per-job) for the intermediate chunk uploads; nothing
    else reads them. Not an HTTP path (C-6.5): stations run this inside
    lease-queue jobs. `omni_edit` is injectable for tests (same pattern as
    `render_pickup_repair`) — production always uses the real adapter."""
    source_bytes = gcs.download_bytes(input_uri)
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        src_path = tmp / "source.mp4"
        src_path.write_bytes(source_bytes)
        duration_s = float(media.probe(src_path).get("duration_s") or 0.0)
        if duration_s <= max_duration_s:
            return omni_edit(
                settings,
                input_uri=input_uri,
                prompt=prompt,
                reference_uris=reference_uris,
                timeout_s=timeout_s,
            )
        segment_paths = media.split_segments(src_path, tmp, max_duration_s)
        edited_paths: list[Path] = []
        interaction_ids: list[str] = []
        total_tokens = 0
        for index, segment_path in enumerate(segment_paths):
            if index > 0:
                time.sleep(gap_s)
            scratch_key = f"{scratch_prefix}/chunk-{index:02d}.mp4"
            gcs.upload_bytes(
                scratch_key, segment_path.read_bytes(), content_type="video/mp4"
            )
            scratch_uri = f"gs://{settings.gcs_bucket}/{scratch_key}"
            render = omni_edit(
                settings,
                input_uri=scratch_uri,
                prompt=prompt,
                reference_uris=reference_uris,
                timeout_s=timeout_s,
            )
            edited_path = tmp / f"edited-{index:02d}.mp4"
            edited_path.write_bytes(render["video_bytes"])
            edited_paths.append(edited_path)
            interaction_id = str(render.get("interaction_id") or "")
            if interaction_id:
                interaction_ids.append(interaction_id)
            tokens = render.get("total_token_count")
            if isinstance(tokens, (int, float)):
                total_tokens += int(tokens)
        out_path = tmp / "reassembled.mp4"
        media.concat_videos(edited_paths, out_path)
        return {
            "video_bytes": out_path.read_bytes(),
            "model": OMNI_MODEL,
            "interaction_id": ",".join(interaction_ids),
            "total_token_count": total_tokens or None,
            "chunked": True,
            "chunk_count": len(segment_paths),
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
            return _resilient_urlopen(urllib.request.Request(str(uri)), timeout=180)
        except Exception:
            return None
    return None


# -- Veo fallback (predictLongRunning — the Interactions API does not serve
#    the pinned Veo ID (core/models.py); proven 2026-09-04: it accepts
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
        return dict(
            json.loads(_resilient_urlopen(request, timeout=120).decode("utf-8"))
        )

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
                video = _resilient_urlopen(urllib.request.Request(video), timeout=300)
            return {
                "video_bytes": video,
                "interaction_id": op_name,
                "model": VEO_MODEL,
            }
        time.sleep(15)
    raise RuntimeError(f"veo operation timed out after {timeout_s}s")
