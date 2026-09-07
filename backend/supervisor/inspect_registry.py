"""Roster → inspect callable. Missing callable = listed empty, never fake ok."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.stations.run import STATION_NAMES
from backend.supervisor.inspect import ROSTER, InspectNote, empty_note

Inspector = Callable[..., InspectNote]

# Importing STATION_NAMES keeps roster == worker dispatch. Do not drift.
assert ROSTER == STATION_NAMES

_INSPECTORS: dict[str, Inspector] = {}


def register_inspector(station: str, fn: Inspector) -> None:
    if station not in ROSTER:
        raise ValueError(f"cannot register unknown station {station!r}")
    _INSPECTORS[station] = fn


def inspector_for(station: str) -> Inspector | None:
    if station not in ROSTER:
        return None
    _ensure_defaults()
    return _INSPECTORS.get(station)


def inspect_station(station: str, **kwargs: Any) -> InspectNote:
    fn = inspector_for(station)
    if fn is None:
        return empty_note(station)
    return fn(**kwargs)


def _ensure_defaults() -> None:
    if _INSPECTORS:
        return
    from backend.supervisor import inspect_impl

    inspect_impl.register_all(register_inspector)
