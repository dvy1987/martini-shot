#!/usr/bin/env python
"""Re-probe gated models (Veo, Lyria, nano-banana) on both surfaces.

Fast fail-fast probes; on any success the output is saved as evidence.
Writes docs/evidence/G0/rego_probe.json.
Usage: .venv/Scripts/python.exe scripts/rego_probe.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "G0"
OUT_DIR = EVIDENCE_DIR / "outputs"


def classify(err: str) -> str:
    for code in ["404", "403", "429", "400"]:
        if code in err[:250]:
            return code
    return "other"


def main() -> int:
    from google import genai

    sys.path.insert(0, str(ROOT / "scripts"))
    from g0_spike import load_env

    env = load_env(ROOT / ".env")
    key = env.get("GEMINI_API_KEY", "")
    key_client = genai.Client(api_key=key) if key else None
    vertex_client = genai.Client(enterprise=True, project="martini-shot", location="global")

    results: dict[str, object] = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "probes": [],
    }
    any_success = False

    def probe(name: str, fn) -> None:
        nonlocal any_success
        entry: dict[str, object] = {"name": name}
        try:
            detail = fn()
            entry.update(detail)
            if not entry.get("error"):
                any_success = True
        except Exception as exc:  # noqa: BLE001 - probe records failures verbatim
            entry["error_code"] = classify(str(exc))
            entry["error"] = str(exc)[:200]
        results["probes"].append(entry)  # type: ignore[union-attr]
        print(entry, flush=True)

    # Veo via Vertex (2.0 as the most likely legacy-allocated variant).
    def veo_vertex() -> dict[str, object]:
        op = vertex_client.models.generate_videos(  # type: ignore[name-defined]
            model="veo-2.0-generate-001",
            prompt="A red balloon floating upward, static camera, 4 seconds.",
            config={"number_of_videos": 1, "duration_seconds": 4},
        )
        deadline = datetime.now(tz=timezone.utc).timestamp() + 600
        while not getattr(op, "done", False):
            if datetime.now(tz=timezone.utc).timestamp() > deadline:
                return {"status": "timeout"}
            time.sleep(10)
            op = vertex_client.operations.get(op)  # type: ignore[name-defined]
        samples = op.response.generate_video_response.generated_samples
        saved = []
        for sample in samples:
            uri = getattr(sample.video, "uri", None)
            if uri:
                import urllib.request

                data = urllib.request.urlopen(uri, timeout=120).read()
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                (OUT_DIR / f"rego-{len(saved)}.mp4").write_bytes(data)
                saved.append(len(saved))
        return {"status": "completed", "videos_saved": len(saved)}

    # Image gen via Vertex (known-good modality) as a control.
    def image_vertex() -> dict[str, object]:
        r = vertex_client.models.generate_content(  # type: ignore[name-defined]
            model="gemini-3.1-flash-image",
            contents="A single red balloon floating upward, photorealistic.",
        )
        parts = r.candidates[0].content.parts or []
        for p in parts:
            inline = getattr(p, "inline_data", None)
            if inline and inline.data:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                (OUT_DIR / "rego-image.png").write_bytes(inline.data)
                return {"status": "completed", "image_bytes": len(inline.data)}
        return {"status": "no_image"}

    # Lyria via Vertex and via key.
    def lyria_vertex() -> dict[str, object]:
        r = vertex_client.models.generate_content(  # type: ignore[name-defined]
            model="lyria-3-clip-preview",
            contents="An uplifting 8-second orchestral fanfare.",
        )
        parts = r.candidates[0].content.parts or []
        for p in parts:
            inline = getattr(p, "inline_data", None)
            if inline and inline.data:
                return {"status": "completed", "audio_bytes": len(inline.data)}
        return {"status": "no_audio", "parts": str(parts)[:150]}

    def lyria_key() -> dict[str, object]:
        r = key_client.models.generate_content(  # type: ignore[name-defined]
            model="lyria-3-clip-preview",
            contents="An uplifting 8-second orchestral fanfare.",
        )
        parts = r.candidates[0].content.parts or []
        for p in parts:
            inline = getattr(p, "inline_data", None)
            if inline and inline.data:
                return {"status": "completed", "audio_bytes": len(inline.data)}
        return {"status": "no_audio", "parts": str(parts)[:150]}

    def nano_banana_key() -> dict[str, object]:
        r = key_client.models.generate_content(  # type: ignore[name-defined]
            model="nano-banana-pro-preview",
            contents="A single red balloon on a white background.",
        )
        parts = r.candidates[0].content.parts or []
        for p in parts:
            inline = getattr(p, "inline_data", None)
            if inline and inline.data:
                return {"status": "completed", "image_bytes": len(inline.data)}
        return {"status": "no_image"}

    def veo_key() -> dict[str, object]:
        op = key_client.models.generate_videos(  # type: ignore[name-defined]
            model="veo-3.1-fast-generate-preview",
            prompt="A red balloon floating upward, static camera, 4 seconds.",
            config={"number_of_videos": 1, "duration_seconds": 4},
        )
        deadline = datetime.now(tz=timezone.utc).timestamp() + 600
        while not getattr(op, "done", False):
            if datetime.now(tz=timezone.utc).timestamp() > deadline:
                return {"status": "timeout"}
            time.sleep(10)
            op = key_client.operations.get(op)  # type: ignore[name-defined]
        samples = op.response.generate_video_response.generated_samples
        return {"status": "completed", "videos": len(samples)}

    probe("veo-2.0 vertex", veo_vertex)
    probe("gemini-3.1-flash-image vertex (control)", image_vertex)
    probe("lyria-3 vertex", lyria_vertex)
    probe("lyria-3 gemini-api-key", lyria_key)
    probe("nano-banana-pro gemini-api-key", nano_banana_key)
    probe("veo-3.1-fast gemini-api-key", veo_key)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "rego_probe.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("any_success:", any_success, flush=True)
    return 0


if __name__ == "__main__":
    import time

    sys.exit(main())
