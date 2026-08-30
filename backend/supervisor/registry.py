"""Tool registry for the supervisor agent (plan B-1).

Every supervisor capability is a registered Python function; act-class
tools are flagged so the autonomy layer can gate them. Registration is
the single source of truth for what the agent may call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from google.adk.tools import BaseTool, FunctionTool
from google.adk.tools.base_toolset import BaseToolset

ToolBinding = Callable[..., Any] | BaseTool | BaseToolset


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    act: bool
    fn: Callable[..., Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def tool(
        self, *, description: str, act: bool = False
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            name = fn.__name__
            if name in self._tools:
                raise ValueError(f"duplicate tool registration: {name}")
            self._tools[name] = RegisteredTool(
                name=name, description=description, act=act, fn=fn
            )
            return fn

        return decorator

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> RegisteredTool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def description(self, name: str) -> str:
        return self.get(name).description

    def is_act_tool(self, name: str) -> bool:
        return self.get(name).act

    def adk_tools(self, *, allow_act: bool) -> list[ToolBinding]:
        """Real ADK tool bindings for the allowed toolset."""
        tools: list[ToolBinding] = [
            FunctionTool(t.fn)
            for t in sorted(self._tools.values(), key=lambda t: t.name)
            if allow_act or not t.act
        ]
        return tools
