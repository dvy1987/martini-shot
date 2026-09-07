"""Caption writer: script (or a listen) becomes a valid SRT.

The dubbed line IS the caption text — we do not invent dialogue.
Deterministic wrap/time from the script is the default. Gemini writes
only when there is audio and no script. Broken existing SRTs go through
the Caption Remediation editor, then the D-3 rule engine re-validates.
"""

from __future__ import annotations

from backend.stations.delivery.captions import (
    MAX_CPS,
    MAX_LINE_CHARS,
    MIN_DURATION_S,
    parse_srt,
    validate_cues,
)
from backend.stations.delivery.prepare import prepare_captions, write_cues_from_script
from backend.supervisor.station_agents.caption_remediation import render_srt


def test_writer_wraps_long_lines_and_stays_readable() -> None:
    script = (
        "Bienvenido a Martini Shot, la cabina de posproduccion "
        "para un lote de episodios en tres idiomas."
    )
    cues = write_cues_from_script(script, duration_s=8.0)
    assert cues
    assert validate_cues(cues) == []
    for cue in cues:
        for line in cue.lines:
            assert len(line) <= MAX_LINE_CHARS
        assert cue.duration_s + 1e-9 >= MIN_DURATION_S
        assert len(cue.text) / cue.duration_s <= MAX_CPS + 1e-9
    joined = " ".join(cue.text for cue in cues)
    for word in script.split():
        assert word in joined


def test_writer_empty_script_is_nothing() -> None:
    assert write_cues_from_script("   ", duration_s=8.0) == []


def test_prepare_writes_when_captions_are_missing() -> None:
    srt, meta = prepare_captions(
        existing_srt=None,
        script="Hola, este es un doblaje.",
        duration_s=8.0,
        settings=None,
    )
    assert srt
    assert meta["source"] == "writer"
    assert validate_cues(parse_srt(srt)) == []


def test_prepare_keeps_a_valid_existing_srt() -> None:
    existing = render_srt(write_cues_from_script("Hello there.", duration_s=3.0))
    srt, meta = prepare_captions(
        existing_srt=existing,
        script="Hello there.",
        duration_s=3.0,
        settings=None,
    )
    assert meta["source"] == "existing"
    assert srt == existing


def test_prepare_sends_broken_srt_to_the_editor(
    monkeypatch,
) -> None:
    from backend.supervisor.station_agents.base import StationDecision

    broken = "1\n00:00:00,000 --> 00:00:00,200\nThis line is way too long for a legal caption row and also too fast.\n"

    def fake_remediate(_settings, *, cues, violations):
        del cues, violations
        fixed = write_cues_from_script(
            "This line is way too long for a legal caption row and also too fast.",
            duration_s=8.0,
        )
        return (
            StationDecision(
                agent="caption_remediation",
                decision="apply_fixes",
                reason="re-timed and wrapped; meaning preserved",
                confidence="high",
                deterministic_advice="needs_human",
                overridden=True,
                raw={
                    "fixed_cues": [
                        {
                            "start_s": c.start_s,
                            "end_s": c.end_s,
                            "lines": list(c.lines),
                        }
                        for c in fixed
                    ]
                },
            ),
            900,
        )

    monkeypatch.setattr(
        "backend.supervisor.station_agents.caption_remediation.decide_caption_remediation",
        fake_remediate,
    )
    srt, meta = prepare_captions(
        existing_srt=broken,
        script="unused",
        duration_s=8.0,
        settings=object(),
    )
    assert meta["source"] == "editor"
    assert srt
    assert validate_cues(parse_srt(srt)) == []
    assert meta["cost_micros"] == 900


def test_prepare_listen_writer_when_there_is_no_script(monkeypatch) -> None:
    from backend.supervisor.station_agents.base import StationDecision

    def fake_write(_settings, *, script, duration_s, audio):
        del script, duration_s, audio
        return (
            StationDecision(
                agent="caption_write",
                decision="write",
                reason="captioned the spoken line",
                confidence="high",
                deterministic_advice="needs_human",
                overridden=True,
                raw={
                    "cues": [
                        {
                            "start_s": 0.0,
                            "end_s": 3.0,
                            "lines": ["Hola mundo"],
                        }
                    ]
                },
            ),
            1100,
        )

    monkeypatch.setattr(
        "backend.supervisor.station_agents.caption_write.decide_caption_write",
        fake_write,
    )
    srt, meta = prepare_captions(
        existing_srt=None,
        script="",
        duration_s=8.0,
        settings=object(),
        audio=(b"RIFF", "audio/wav"),
    )
    assert meta["source"] == "listen_writer"
    assert "Hola mundo" in (srt or "")
    assert meta["cost_micros"] == 1100


