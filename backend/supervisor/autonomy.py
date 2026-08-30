"""Autonomy toggle (plan B-1, spec §5): propose-only by default.

ACT mode is an explicit env decision (POST_COMMAND_AUTONOMY=act). In
propose-only mode, act-class tool calls are refused at the registry
boundary and surface as proposals for human approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.supervisor.registry import ToolRegistry


class AutonomyMode(str, Enum):
    PROPOSE_ONLY = "propose_only"
    ACT = "act"


@dataclass(frozen=True)
class Autonomy:
    mode: AutonomyMode

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "Autonomy":
        raw = env.get("POST_COMMAND_AUTONOMY", "propose_only").strip().lower()
        try:
            return cls(mode=AutonomyMode(raw))
        except ValueError as exc:
            raise ValueError(
                f"POST_COMMAND_AUTONOMY must be one of "
                f"{[m.value for m in AutonomyMode]}, got {raw!r}"
            ) from exc

    def check(self, tool_name: str, registry: ToolRegistry) -> tuple[bool, str]:
        """Gate a tool call: (allowed, refusal_reason)."""
        if registry.is_act_tool(tool_name) and self.mode is not AutonomyMode.ACT:
            return False, (
                f"{tool_name} is an act-class tool; supervisor runs in "
                "propose-only mode — return a proposal for human approval instead"
            )
        return True, ""
