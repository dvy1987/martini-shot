"""Caption spec sub-check (S5 / D-3). Parsers + rule IDs; no screen of its own."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

TTML_NS = "http://www.w3.org/ns/ttml"
MIN_DURATION_S = 5 / 6  # 5/6 second (common caption spec floor)
MAX_CPS = 20.0
MAX_LINE_CHARS = 42
GAP_MIN_S = 2 / 24  # two frames at 24 fps

RULE_READING_SPEED = "CAP-001"
RULE_LINE_LENGTH = "CAP-002"
RULE_MIN_DURATION = "CAP-003"
RULE_GAP = "CAP-004"
RULE_OVERLAP = "CAP-005"
RULE_TTML_PROFILE = "CAP-006"
RULE_EMPTY = "CAP-007"


@dataclass(frozen=True)
class Cue:
    start_s: float
    end_s: float
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return " ".join(self.lines).strip()

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)


@dataclass(frozen=True)
class Violation:
    rule_id: str
    message: str
    cue_index: int | None = None


_SRT_TS = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def _hms(h: int, m: int, s: int, ms: int) -> float:
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_srt(text: str) -> list[Cue]:
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        match = None
        body_start = 0
        for i, ln in enumerate(lines):
            match = _SRT_TS.search(ln)
            if match:
                body_start = i + 1
                break
        if match is None:
            continue
        g = [int(x) for x in match.groups()]
        start = _hms(g[0], g[1], g[2], g[3])
        end = _hms(g[4], g[5], g[6], g[7])
        body = tuple(lines[body_start:]) or ("",)
        cues.append(Cue(start, end, body))
    return cues


def parse_vtt(text: str) -> list[Cue]:
    converted = re.sub(
        r"(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})",
        lambda m: f"{int(m.group(1) or 0):02d}:{m.group(2)}:{m.group(3)},{m.group(4)}",
        text.replace("\r\n", "\n"),
    )
    return parse_srt(converted)


def _ttml_seconds(raw: str) -> float:
    raw = raw.strip()
    if raw.endswith("s") and raw[:-1].replace(".", "", 1).isdigit():
        return float(raw[:-1])
    match = re.match(r"(?:(\d+):)?(\d+):(\d+)(?:\.(\d+))?", raw)
    if match:
        h = int(match.group(1) or 0)
        m = int(match.group(2))
        s = int(match.group(3))
        frac = match.group(4) or "0"
        ms = int(frac.ljust(3, "0")[:3])
        return _hms(h, m, s, ms)
    return 0.0


def parse_ttml(text: str) -> tuple[list[Cue], bool]:
    """Return cues and whether the TTML profile xmlns is present."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return [], False
    tag = root.tag
    has_ns = tag.startswith("{") and TTML_NS in tag
    xmlns_ok = has_ns or TTML_NS in text
    cues: list[Cue] = []
    for el in root.iter():
        local = el.tag.split("}")[-1]
        if local != "p":
            continue
        begin = _ttml_seconds(el.attrib.get("begin", "0"))
        end = _ttml_seconds(el.attrib.get("end", "0"))
        lines = tuple((el.text or "").split("\n")) or ("",)
        cues.append(Cue(begin, end, lines))
    return cues, xmlns_ok


def parse_captions(text: str, filename: str) -> tuple[list[Cue], list[Violation]]:
    lower = filename.lower()
    extra: list[Violation] = []
    if lower.endswith(".ttml") or lower.endswith(".xml"):
        cues, xmlns_ok = parse_ttml(text)
        if not xmlns_ok:
            extra.append(
                Violation(RULE_TTML_PROFILE, "TTML missing required xmlns profile")
            )
        return cues, extra
    if lower.endswith(".vtt"):
        return parse_vtt(text), extra
    return parse_srt(text), extra


def validate_cues(cues: list[Cue]) -> list[Violation]:
    found: list[Violation] = []
    for i, cue in enumerate(cues):
        if not cue.text:
            found.append(Violation(RULE_EMPTY, "empty cue text", i))
        if cue.duration_s < MIN_DURATION_S:
            found.append(
                Violation(
                    RULE_MIN_DURATION,
                    f"duration {cue.duration_s:.3f}s < {MIN_DURATION_S:.3f}s",
                    i,
                )
            )
        if cue.duration_s > 0 and len(cue.text) / cue.duration_s > MAX_CPS:
            found.append(
                Violation(
                    RULE_READING_SPEED,
                    f"reading speed {len(cue.text) / cue.duration_s:.1f} cps > {MAX_CPS}",
                    i,
                )
            )
        for line in cue.lines:
            if len(line) > MAX_LINE_CHARS:
                found.append(
                    Violation(
                        RULE_LINE_LENGTH,
                        f"line length {len(line)} > {MAX_LINE_CHARS}",
                        i,
                    )
                )
        if i > 0:
            prev = cues[i - 1]
            if cue.start_s < prev.end_s:
                found.append(Violation(RULE_OVERLAP, "cue overlaps previous", i))
            elif cue.start_s - prev.end_s < GAP_MIN_S:
                found.append(Violation(RULE_GAP, "gap shorter than 2 frames", i))
    return found


def check_captions(text: str, filename: str) -> list[Violation]:
    cues, extra = parse_captions(text, filename)
    return extra + validate_cues(cues)
