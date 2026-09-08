"""Provision Run Pulse dashboards through Grafana MCP (C-2.2, C-4.5).

Grafana Cloud writes require an explicit --yes (owner rule). Dry-run
prints the UIDs that would be upserted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARDS = ROOT / "infra" / "grafana"
ALERTS = DASHBOARDS / "alerts" / "run-pulse.yaml"
FOLDER_TITLE = "Martini Shot"

DASHBOARD_FILES = (
    "station-health.json",
    "finishing-cost.json",
    "interventions.json",
)


def load_dashboards() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in DASHBOARD_FILES:
        path = DASHBOARDS / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload.get("uid") or not payload.get("title"):
            raise ValueError(f"{path} missing uid/title")
        if not payload.get("panels"):
            raise ValueError(f"{path} has no panels")
        out.append(payload)
    return out


def provision(dashboards: list[dict[str, Any]], *, yes: bool) -> dict[str, Any]:
    uids = [str(row["uid"]) for row in dashboards]
    result: dict[str, Any] = {
        "folder": FOLDER_TITLE,
        "uids": uids,
        "alerts": str(ALERTS.relative_to(ROOT)),
        "applied": False,
    }
    if not yes:
        result["note"] = "dry-run; pass --yes to write via Grafana MCP"
        return result

    from backend.core.config import get_settings
    from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config

    settings = get_settings()
    with GrafanaMcpConnector(build_server_config(settings)) as grafana:
        try:
            grafana.create_folder(title=FOLDER_TITLE)
        except Exception as exc:
            result["folder_error"] = str(exc)[:200]
        writes = []
        for dashboard in dashboards:
            writes.append(
                grafana.update_dashboard(
                    dashboard=dashboard,
                    overwrite=True,
                    message="Martini Shot Run Pulse (C-4.5)",
                )
            )
        result["writes"] = writes
        result["applied"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Write dashboards to Grafana Cloud through MCP (owner approval).",
    )
    args = parser.parse_args(argv)
    dashboards = load_dashboards()
    payload = provision(dashboards, yes=args.yes)
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
