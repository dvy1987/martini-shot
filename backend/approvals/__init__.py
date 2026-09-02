"""Approval→action executor (H-0, amendment A8)."""

from backend.approvals.commands import CommandRegistry, default_registry
from backend.approvals.machine import (
    APPROVALS,
    ApprovalConflict,
    ApprovalStateMachine,
    DispatchContext,
)

__all__ = [
    "APPROVALS",
    "ApprovalConflict",
    "ApprovalStateMachine",
    "CommandRegistry",
    "DispatchContext",
    "default_registry",
]
