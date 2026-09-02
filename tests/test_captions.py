"""D-3 caption sub-check golden files (AC-S5.2)."""

from pathlib import Path

from backend.stations.delivery.captions import (
    RULE_EMPTY,
    RULE_GAP,
    RULE_LINE_LENGTH,
    RULE_MIN_DURATION,
    RULE_OVERLAP,
    RULE_READING_SPEED,
    RULE_TTML_PROFILE,
    check_captions,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "captions"


def _ids(path: Path) -> set[str]:
    return {
        v.rule_id for v in check_captions(path.read_text(encoding="utf-8"), path.name)
    }


def test_valid_srt_has_no_violations() -> None:
    assert _ids(FIXTURES / "valid.srt") == set()


def test_vtt_and_ttml_happy_and_parse_error() -> None:
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello there\n"
    assert check_captions(vtt, "ok.vtt") == []
    ttml = (
        '<tt xmlns="http://www.w3.org/ns/ttml"><body><div>'
        '<p begin="0s" end="2s">Hello there</p></div></body></tt>'
    )
    assert check_captions(ttml, "ok.ttml") == []
    assert check_captions("<not-xml", "broken.xml")  # parse error → empty cues ok


def test_seven_violation_classes() -> None:
    assert RULE_READING_SPEED in _ids(FIXTURES / "speed.srt")
    assert RULE_LINE_LENGTH in _ids(FIXTURES / "longline.srt")
    assert RULE_MIN_DURATION in _ids(FIXTURES / "shortdur.srt")
    assert RULE_GAP in _ids(FIXTURES / "gap.srt")
    assert RULE_OVERLAP in _ids(FIXTURES / "overlap.srt")
    assert RULE_TTML_PROFILE in _ids(FIXTURES / "profile.ttml")
    assert RULE_EMPTY in _ids(FIXTURES / "empty.srt")
