"""Prepare delivery captions: write missing ones, edit broken ones.

The D-3 rule engine remains the arbiter. Gemini may write (no script) or
edit (broken SRT); anything that still violates after re-validation does
not ship.
"""

from __future__ import annotations

from typing import Any

from backend.stations.delivery.captions import (
    GAP_MIN_S,
    MAX_CPS,
    MAX_LINE_CHARS,
    MIN_DURATION_S,
    Cue,
    parse_captions,
    validate_cues,
)
from backend.supervisor.station_agents.caption_remediation import render_srt


def wrap_to_lines(text: str, max_chars: int = MAX_LINE_CHARS) -> list[str]:
    """Word-wrap to the caption line-length cap. Does not invent words."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    buf: list[str] = []
    for word in words:
        if len(word) > max_chars:
            if buf:
                lines.append(" ".join(buf))
                buf = []
            for i in range(0, len(word), max_chars):
                lines.append(word[i : i + max_chars])
            continue
        trial = " ".join(buf + [word])
        if buf and len(trial) > max_chars:
            lines.append(" ".join(buf))
            buf = [word]
        else:
            buf.append(word)
    if buf:
        lines.append(" ".join(buf))
    return lines


def write_cues_from_script(script: str, duration_s: float) -> list[Cue]:
    """Deterministic caption writer: the script is the caption text."""
    text = " ".join(script.split())
    if not text:
        return []
    lines = wrap_to_lines(text)
    groups: list[tuple[str, ...]] = []
    for i in range(0, len(lines), 2):
        groups.append(tuple(lines[i : i + 2]))
    n = len(groups)
    # A hair over the 2-frame floor so float rounding cannot fail CAP-004.
    gap = GAP_MIN_S + 0.001 if n > 1 else 0.0
    required = [max(MIN_DURATION_S, len(" ".join(group)) / MAX_CPS) for group in groups]
    total_req = sum(required) + gap * max(0, n - 1)
    window = duration_s if duration_s > 0 else total_req
    extra = max(0.0, window - total_req)
    extra_each = extra / n if n else 0.0
    cues: list[Cue] = []
    t = 0.0
    for i, group in enumerate(groups):
        dur = required[i] + extra_each
        cues.append(Cue(start_s=t, end_s=t + dur, lines=group))
        t = t + dur
        if i < n - 1:
            t += gap
    return cues


def _cue_rows(cues: list[Cue]) -> list[dict[str, Any]]:
    return [
        {"start_s": c.start_s, "end_s": c.end_s, "lines": list(c.lines)} for c in cues
    ]


def _violation_rows(violations: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": v.rule_id,
            "message": v.message,
            "cue_index": v.cue_index,
        }
        for v in violations
    ]


def prepare_captions(
    *,
    existing_srt: str | None,
    script: str,
    duration_s: float,
    settings: Any | None,
    audio: tuple[bytes, str] | None = None,
    lufs: float | None = None,
    loudness_job_id: str | None = None,
    has_speech: bool | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Return (srt_text or None, meta with source + cost_micros).

    Quiet *speech* stamps an orchestrator_note so loudness can retry.
    A scene with no spoken words does not — room tone is not a mix miss.
    """
    speech = bool(script.strip()) if has_speech is None else bool(has_speech)
    note: dict[str, Any] | None = None
    if lufs is not None and loudness_job_id:
        from backend.supervisor.station_agents.caption_write import (
            quiet_audio_orchestrator_note,
        )

        note = quiet_audio_orchestrator_note(
            float(lufs),
            loudness_job_id=str(loudness_job_id),
            has_speech=speech,
        )

    def _meta(base: dict[str, Any]) -> dict[str, Any]:
        if note is not None:
            return {**base, "orchestrator_note": note}
        return base

    cost = 0
    if existing_srt and existing_srt.strip():
        cues, extra = parse_captions(existing_srt, "captions.srt")
        violations = extra + validate_cues(cues)
        if not violations:
            return existing_srt, _meta({"source": "existing", "cost_micros": 0})
        if settings is not None:
            from backend.supervisor.station_agents import (
                caption_remediation as editor,
            )

            decision, cost = editor.decide_caption_remediation(
                settings,
                cues=_cue_rows(cues),
                violations=_violation_rows(violations),
            )
            if decision.decision == "apply_fixes":
                fixed, residual = editor.revalidate_fixed_cues(decision.raw)
                if not residual:
                    return editor.render_srt(fixed), _meta(
                        {
                            "source": "editor",
                            "cost_micros": cost,
                        }
                    )

    if script.strip():
        written = write_cues_from_script(script, duration_s)
        if written and not validate_cues(written):
            return render_srt(written), _meta({"source": "writer", "cost_micros": cost})

    if settings is not None and audio is not None:
        from backend.supervisor.station_agents import caption_write as writer

        decision, wcost = writer.decide_caption_write(
            settings,
            script=script,
            duration_s=duration_s,
            audio=audio,
        )
        cost += wcost
        if decision.decision == "write":
            cues, residual = writer.revalidate_written_cues(decision.raw)
            if cues and not residual:
                return render_srt(cues), _meta(
                    {
                        "source": "listen_writer",
                        "cost_micros": cost,
                    }
                )

    return None, _meta({"source": "missing", "cost_micros": cost})
