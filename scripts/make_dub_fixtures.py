#!/usr/bin/env python
"""One-time E-2 fixture generation (C-1.3 labeled synthetic INPUT): the six
English source segments are REAL Chirp 3 HD TTS renders, committed as the
dub-eval originals. The eval then dubs each into es/fr/de and measures timing
against these sources. Billed: ~2k characters ≈ pennies (C-7.2)."""

from __future__ import annotations

import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.core.generative import tts_synthesize

SEGMENTS = {
    "seg-01": "Welcome to Martini Shot, the post-production cockpit.",
    "seg-02": "Spend control watched the retry loop all night long.",
    "seg-03": "Take three, episode one.",
    "seg-04": "The morning report cites the spend control lines with the corresponding evidence.",
    "seg-05": "Intake paused at the dubbing station.",
    "seg-06": "The continuity agent approved adding the dub to continuity.",
}

OUT = ROOT / "fixtures" / "dubbing"


def wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as w:
        return int(w.getnframes() / w.getframerate() * 1000)


def main() -> int:
    settings = get_settings()
    OUT.mkdir(parents=True, exist_ok=True)
    total_cost = 0
    for seg, text in SEGMENTS.items():
        out = OUT / f"{seg}-source.wav"
        if out.exists():
            print(f"skip existing {out.name}")
            continue
        result = tts_synthesize(
            settings,
            ssml=f"<speak>{text}</speak>",
            language_code="en-US",
        )
        out.write_bytes(result["audio_bytes"])
        total_cost += result["cost_estimate_micros"]
        print(
            f"{out.name}: {wav_duration_ms(out)}ms cost={result['cost_estimate_micros']}u"
        )
    print(f"total estimated cost: {total_cost} micros (${total_cost / 1e6:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
