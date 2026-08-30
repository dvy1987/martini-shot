#!/usr/bin/env python
"""Compute flicker scores for the G0 spike pairs and write the verdict JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from g0_spike import flicker_score


def main() -> int:
    pairs = [
        (
            "bg-swap",
            ROOT / "fixtures/spike/shot-01-meadow.mp4",
            ROOT / "docs/evidence/G0/outputs/G0-bg-swap-veo.mp4",
        ),
        (
            "scene-extend",
            ROOT / "fixtures/tmp/shot-03-720p.mp4",
            ROOT / "docs/evidence/G0/outputs/G0-scene-extend-veo.mp4",
        ),
    ]
    results: dict[str, object] = {}
    for name, inp, out in pairs:
        input_score = flicker_score(inp)
        output_score = flicker_score(out)
        ratio = None
        if (
            input_score.get("ok")
            and output_score.get("ok")
            and input_score.get("flicker_score")
        ):
            ratio = round(
                output_score["flicker_score"] / input_score["flicker_score"], 2
            )
        results[name] = {
            "input": input_score,
            "output": output_score,
            "output_over_input": ratio,
        }
        in_f = input_score.get("flicker_score")
        out_f = output_score.get("flicker_score")
        print(f"{name}: input={in_f} output={out_f} ratio={ratio}")
        print(f"  input:  {input_score}")
        print(f"  output: {output_score}")

    out_path = ROOT / "docs/evidence/G0/flicker_scores.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("saved:", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
