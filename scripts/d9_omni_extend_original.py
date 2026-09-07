#!/usr/bin/env python
"""D-9 check on original generated clips (not Big Buck Bunny, not gradients).

1. Make two new short videos from a written scene (Omni first, Veo only if
   Omni cannot create the starting clip).
2. Ask Omni to EXTEND each clip. No silent Veo fallback on extend.
3. If Omni extend fails, stop and report. Do not swap in fake footage.

Usage: .venv\\Scripts\\python.exe scripts\\d9_omni_extend_original.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.core.generative import (
    _extract_video,
    _omni_client,
    _resilient_urlopen,
    build_extend_prompt,
    estimate_extend_cost_micros,
    omni_extend,
)
from backend.core.models import OMNI_MODEL, VEO_MODEL

EVIDENCE = ROOT / "docs" / "evidence" / "D-9"
SCENES = [
    {
        "id": "cafe-sign",
        "prompt": (
            "A quiet street cafe exterior. A wooden sign above the door "
            "reads CAFE. Morning light. Camera does not move. Eight seconds."
        ),
    },
    {
        "id": "table-cup",
        "prompt": (
            "Two people sitting at an outdoor cafe table. A paper cup sits "
            "on the table. Soft daylight. Camera does not move. Eight seconds."
        ),
    },
]


def _upload_gs(settings, key: str, data: bytes) -> str:
    tmp = ROOT / "fixtures" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    local = tmp / Path(key).name
    local.write_bytes(data)
    import shutil
    import subprocess

    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud is None:
        raise RuntimeError("gcloud not on PATH")
    uri = f"gs://{settings.gcs_bucket}/{key}"
    subprocess.run(
        [gcloud, "storage", "cp", str(local), uri],
        check=True,
    )
    return uri


def generate_start_clip(settings, prompt: str) -> dict:
    """Make a brand-new clip. Omni first. Veo only to create the start tape."""
    client = _omni_client(settings, timeout_s=900)
    last_error = ""
    for shape, kwargs in (
        (
            "omni_text_only",
            {
                "model": OMNI_MODEL,
                "input": [{"type": "text", "text": prompt}],
                "timeout": 900,
            },
        ),
        (
            "omni_text_image_to_video",
            {
                "model": OMNI_MODEL,
                "input": [{"type": "text", "text": prompt}],
                "generation_config": {"video_config": {"task": "image_to_video"}},
                "timeout": 900,
            },
        ),
    ):
        try:
            interaction = client.interactions.create(**kwargs)
            status = str(getattr(interaction, "status", "unknown"))
            if status != "completed":
                last_error = (
                    f"{shape} status={status} {getattr(interaction, 'errors', None)}"
                )
                continue
            video = _extract_video(interaction)
            if not video:
                last_error = f"{shape} completed with no video"
                continue
            return {
                "maker": "omni",
                "model": OMNI_MODEL,
                "shape": shape,
                "video_bytes": video,
            }
        except Exception as exc:
            last_error = f"{shape}: {type(exc).__name__}: {exc}"[:400]
            print(f"START CLIP {shape} failed: {last_error}", flush=True)

    from google import genai
    from google.genai import types

    print(
        "Omni could not make the starting clip. Trying Veo to CREATE it only.",
        flush=True,
    )
    veo_client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location="global",
        http_options={"timeout": 900_000},
    )
    try:
        operation = veo_client.models.generate_videos(
            model=VEO_MODEL,
            source=types.GenerateVideosSource(prompt=prompt),
            config={"number_of_videos": 1, "duration_seconds": 8},
        )
        deadline = time.monotonic() + 900
        while not getattr(operation, "done", False):
            if time.monotonic() > deadline:
                raise RuntimeError("Veo generate timed out after 900s")
            time.sleep(10)
            operation = veo_client.operations.get(operation)
        videos = []
        result = getattr(operation, "result", None) or getattr(
            operation, "response", None
        )
        if result is not None:
            videos = list(getattr(result, "generated_videos", None) or [])
        if not videos:
            response = getattr(operation, "response", None)
            samples = getattr(
                getattr(response, "generate_video_response", None),
                "generated_samples",
                None,
            )
            videos = list(samples or [])
        if not videos:
            raise RuntimeError(f"Veo generate finished with no video: {operation}")
        sample = videos[0]
        video_obj = getattr(sample, "video", sample)
        data = getattr(video_obj, "video_bytes", None) or getattr(
            video_obj, "data", None
        )
        if data:
            video_bytes = bytes(data)
        else:
            uri = getattr(video_obj, "uri", None)
            if not uri:
                raise RuntimeError("Veo generate returned no bytes and no uri")
            video_bytes = _resilient_urlopen(
                urllib.request.Request(str(uri)), timeout=180
            )
        return {
            "maker": "veo",
            "model": VEO_MODEL,
            "shape": "veo_text_to_video",
            "video_bytes": video_bytes,
            "omni_create_error": last_error,
        }
    except Exception as exc:
        raise RuntimeError(
            f"Could not generate a starting clip. Omni: {last_error}. "
            f"Veo: {type(exc).__name__}: {exc}"
        ) from exc


def main() -> int:
    n = len(SCENES)
    estimate = n * estimate_extend_cost_micros(8.0) + n * estimate_extend_cost_micros(
        7.0
    )
    print(
        f"estimated_cost_micros={estimate} (~${estimate / 1_000_000:.2f}) "
        f"for {n} new clips + {n} Omni extends (draft 720p table)",
        flush=True,
    )
    settings = get_settings()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    records: list[dict] = []
    for scene in SCENES:
        record: dict = {"scene_id": scene["id"], "prompt": scene["prompt"]}
        print(f"=== making start clip {scene['id']} ===", flush=True)
        try:
            made = generate_start_clip(settings, scene["prompt"])
            key = f"original-probes/{stamp}-{scene['id']}.mp4"
            uri = _upload_gs(settings, key, made["video_bytes"])
            record.update(
                {
                    "start_maker": made["maker"],
                    "start_model": made["model"],
                    "start_shape": made["shape"],
                    "source_uri": uri,
                    "start_bytes": len(made["video_bytes"]),
                }
            )
            if made.get("omni_create_error"):
                record["omni_create_error"] = made["omni_create_error"]
            print(
                f"START CLIP ok maker={made['maker']} bytes={len(made['video_bytes'])} {uri}",
                flush=True,
            )
            print(f"=== Omni EXTEND {scene['id']} (no Veo backup) ===", flush=True)
            render = omni_extend(
                settings,
                input_uri=uri,
                prompt=build_extend_prompt(scene["id"]),
            )
            out_key = f"original-probes/{stamp}-{scene['id']}-omni-extend.mp4"
            out_uri = _upload_gs(settings, out_key, render["video_bytes"])
            record.update(
                {
                    "omni_extend": "ok",
                    "extend_model": render.get("model") or OMNI_MODEL,
                    "extend_bytes": len(render["video_bytes"]),
                    "extend_uri": out_uri,
                    "extend_interaction_id": render.get("interaction_id"),
                }
            )
            print(f"OMNI EXTEND ok {out_uri}", flush=True)
        except Exception as exc:
            record["omni_extend"] = "FAILED"
            record["error"] = f"{type(exc).__name__}: {exc}"[:500]
            records.append(record)
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / f"omni_original_extend_{stamp}.json").write_text(
                json.dumps(
                    {"pass": False, "stopped": True, "records": records}, indent=2
                ),
                encoding="utf-8",
            )
            print(
                "STOPPED. Omni did not finish. Not switching tools. Not using fake clips.",
                flush=True,
            )
            print(json.dumps(record, indent=2), flush=True)
            return 1
        records.append(record)

    payload = {"pass": True, "stopped": False, "n": len(records), "records": records}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"omni_original_extend_{stamp}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: payload[k] for k in ("pass", "n")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
