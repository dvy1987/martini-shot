"""Order-safety helpers (H-0 peer-review hardening).

Shared by the sweeper (pre-check before a redrive) and the command handlers
(execution-time re-check that closes the check-then-act window). Lives in its
own module so machine.py and commands.py can both import it without a cycle.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("pc.approvals.orders")

# Commands that target a shared mutable resource the order-safety guard
# understands today (intake pause flags per station). New target types
# extend this set alongside their handlers.
TARGETED_COMMANDS = {"pause_intake", "resume_intake"}


class SupersededError(RuntimeError):
    """Order-safety at execution time: a newer decision already touched the
    same target — this (stale) action must not replay over it."""


def newer_decision_exists(store: Any, collection: str, doc: dict[str, Any]) -> bool:
    """True when a NEWER decision already touched the same target. Fail-closed:
    if freshness cannot be proven (query error), the caller must not act."""
    command = doc.get("command") or {}
    if command.get("name") not in TARGETED_COMMANDS:
        return False
    station = (command.get("args") or {}).get("station")
    if station is None:
        return False
    mine = str(doc.get("decided_at") or "")
    try:
        rows = store.list_where(collection, "project_id", doc.get("project_id"))
    except Exception:
        log.exception("freshness check failed; refusing to act")
        return True  # fail-closed: can't prove freshness -> don't act
    for row in rows:
        if row.get("approval_id") == doc.get("approval_id"):
            continue
        other = row.get("command") or {}
        if other.get("name") not in TARGETED_COMMANDS:
            continue
        if (other.get("args") or {}).get("station") != station:
            continue
        if row.get("status") == "proposed":
            continue
        if str(row.get("decided_at") or "") > mine:
            return True
    return False
