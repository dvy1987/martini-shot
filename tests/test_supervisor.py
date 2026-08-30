"""B-1 RED tests: supervisor scaffold — tool registry, autonomy toggle
(propose-only default), persona + agent assembly with REAL google-adk
objects (plan B-1; spec §5 supervisor; C-2.2 text model = pinned Gemini).
"""

import pytest
from google.adk.agents import LlmAgent

from backend.core.config import get_settings
from backend.core.models import TEXT_MODEL
from backend.supervisor.agent import build_supervisor
from backend.supervisor.autonomy import Autonomy, AutonomyMode
from backend.supervisor.registry import ToolRegistry


def test_registry_registers_and_lists_tools() -> None:
    registry = ToolRegistry()

    @registry.tool(description="Read a job document from Firestore")
    def read_job(job_id: str) -> dict:  # pragma: no cover - never executed here
        return {}

    names = registry.names()
    assert "read_job" in names
    assert registry.get("read_job") is not None
    assert registry.description("read_job") == "Read a job document from Firestore"


def test_registry_rejects_duplicates_and_unknown() -> None:
    registry = ToolRegistry()

    @registry.tool(description="one")
    def probe() -> dict:  # pragma: no cover
        return {}

    with pytest.raises(ValueError, match="duplicate"):
        registry.tool(description="two")(probe)
    with pytest.raises(KeyError):
        registry.get("nope")


def test_autonomy_defaults_to_propose_only() -> None:
    autonomy = Autonomy.from_env({})
    assert autonomy.mode is AutonomyMode.PROPOSE_ONLY


def test_autonomy_act_mode_requires_explicit_env() -> None:
    autonomy = Autonomy.from_env({"POST_COMMAND_AUTONOMY": "act"})
    assert autonomy.mode is AutonomyMode.ACT
    with pytest.raises(ValueError):
        Autonomy.from_env({"POST_COMMAND_AUTONOMY": "yolo"})


def test_act_tools_are_blocked_in_propose_only() -> None:
    registry = ToolRegistry()

    @registry.tool(description="retry a failed job", act=True)
    def retry_job(job_id: str) -> dict:  # pragma: no cover
        return {}

    autonomy = Autonomy.from_env({})
    assert registry.is_act_tool("retry_job") is True
    allowed, reason = autonomy.check("retry_job", registry)
    assert allowed is False
    assert "propose-only" in reason.lower()


def test_read_tools_allowed_in_propose_only() -> None:
    registry = ToolRegistry()

    @registry.tool(description="inspect job state")
    def read_job(job_id: str) -> dict:  # pragma: no cover
        return {}

    autonomy = Autonomy.from_env({})
    allowed, reason = autonomy.check("read_job", registry)
    assert allowed is True
    assert reason == ""


def test_build_supervisor_wires_persona_model_and_tools() -> None:
    settings = get_settings()
    agent = build_supervisor(settings)
    assert isinstance(agent, LlmAgent)
    assert agent.model == TEXT_MODEL
    assert "Post Supervisor" in (agent.instruction or "")
    assert agent.name == "post_supervisor"
    assert len(agent.tools) >= 1
