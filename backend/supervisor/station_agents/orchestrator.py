"""Batch Orchestrator Agent (A10-2): plans the station chain per
episode×language manifest item with ONE metered Gemini call.

The deterministic chain is ADVICE: the agent may TRIM it (skip stations it
can justify) but never invent stations or reorder — `validate_agent_chain`
(enforced here) fails loud, and any malformed/failed response falls back to
the deterministic chain marked `decision_mode: deterministic_fallback`
(visible, never silent — A10 spec)."""

from __future__ import annotations

import json
from typing import Any, Callable

from backend.supervisor.orchestrator import validate_agent_chain

AGENT = "orchestrator"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "chain": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["ingest", "dub", "loudness", "delivery"],
            },
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "chain", "reason", "confidence"],
}


def build_planning_prompt(item: dict[str, Any], *, default_chain: list[str]) -> str:
    caption_note = _caption_loudness_note(item.get("context"))
    return (
        "You are the Batch Orchestrator agent for Martini Shot. Plan the "
        "station chain for ONE episode×language item of an approved batch "
        "manifest.\n\n"
        f"- episode: {item.get('episode_id')}\n"
        f"- language: {item.get('language')}\n"
        f"- line: {item.get('script') or '(n/a)'}\n"
        f"- batch context: {item.get('context') or '(none)'}\n"
        f"{caption_note}"
        f"{_scene_understanding_note(item.get('context'))}"
        "Station vocabulary (the ONLY stations a batch may route through, in "
        "fixed order): ingest → dub → loudness → delivery.\n"
        f"Deterministic default chain (advisory): {default_chain}\n\n"
        "Decide each station on the merits, using the batch context:\n"
        "- ingest proves + registers the source; if the context shows this "
        "source already passed ingest upstream, ingest is redundant — skip it.\n"
        "- dub renders THIS language's line; always required for a dub item.\n"
        "- loudness must always HEAR the NEW dub (not the picture "
        "soundtrack), classify the scene (whisper, talk, shout, crash, "
        "explosion — not only 'make everything TV-loud'), mix toward that "
        "level, and re-measure. A prior master's pass says nothing about "
        "this dub.\n"
        "- delivery builds the destination pack; always the last step.\n"
        "You may NOT invent stations or reorder — only trim with a stated "
        "reason. When in doubt, keep the default chain.\n\n"
        'Respond ONLY with JSON: {"agent": "orchestrator", "chain": [...], '
        '"reason": "...", "confidence": "low|medium|high"}.'
    )


def _caption_loudness_note(context: Any) -> str:
    """Captions may flag quiet speech; silence is not a mix miss."""
    if not isinstance(context, dict):
        return ""
    if context.get("audio_too_quiet") and context.get("has_speech"):
        return (
            "- captions heard spoken words that are too quiet: do not skip "
            "loudness — keep loudness in the chain so the mix can be retried.\n\n"
        )
    if context.get("has_speech") is False:
        return (
            "- captions report no spoken words. Quiet room tone is not a "
            "loudness miss — do not treat silence as a mix failure.\n\n"
        )
    return ""


def _scene_understanding_note(context: Any) -> str:
    """Original-clip watch lives on the shot; planning must see it."""
    if not isinstance(context, dict):
        return ""
    meta = context.get("scene_understanding")
    if not isinstance(meta, dict):
        return ""
    words = str(meta.get("spoken_words") or "").strip() or "(none)"
    scene = str(meta.get("scene") or "").strip() or "(none)"
    return (
        f"- scene understanding (shot metadata): spoken words: {words}; "
        f"scene: {scene}. Pass this to later stations; do not re-guess "
        "what was said.\n\n"
    )


def parse_plan(
    text: str, item: dict[str, Any], *, default_chain: list[str]
) -> tuple[list[str], dict[str, Any]]:
    """Validate the model's JSON + chain; returns (chain, doc) where doc is
    persisted for the audit trail (C-4.2)."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if str(payload.get("agent") or "") != AGENT:
        raise ValueError(f"payload agent {payload.get('agent')!r} is not {AGENT!r}")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise ValueError("reason is mandatory — no unexplained plan")
    chain = validate_agent_chain(
        list(payload.get("chain") or []), str(item.get("language"))
    )
    overridden = chain != list(default_chain)
    return chain, {
        "agent": AGENT,
        "chain": chain,
        "reason": reason,
        "confidence": str(payload.get("confidence") or "low"),
        "deterministic_advice": list(default_chain),
        "overridden": overridden,
        "decision_mode": "agent",
    }


def plan_item(
    settings: Any,
    item: dict[str, Any],
    *,
    default_chain: list[str],
    run_agent_call: Callable[..., dict[str, Any]] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """ONE metered Gemini planning call per item; validated chain out. Any
    failure (API or validation) falls back to the deterministic chain marked
    `decision_mode: deterministic_fallback` — visible, never silent (A10)."""
    from backend.supervisor.otel_ai import run_agent_call as _real

    runner = run_agent_call or _real
    try:
        response = runner(
            settings,
            build_planning_prompt(item, default_chain=default_chain),
            span_name="orchestrator.plan_item",
            persona=AGENT,
            response_schema=SCHEMA,
        )
        chain, doc = parse_plan(response["text"], item, default_chain=default_chain)
        doc["cost_micros"] = int(response["cost_micros"])
        return chain, doc
    except Exception as exc:
        return list(default_chain), {
            "agent": AGENT,
            "chain": list(default_chain),
            "reason": f"agent planning failed: {type(exc).__name__}: {str(exc)[:160]}",
            "confidence": "none",
            "deterministic_advice": list(default_chain),
            "overridden": False,
            "decision_mode": "deterministic_fallback",
        }
