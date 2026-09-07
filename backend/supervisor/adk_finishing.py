"""Google ADK finishing team: ParallelAgent of station LlmAgents, then boss.

The Runner is actually invoked. Station tools call the billed inspect look.
Global ranking is a separate billed orchestrator call over the complete bag.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from backend.core.models import TEXT_MODEL
from backend.supervisor.inspect import ROSTER, InspectNote, attendance_rows
from backend.supervisor.inspect_impl import run_inspect, station_inspect_prompt

log = logging.getLogger("pc.finishing.adk")

APP_NAME = "martini-shot-finishing"
ORCHESTRATOR_NAME = "finishing_orchestrator"

ORCHESTRATOR_PERSONA = """You are the finishing orchestrator for Martini Shot.
You have taste. Specialists already looked. You weigh tradeoffs and name
dependencies (mix before extending the same scene; one generative picture
edit per shot at a time; independent clips may run together).

Hard rails you never break:
- empty notes are attendance holes, never work.
- you cannot invent a station, a cost, or a command.
- spend never becomes a picture job.

Return JSON: {"order": ["loudness::shot-a", ...], "dependencies": [{"before": "...", "after": "...", "reason": "..."}], "drop": [{"id": "...", "reason": "..."}], "reason": "..."}
"""


def _station_tool(
    station: str,
    settings: Any,
    context: dict[str, Any],
    preview_cache: Any | None = None,
) -> FunctionTool:
    def look(clip_uri: str = "") -> str:
        ctx = dict(context)
        if clip_uri:
            ctx["clip_uri"] = clip_uri
        note = run_inspect(
            station,
            settings=settings,
            context=ctx,
            preview_cache=preview_cache,
        )
        return json.dumps(note.to_doc())

    look.__name__ = f"look_{station}"
    look.__doc__ = (
        f"Billed look at the source clip for the {station} station. "
        "Returns inspect JSON (defects and quality)."
    )
    return FunctionTool(look)


def build_station_agent(
    station: str,
    settings: Any,
    context: dict[str, Any],
    preview_cache: Any | None = None,
) -> LlmAgent:
    return LlmAgent(
        name=f"finish_{station}",
        model=TEXT_MODEL,
        instruction=(
            station_inspect_prompt(station, context)
            + f"\nCall look_{station} and return that JSON unchanged "
            "unless you genuinely improve impact/kind with taste. "
            "The tool watches extracted frames and audio from the clip."
        ),
        description=f"Finishing inspect agent for {station}",
        tools=[_station_tool(station, settings, context, preview_cache)],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


def build_finishing_team(
    settings: Any,
    context: dict[str, Any] | None = None,
    preview_cache: Any | None = None,
) -> SequentialAgent:
    context = dict(context or {})
    cache = preview_cache
    if cache is None and settings is not None:
        from backend.supervisor.clip_preview import ClipPreviewCache

        cache = ClipPreviewCache(settings)
    parallel = ParallelAgent(
        name="finishing_attendance",
        sub_agents=[
            build_station_agent(station, settings, context, cache) for station in ROSTER
        ],
    )
    boss = LlmAgent(
        name=ORCHESTRATOR_NAME,
        model=TEXT_MODEL,
        instruction=ORCHESTRATOR_PERSONA,
        description="Ranks finishing inspect notes by scene impact",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
    return SequentialAgent(
        name="finishing_root",
        sub_agents=[parallel, boss],
    )


def _event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    chunks: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(str(text))
    return "\n".join(chunks)


def notes_from_events(events: list[Any]) -> list[InspectNote]:
    found: dict[str, InspectNote] = {}
    for event in events:
        text = _event_text(event)
        if not text or "{" not in text:
            continue
        stripped = text.strip()
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            continue
        station = str(payload.get("station") or "")
        if station not in ROSTER:
            continue
        try:
            from backend.supervisor.inspect import validate_inspect_note

            found[station] = validate_inspect_note(payload)
        except Exception:
            log.exception("ADK inspect JSON failed station=%s", station)
    return attendance_rows(list(found.values()))


async def run_finishing_runner(
    settings: Any,
    context: dict[str, Any],
    *,
    session_service: InMemorySessionService | None = None,
    preview_cache: Any | None = None,
) -> tuple[list[InspectNote], str]:
    """Actually invoke google.adk.runners.Runner. Returns notes + last text."""
    team = build_finishing_team(settings, context, preview_cache=preview_cache)
    sessions = session_service or InMemorySessionService()
    session = await sessions.create_session(
        app_name=APP_NAME,
        user_id="finishing",
        session_id=f"fin-{uuid.uuid4().hex[:12]}",
        state={"context": context},
    )
    runner = Runner(app_name=APP_NAME, agent=team, session_service=sessions)
    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=(
                    "Take attendance of every station on this clip. "
                    "Each specialist must look. Then the orchestrator ranks.\n"
                    + json.dumps(context, default=str)
                )
            )
        ],
    )
    events: list[Any] = []
    last = ""
    async for event in runner.run_async(
        user_id="finishing",
        session_id=session.id,
        new_message=message,
    ):
        events.append(event)
        text = _event_text(event)
        if text:
            last = text
    return notes_from_events(events), last


def run_finishing_runner_sync(
    settings: Any,
    context: dict[str, Any],
    preview_cache: Any | None = None,
) -> tuple[list[InspectNote], str]:
    """Invoke Runner from sync worker/HTTP threads without nested-loop crashes."""

    async def _go() -> tuple[list[InspectNote], str]:
        return await run_finishing_runner(
            settings, context, preview_cache=preview_cache
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_go())

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _go()).result()


def apply_orchestrator_keep(
    notes: list[InspectNote], keep: list[str]
) -> list[InspectNote]:
    """Legacy keep-list → plan. Invented names are ignored."""
    from backend.supervisor.rank import apply_orchestrator_plan, note_key

    order = []
    by_station: dict[str, list[InspectNote]] = {}
    for note in notes:
        if note.status == "needs_work" and note.proposal:
            by_station.setdefault(note.station, []).append(note)
    for station in keep:
        for note in by_station.get(station, []):
            order.append(note_key(note))
    return apply_orchestrator_plan(notes, {"order": order, "reason": "keep"}).ordered
