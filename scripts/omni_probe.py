#!/usr/bin/env python
"""Omni-vs-Veo capability probe (owner request 2026-09-04, A5 model-choice rule).

Background (G0, 2026-08-29): Veo 3.1 Fast `veo-3.1-fast-generate-001` is the
PROVEN render path (bg-swap + scene-extend rendered, flicker-gated). Omni
video ops all failed then: 400s/404s on the -preview ID, then a hard Vertex
429; only Omni text completed. Meanwhile Omni 1.1 Flash went GA (2026-08-27,
stable ID `gemini-omni-1.1-flash`, -preview deprecates 2026-09-30) with
append-style extension (3-10s), first/last-frame interpolation and 360p
drafting (~1/3 of 720p cost; 720p ~= $0.10/s output).

This probe re-tests Omni VIDEO on the GA ID with the SAME two ops, inputs
and prompts G0 ran through Veo, so outputs are directly comparable on the
deterministic flicker metric:

  Stage 1  availability matrix: {GA, preview} x {vertex-global, gemini-api},
           text-only interactions (near-zero cost).
  Stage 2  on the first working (runtime, model): scene-extend on
           shot-03-clearing.mp4 + bg-swap edit on shot-01-meadow.mp4,
           bare conversational payload (no response_format — the G0 400
           trap), Files API upload on the gemini-api runtime, GCS reference
           on the vertex runtime.

Draft-tier spend estimate: ~2 x 8s x <=$0.10/s ~= $1.60 worst case (720p),
~$0.55 at 360p — inside the <=$5 eval autonomy envelope.

Evidence: docs/evidence/G0/omni_ops_2026-09-04.jsonl + omni_probe_2026-09-04.json.
Usage: .venv/Scripts/python.exe scripts/omni_probe.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "G0"
OUTPUT_DIR = EVIDENCE_DIR / "outputs"
GA_MODEL = "gemini-omni-1.1-flash"
PREVIEW_MODEL = "gemini-omni-1.1-flash-preview"
TEXT_MODELS = [GA_MODEL, PREVIEW_MODEL]

OPS = [
    {
        "op_id": "G0-scene-extend-omni-01",
        "task": "extend",
        "shot": "shot-03-clearing.mp4",
        # Docs' extend guidance: keep the extend prompt simple; elaborate
        # instructions caused a generation refusal on the first attempt.
        "prompt": (
            "Extend this video. The scene continues exactly as established, "
            "as if the shot simply keeps rolling. Keep everything else the same."
        ),
    },
    {
        "op_id": "G0-bg-swap-omni-01",
        "task": "edit",
        "shot": "shot-01-meadow.mp4",
        "prompt": (
            "Replace the background environment with a rainy neon-lit city "
            "street at night. Keep the subject, its motion, and the camera "
            "movement exactly the same. Keep everything else the same."
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


def flicker_score(path: Path) -> dict[str, object]:
    """Same deterministic metric as g0_spike.py: mean temporal-median
    residual on grayscale (half-res), motion-invariant, lower is better."""
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
    height = stack.shape[1]
    return {
        "ok": True,
        "flicker_score": round(float(residual.mean()), 5),
        "p99_residual": round(float(np.percentile(residual, 99)), 5),
        "frames_analyzed": len(frames),
        "frame_height_px": int(height * 2),  # analyzed at half-res
        "definition": "mean |I_t - median3| grayscale [0,1], half-res, lower=better",
    }


def stage1_availability() -> tuple[str, str] | None:
    """Text-only matrix; returns (runtime, model) of the first completed."""
    env = load_env(ROOT / ".env")
    env.update(os.environ)
    api_key = env.get("GEMINI_API_KEY", "")
    project = env.get("GOOGLE_CLOUD_PROJECT", "")
    candidates: list[tuple[str, object]] = []
    if api_key:
        from google import genai

        candidates.append(("gemini_api", genai.Client(api_key=api_key)))
    if project:
        from google import genai

        candidates.append(
            (
                "vertex",
                genai.Client(enterprise=True, project=project, location="global"),
            )
        )

    matrix: list[dict[str, object]] = []
    for runtime, client in candidates:
        for model in TEXT_MODELS:
            entry: dict[str, object] = {"runtime": runtime, "model": model}
            try:
                interaction = client.interactions.create(
                    model=model,
                    input="Reply with exactly: omni text OK",
                    timeout=120,
                )
                status = str(getattr(interaction, "status", "unknown"))
                entry["status"] = status
                if status == "completed":
                    matrix.append(entry)
                    print(f"  AVAILABLE: {runtime} / {model}", flush=True)
                    return runtime, model
            except Exception as exc:
                entry["error"] = str(exc)[:220]
            matrix.append(entry)
            print(f"  {entry}", flush=True)
    return None


def upload_for_runtime(runtime: str, client: object, shot_path: Path) -> dict[str, str]:
    """gemini-api -> Files API upload; vertex -> GCS reference."""
    if runtime == "gemini_api":
        video_file = client.files.upload(file=str(shot_path))  # type: ignore[attr-defined]
        video_file = client.files.get(name=video_file.name)  # type: ignore[attr-defined]
        waited = 0
        while getattr(video_file, "state", "") == "PROCESSING" and waited < 300:
            time.sleep(10)
            waited += 10
            video_file = client.files.get(name=video_file.name)  # type: ignore[attr-defined]
        if getattr(video_file, "state", "") == "FAILED":
            raise RuntimeError("Files API upload state FAILED")
        uri = getattr(video_file, "uri", None)
        if not uri:
            raise RuntimeError("Files API returned no URI")
        return {"uri": str(uri), "mime_type": "video/mp4"}

    env = load_env(ROOT / ".env")
    env.update(os.environ)
    bucket_name = env.get("GCS_BUCKET", "martini-shot-media")
    from google.cloud import storage

    storage_client = storage.Client(project=env.get("GOOGLE_CLOUD_PROJECT", ""))
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"probes/{shot_path.name}")
    if not blob.exists():
        blob.upload_from_filename(str(shot_path))
    return {
        "uri": f"gs://{bucket_name}/probes/{shot_path.name}",
        "mime_type": "video/mp4",
    }


def extract_video_bytes(interaction: object) -> bytes | None:
    """Video out of either an SDK interaction object (output_video) or a
    raw-REST interaction dict (steps[].model_output content items)."""
    import base64
    import urllib.request

    def fetch(uri: str) -> bytes | None:
        try:
            with urllib.request.urlopen(uri, timeout=180) as response:
                return response.read()
        except Exception:
            return None

    if isinstance(interaction, dict):
        steps = interaction.get("steps") or []
        for step in steps:
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            for content in step.get("content") or []:
                if not isinstance(content, dict) or content.get("type") != "video":
                    continue
                data = content.get("data")
                if isinstance(data, str) and data:
                    try:
                        return base64.b64decode(data)
                    except Exception:
                        return data.encode("utf-8")
                uri = content.get("uri") or content.get("gcs_uri")
                if uri:
                    fetched = fetch(str(uri))
                    if fetched:
                        return fetched
        return None

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
        return fetch(str(uri))
    return None


def run_video_op(
    runtime: str,
    client: object,
    model: str,
    spec: dict[str, str],
) -> dict[str, object]:
    """Vertex Agent Platform path (extend-videos doc, 2026-09-03): media by
    gs:// URI, response_format as a LIST, op named via
    generation_config.video_config.task. SDK first, raw REST (exact
    documented endpoint + bearer token) as fallback."""

    shot_path = ROOT / "fixtures" / "spike" / spec["shot"]
    record: dict[str, object] = {
        "op_id": spec["op_id"],
        "task": spec["task"],
        "model": model,
        "runtime": runtime,
        "input_shot": spec["shot"],
        "prompt": spec["prompt"],
        "started_utc": datetime.now(tz=timezone.utc).isoformat(),
        "input_bytes": shot_path.stat().st_size,
    }

    # PROVEN shape (2026-09-04): gs:// media + generation_config.video_config.task,
    # NO response_format — aspect_ratio in response_format is explicitly
    # rejected for extend/edit tasks (doc field is t2v-only), and that one
    # field poisoned every earlier probe attempt.
    gs_uri = f"gs://martini-shot-media/probes/{spec['shot']}"
    record["input_uri"] = gs_uri

    interaction = None
    last_error = ""
    for label, call in (
        (
            "sdk_task_only",
            lambda: client.interactions.create(  # type: ignore[attr-defined]
                model=model,
                input=[
                    {"type": "text", "text": spec["prompt"]},
                    {"type": "video", "uri": gs_uri, "mime_type": "video/mp4"},
                ],
                generation_config={"video_config": {"task": spec["task"]}},
                timeout=900,
            ),
        ),
        (
            "sdk_bare",
            lambda: client.interactions.create(  # type: ignore[attr-defined]
                model=model,
                input=[
                    {"type": "text", "text": spec["prompt"]},
                    {"type": "video", "uri": gs_uri, "mime_type": "video/mp4"},
                ],
                timeout=900,
            ),
        ),
    ):
        try:
            interaction = call()
            record["call_shape"] = label
            break
        except Exception as exc:
            last_error = str(exc)[:400]
            print(f"  {label} rejected: {last_error[:160]}", flush=True)
            if "429" in last_error[:120]:
                time.sleep(90)
    if interaction is None:
        # Raw REST fallback: the exact documented endpoint + bearer token,
        # bypassing any SDK serialization of the list-typed response_format.
        env = load_env(ROOT / ".env")
        env.update(os.environ)
        project = env.get("GOOGLE_CLOUD_PROJECT", "")
        import shutil
        import subprocess
        import urllib.request

        gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
        if gcloud is None or not project:
            record.update({"status": "api_error", "error": last_error})
            return record
        token = subprocess.run(
            [gcloud, "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        url = (
            "https://aiplatform.googleapis.com/v1beta1/projects/"
            f"{project}/locations/global/interactions"
        )
        body = {
            "model": model,
            "input": [
                {"type": "text", "text": spec["prompt"]},
                {"type": "video", "uri": gs_uri, "mime_type": "video/mp4"},
            ],
            "generation_config": {"video_config": {"task": spec["task"]}},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                record["call_shape"] = "raw_rest_doc_exact"
                interaction = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            record.update(
                {"status": "api_error", "error": f"raw REST: {str(exc)[:400]}"}
            )
            return record

    def field(obj: object, name: str, default: object = None) -> object:
        """Read a field off either an SDK interaction object or a raw-REST
        JSON dict (the two response shapes this probe can receive)."""
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    status = str(field(interaction, "status", "unknown"))
    record["status"] = status
    record["interaction_id"] = field(interaction, "id")
    usage = field(interaction, "usage")
    if usage is not None:
        record["total_token_count"] = field(usage, "total_token_count")

    if status != "completed":
        record["error"] = str(
            field(interaction, "errors", "") or "status != completed"
        )[:500]
        return record

    video_bytes = extract_video_bytes(interaction)
    if not video_bytes:
        record["error"] = "no downloadable video in response"
        return record
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{spec['op_id']}.mp4"
    out_path.write_bytes(video_bytes)
    record.update(
        {
            "output_file": str(out_path.relative_to(ROOT)),
            "output_bytes": len(video_bytes),
            "flicker_input": flicker_score(shot_path),
            "flicker_output": flicker_score(out_path),
            "finished_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
    )
    return record


def main() -> int:
    # Optional: `omni_probe.py G0-scene-extend-omni-01` re-runs one op only
    # (avoids re-paying for ops already completed and recorded in the JSONL).
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    specs = [s for s in OPS if not only or s["op_id"] == only]
    print("Stage 1: Omni availability matrix (text-only)...", flush=True)
    available = stage1_availability()
    summary: dict[str, object] = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "purpose": "Omni-vs-Veo: re-probe Omni video on the GA ID after G0's preview-era failures",
    }
    if available is None:
        summary["verdict"] = "omni_unavailable"
        summary["stage1"] = "no (runtime, model) completed a text interaction"
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (EVIDENCE_DIR / "omni_probe_2026-09-04.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 1

    runtime, model = available
    print(f"Stage 2: video ops on {runtime} / {model}...", flush=True)
    env = load_env(ROOT / ".env")
    env.update(os.environ)
    if runtime == "vertex":
        from google import genai

        client: object = genai.Client(
            enterprise=True,
            project=env.get("GOOGLE_CLOUD_PROJECT", ""),
            location="global",
        )
    else:
        from google import genai

        client = genai.Client(api_key=env.get("GEMINI_API_KEY", ""))

    ops_log = EVIDENCE_DIR / "omni_ops_2026-09-04.jsonl"
    ops_log.parent.mkdir(parents=True, exist_ok=True)
    all_ok = True
    with ops_log.open("a", encoding="utf-8") as evidence:
        for index, spec in enumerate(specs):
            if index > 0:
                print("  spacing 90s between ops for per-minute quota...", flush=True)
                time.sleep(90)
            record = run_video_op(runtime, client, model, spec)
            record["recorded_utc"] = datetime.now(tz=timezone.utc).isoformat()
            evidence.write(json.dumps(record) + "\n")
            evidence.flush()
            print(json.dumps(record, indent=2), flush=True)
            if record.get("status") != "completed":
                all_ok = False

    summary["stage2_model"] = model
    summary["stage2_runtime"] = runtime
    summary["all_ops_completed"] = all_ok
    (EVIDENCE_DIR / "omni_probe_2026-09-04.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