def test_write_agent_prompt_forbids_inventing_dialogue() -> None:
    from backend.supervisor.station_agents.caption_write import build_prompt

    prompt = build_prompt("Hola.", 8.0, has_audio=True)
    assert "listen" in prompt.lower()
    assert "invent" in prompt.lower()
    assert "42" in prompt


def test_write_agent_parse_requires_cues_on_write() -> None:
    import json

    import pytest

    from backend.supervisor.station_agents.caption_write import parse_write_decision

    with pytest.raises(ValueError, match="cues"):
        parse_write_decision(
            json.dumps(
                {
                    "agent": "caption_write",
                    "decision": "write",
                    "reason": "ok",
                    "confidence": "high",
                }
            )
        )


def test_write_agent_refuses_to_invent_when_nothing_to_caption() -> None:
    from backend.supervisor.station_agents.caption_write import decide_caption_write

    decision, cost = decide_caption_write(object(), script="  ", duration_s=8.0)
    assert decision.decision == "needs_human"
    assert cost == 0


def test_quiet_speech_tells_orchestrator_to_retry_loudness() -> None:
    from backend.supervisor.station_agents.caption_write import (
        quiet_audio_orchestrator_note,
    )

    note = quiet_audio_orchestrator_note(
        -25.3,
        loudness_job_id="cyc-demo-ep-01-es-ES-loudness",
        has_speech=True,
    )
    assert note is not None
    assert note["kind"] == "audio_too_quiet"
    assert note["has_speech"] is True
    assert note["proposal"]["command_name"] == "retry_job"
    assert note["proposal"]["args"]["job_id"] == "cyc-demo-ep-01-es-ES-loudness"


def test_silent_scene_does_not_send_quiet_audio_to_loudness() -> None:
    """Room tone / no spoken words may sit quiet on purpose. Do not ask
    loudness to pump it up to talk level."""
    from backend.supervisor.station_agents.caption_write import (
        quiet_audio_orchestrator_note,
    )

    assert (
        quiet_audio_orchestrator_note(
            -38.0,
            loudness_job_id="cyc-demo-ep-01-es-ES-loudness",
            has_speech=False,
        )
        is None
    )


def test_audible_speech_does_not_alarm() -> None:
    from backend.supervisor.station_agents.caption_write import (
        quiet_audio_orchestrator_note,
    )

    assert (
        quiet_audio_orchestrator_note(
            -16.0,
            loudness_job_id="cyc-x-loudness",
            has_speech=True,
        )
        is None
    )
    # A whisper sitting a bit under talk is still speech and still audible.
    assert (
        quiet_audio_orchestrator_note(
            -20.0,
            loudness_job_id="cyc-x-loudness",
            has_speech=True,
        )
        is None
    )


def test_agent_cannot_flag_silence_as_too_quiet_for_loudness() -> None:
    """Hard gate: heard_speech=false wins. Quiet room tone is not a mix job."""
    import json

    from backend.supervisor.station_agents.caption_write import parse_write_decision

    text = json.dumps(
        {
            "agent": "caption_write",
            "decision": "needs_human",
            "heard_speech": False,
            "audio_too_quiet": True,
            "reason": "nothing is said; the bed is very quiet",
            "confidence": "high",
            "proposal": {
                "command_name": "retry_job",
                "args": {"job_id": "cyc-x-loudness"},
            },
        }
    )
    decision = parse_write_decision(text, lufs=-38.0, has_speech=False)
    assert decision.raw.get("audio_too_quiet") is False
    assert not decision.proposal


def test_caption_prompt_says_silence_is_not_a_loudness_miss() -> None:
    from backend.supervisor.station_agents.caption_write import build_prompt

    prompt = build_prompt("Hola.", 8.0, has_audio=True, lufs=-25.0)
    assert "too quiet" in prompt.lower()
    assert "orchestrator" in prompt.lower()
    assert "silence" in prompt.lower() or "no spoken" in prompt.lower()


def test_prepare_attaches_orchestrator_note_only_for_quiet_speech() -> None:
    srt, meta = prepare_captions(
        existing_srt=None,
        script="Hola, este es un doblaje.",
        duration_s=8.0,
        settings=None,
        lufs=-25.3,
        loudness_job_id="cyc-x-loudness",
    )
    assert srt
    assert meta["orchestrator_note"]["kind"] == "audio_too_quiet"

    silent, silent_meta = prepare_captions(
        existing_srt=None,
        script="",
        duration_s=8.0,
        settings=None,
        lufs=-38.0,
        loudness_job_id="cyc-x-loudness",
        has_speech=False,
    )
    assert silent is None
    assert silent_meta.get("orchestrator_note") is None
