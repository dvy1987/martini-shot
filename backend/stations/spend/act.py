"""Spend Control actions: pause intake, Approvals inbox, Grafana annotation+incident."""

from __future__ import annotations

import uuid
from typing import Any

from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso
from backend.stations.spend.control import pause_intake
from backend.supervisor.mcp import GrafanaMcpConnector

APPROVALS = "pc-approvals"


def open_spend_approval(
    store: FirestoreStore,
    *,
    project_id: str,
    job_id: str | None,
    title: str,
    detail: str,
    cost_delta_micros: int = 0,
) -> str:
    approval_id = f"ap-{uuid.uuid4().hex[:12]}"
    store.set_doc(
        APPROVALS,
        approval_id,
        {
            "approval_id": approval_id,
            "project_id": project_id,
            "job_id": job_id,
            "kind": "spend",
            "title": title,
            "detail": detail,
            "status": "proposed",
            "created_at": utc_now_iso(),
            "cost_delta_micros": cost_delta_micros,
        },
    )
    return approval_id


def throttle_station(
    store: FirestoreStore,
    *,
    station: str,
    project_id: str,
    job_id: str | None,
    reason: str,
    grafana: GrafanaMcpConnector | None,
    cost_delta_micros: int = 0,
) -> dict[str, Any]:
    pause_intake(store, station, reason)
    approval_id = open_spend_approval(
        store,
        project_id=project_id,
        job_id=job_id,
        title=f"Resume {station} after Spend Control hold",
        detail=reason,
        cost_delta_micros=cost_delta_micros,
    )
    grafana_out: dict[str, Any] = {}
    if grafana is not None:
        text = (
            f"spend throttle job_id={job_id or ''} project_id={project_id} "
            f"station={station} approval_id={approval_id} {reason}"
        )
        grafana_out["annotation"] = grafana.add_annotation(
            text, tags=["martini-shot", "spend", station]
        )
        grafana_out["incident"] = grafana.create_incident(
            title=f"Spend Control throttled {station}",
            severity="pending",
        )
    return {
        "action": "throttle",
        "station": station,
        "approval_id": approval_id,
        "grafana": grafana_out,
    }
