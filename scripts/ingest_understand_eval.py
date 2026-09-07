#!/usr/bin/env python
"""Ingest understand eval: real Gemini watches labeled clips for spoken
words AND a scene description.

Gates (thresholds.yaml): ingest_transcript_judgment and
ingest_scene_judgment mean_case_accuracy >= 0.8.

Speech rows are real Chirp 3 HD lines muxed onto a color field (C-1.3
labeled INPUT). Silent/tone rows have no spoken words — inventing a line
is a miss. Scoring is against the label sheet, not canned model output.

Cost: 8 multimodal flash calls/run × 3, plus TTS on speech rows.
Printed before billing; --yes if estimate > $5 (C-7.2).
Evidence: docs/evidence/ingest-understand/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.core.generative import tts_synthesize
from backend.core.media import FFmpeg, get_media
from backend.supervisor.station_agents.ingest_understand import (
    decide_ingest_understand,
)

DATASET = ROOT / "backend" / "evals" / "datasets" / "ingest_understand_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "ingest-understand"
THRESHOLD = 0.8
ESTIMATE_MICROS_PER_CALL = 8_000


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE) if w}


def _lavfi(picture: str) -> str:
    return {
        "blue": "color=c=blue:s=320x240:d=2.5",
        "black": "color=c=black:s=320x240:d=2.5",
        "bars": "smptebars=s=320x240:d=2.5",
    }.get(picture, "color=c=blue:s=320x240:d=2.5")


def _mux(
    media: FFmpeg,
    *,
    picture: str,
    wav: bytes | None,
    tone: bool,
    dest: Path,
) -> bytes:
    video = _lavfi(picture)
    cmd = [
        media.ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        video,
    ]
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "line.wav"
        if wav is not None:
            wav_path.write_bytes(wav)
            cmd.extend(["-i", str(wav_path)])
        elif tone:
            cmd.extend(["-f", "lavfi", "-i", "sine=frequency=1000:duration=2.5"])
        else:
            cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=2.5"])
        cmd.extend(
            [
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(dest),
            ]
        )
        result = media._run(cmd, timeout=60)
        if result.returncode != 0 or not dest.exists():
            raise RuntimeError(f"mux failed: {result.stderr[:400]!r}")
        return dest.read_bytes()


def _clip_bytes(media: FFmpeg, settings, row: dict, dest: Path) -> bytes:
    kind = str(row.get("kind") or "")
    if kind == "fixture":
        path = ROOT / str(row["fixture"])
        return path.read_bytes()
    wav = None
    if kind == "speech":
        render = tts_synthesize(
            settings,
            ssml=f"<speak>{row['line']}</speak>",
            language_code=str(row.get("language") or "en-US"),
        )
        wav = bytes(render["audio_bytes"])
    return _mux(
        media,
        picture=str(row.get("picture") or "blue"),
        wav=wav,
        tone=kind == "tone",
        dest=dest,
    )


def _score(row: dict, spoken: str, has_speech: bool, scene: str) -> tuple[float, float]:
    expected = row["expected"]
    want_speech = bool(expected["has_speech"])
    want_words = [str(w).casefold() for w in expected.get("words") or []]
    got = _words(spoken)
    transcript_ok = has_speech is want_speech
    if want_speech:
        transcript_ok = transcript_ok and all(w in got for w in want_words)
    else:
        transcript_ok = transcript_ok and not spoken.strip()
    keywords = [str(k).casefold() for k in expected.get("scene_keywords") or []]
    scene_l = scene.casefold()
    scene_ok = all(k in scene_l for k in keywords) and bool(scene.strip())
    return (1.0 if transcript_ok else 0.0, 1.0 if scene_ok else 0.0)


def run_suite(run_index: int) -> tuple[list[dict], dict]:
    settings = get_settings()
    media = get_media(settings)
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records: list[dict] = []
    t_hits = 0
    s_hits = 0
    cost_micros = 0
    with tempfile.TemporaryDirectory() as tmp:
        for row in rows:
            spoken = ""
            has_speech = False
            scene = ""
            decision = ""
            reason = "agent call failed"
            t_score = 0.0
            s_score = 0.0
            dest = Path(tmp) / f"{row['id']}.mp4"
            try:
                payload = _clip_bytes(media, settings, row, dest)
                doc, call_cost = decide_ingest_understand(settings, payload, media)
                cost_micros += int(call_cost)
                decision = doc.decision
                reason = doc.reason
                spoken = str(doc.raw.get("spoken_words") or "")
                has_speech = bool(doc.raw.get("has_speech"))
                scene = str(doc.raw.get("scene") or "")
                t_score, s_score = _score(row, spoken, has_speech, scene)
            except Exception as exc:
                reason = f"ERROR {type(exc).__name__}: {exc}"[:200]
            t_hits += int(t_score)
            s_hits += int(s_score)
            records.append(
                {
                    "run": run_index,
                    "id": row["id"],
                    "decision": decision,
                    "has_speech": has_speech,
                    "spoken_words": spoken[:160],
                    "scene": scene[:160],
                    "transcript_score": t_score,
                    "scene_score": s_score,
                    "reason": reason[:200],
                }
            )
            print(
                json.dumps(
                    {
                        k: records[-1][k]
                        for k in ("run", "id", "transcript_score", "scene_score")
                    }
                ),
                flush=True,
            )
    n = len(rows) or 1
    t_acc = t_hits / n
    s_acc = s_hits / n
    summary = {
        "run": run_index,
        "ingest_transcript_judgment": round(t_acc, 3),
        "ingest_scene_judgment": round(s_acc, 3),
        "mean_case_accuracy": round(min(t_acc, s_acc), 3),
        "transcript_hits": t_hits,
        "scene_hits": s_hits,
        "n": len(rows),
        "cost_micros": cost_micros,
        "pass": t_acc >= THRESHOLD and s_acc >= THRESHOLD,
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    n_lines = sum(
        1 for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    estimate = n_lines * args.runs * ESTIMATE_MICROS_PER_CALL
    estimate_usd = round(estimate / 1_000_000, 4)
    print(
        json.dumps(
            {
                "cases": n_lines,
                "runs": args.runs,
                "estimate_usd": estimate_usd,
                "note": "plus Chirp TTS on speech rows",
            }
        ),
        flush=True,
    )
    if estimate_usd > 5 and not args.yes:
        print("estimate exceeds $5 — pass --yes to run (C-7.2)", file=sys.stderr)
        return 2
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    summaries: list[dict] = []
    for run_index in range(1, args.runs + 1):
        rows, summary = run_suite(run_index)
        all_rows.extend(rows)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    t_mean = sum(s["ingest_transcript_judgment"] for s in summaries) / len(summaries)
    s_mean = sum(s["ingest_scene_judgment"] for s in summaries) / len(summaries)
    total_cost = sum(s["cost_micros"] for s in summaries)
    rolled = {
        "ingest_transcript_judgment": round(t_mean, 3),
        "ingest_scene_judgment": round(s_mean, 3),
        "mean_case_accuracy": round(min(t_mean, s_mean), 3),
        "cost_micros": total_cost,
        "cost_usd": round(total_cost / 1_000_000, 4),
        "runs": summaries,
        "pass": t_mean >= THRESHOLD and s_mean >= THRESHOLD,
    }
    (EVIDENCE / "ingest_understand_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_rows) + "\n",
        encoding="utf-8",
    )
    (EVIDENCE / "ingest_understand_eval_summary.json").write_text(
        json.dumps(rolled, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(rolled), flush=True)
    return 0 if rolled["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
