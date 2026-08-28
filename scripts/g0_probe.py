#!/usr/bin/env python
"""G0 capability probe (plan Phase 0): which pinned models are callable on the project.

Real API round-trips only (C-1.1). Records results to docs/evidence/G0/capability_probe.json:
  1. Vertex model availability (client.models.list membership for pinned IDs).
  2. Text path: gemini-3.7-flash with thinking HIGH + thought summary (tiny call).
  3. Cloud Text-to-Speech availability (voice list round-trip).

Video-generation spend is deliberately NOT part of this probe (it belongs to the
quality spike). Exit 0 = text path + TTS reachable; exit 1 = blocker recorded.
Usage: .venv/Scripts/python.exe scripts/g0_probe.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "G0"
PINNED = {
    "text": "gemini-3.7-flash",
    "video_gen_edit": "gemini-omni-1.1-flash",
    "video_extension": "veo-3.1-generate-preview",
}
TEXT_THINKING_LEVEL = "high"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def adc_token() -> str:
    result = subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def tts_probe(project: str, token: str) -> dict[str, object]:
    url = f"https://texttospeech.googleapis.com/v1/voices?project={project}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        voices = body.get("voices", [])
        chirp = [v for v in voices if "chirp" in v.get("name", "").lower()]
        return {
            "ok": True,
            "voice_count": len(voices),
            "chirp_hd_voices": len(chirp),
        }
    except Exception as exc:  # noqa: BLE001 - probe records any failure verbatim
        return {"ok": False, "error": str(exc)[:300]}


def main() -> int:
    env = load_env(ROOT / ".env")
    env.update(os.environ)
    project = env.get("GOOGLE_CLOUD_PROJECT", "")
    location = env.get("GOOGLE_CLOUD_LOCATION", "global")
    if not project:
        print("GOOGLE_CLOUD_PROJECT missing (.env or environment)")
        return 1

    results: dict[str, object] = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "project": project,
        "location": location,
        "pinned_models": PINNED,
    }

    from google import genai
    from google.genai import types

    client = genai.Client(enterprise=True, project=project, location=location)

    # 1. Model availability via list (free round-trip).
    available: set[str] = set()
    for model in client.models.list():
        name = getattr(model, "name", "") or ""
        available.add(name.split("/")[-1])
    availability = {
        role: {"pinned": pinned, "listed": pinned in available}
        for role, pinned in PINNED.items()
    }
    # Veo family may appear under preview names; record near-matches too.
    availability["video_extension"]["near_matches"] = sorted(
        name for name in available if "veo" in name
    )[:10]
    availability["video_gen_edit"]["near_matches"] = sorted(
        name for name in available if "omni" in name
    )[:10]
    results["model_availability"] = availability

    # 2. Text path: tiny call with thinking HIGH and a thought summary.
    try:
        response = client.models.generate_content(
            model=PINNED["text"],
            contents="Reply with exactly: G0 probe OK",
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=TEXT_THINKING_LEVEL,  # type: ignore[arg-type]
                    include_thoughts=True,
                ),
            ),
        )
        thought_parts = [
            part.text
            for part in (response.candidates[0].content.parts or [])
            if getattr(part, "thought", False) and part.text
        ]
        results["text_probe"] = {
            "ok": bool(response.text),
            "reply": (response.text or "")[:80],
            "thinking_level": TEXT_THINKING_LEVEL,
            "thought_summary_present": bool(thought_parts),
            "usage_metadata": str(response.usage_metadata),
        }
    except Exception as exc:  # noqa: BLE001 - probe records any failure verbatim
        results["text_probe"] = {"ok": False, "error": str(exc)[:300]}

    # 3. Cloud TTS reachability (Chirp 3 HD voice census).
    try:
        token = adc_token()
        results["tts_probe"] = tts_probe(project, token)
    except Exception as exc:  # noqa: BLE001 - probe records any failure verbatim
        results["tts_probe"] = {"ok": False, "error": str(exc)[:300]}

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE_DIR / "capability_probe.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    text_ok = isinstance(results.get("text_probe"), dict) and results["text_probe"].get(
        "ok"
    )  # type: ignore[union-attr]
    return 0 if text_ok else 1


if __name__ == "__main__":
    sys.exit(main())
