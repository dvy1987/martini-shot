"""Spend Control policy loader (S5b / D-7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

POLICY_PATH = Path(__file__).resolve().parent / "policies.yaml"


def load_policies(path: Path | None = None) -> dict[str, Any]:
    data = yaml.safe_load((path or POLICY_PATH).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("spend policy file must be a mapping")
    return data


def station_policy(policies: dict[str, Any], station: str) -> dict[str, Any]:
    default = dict(policies.get("default") or {})
    override = dict((policies.get("stations") or {}).get(station) or {})
    return {**default, **override}


def project_budgets(policies: dict[str, Any]) -> dict[str, int]:
    raw = policies.get("project") or {}
    return {
        "hourly_budget_micros": int(raw.get("hourly_budget_micros") or 0),
        "daily_budget_micros": int(raw.get("daily_budget_micros") or 0),
    }
