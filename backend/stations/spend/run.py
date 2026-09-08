"""Spend Control station: scan project jobs, throttle runaways and budget breaches."""

from __future__ import annotations

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.stations.spend.act import throttle_station
from backend.stations.spend.detect import (
    budget_breached,
    coerce_cost_micros,
    is_runaway,
    job_over_cap,
    project_spend_micros,
)
from backend.stations.spend.policy import load_policies, project_budgets, station_policy
from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config

STATION = "spend"


def run_spend(
    job: Job,
    store: FirestoreStore,
    settings: Settings,
    grafana: GrafanaMcpConnector | None = None,
) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            policies = load_policies()
            rows = store.list_where("pc-jobs", "project_id", job.project_id)
            connector = grafana
            owned = False
            if connector is None:
                try:
                    connector = GrafanaMcpConnector(build_server_config(settings))
                    connector.connect()
                    owned = True
                except Exception:
                    connector = None
            actions: list[dict[str, object]] = []
            try:
                for row in rows:
                    station = str(row.get("station") or "")
                    if station in {STATION, ""}:
                        continue
                    policy = station_policy(policies, station)
                    attempts = int(row.get("attempts") or 0)
                    if is_runaway(attempts, int(policy.get("runaway_requeues") or 8)):
                        actions.append(
                            throttle_station(
                                store,
                                station=station,
                                project_id=job.project_id,
                                job_id=str(row.get("id") or row.get("job_id") or ""),
                                reason=f"runaway retries attempts={attempts}",
                                grafana=connector,
                                cost_delta_micros=coerce_cost_micros(
                                    row.get("cost_micros")
                                ),
                            )
                        )
                    elif job_over_cap(
                        row.get("cost_micros"),
                        int(policy.get("max_cost_micros_per_job") or 0),
                    ):
                        actions.append(
                            throttle_station(
                                store,
                                station=station,
                                project_id=job.project_id,
                                job_id=str(row.get("id") or row.get("job_id") or ""),
                                reason="per-job cost cap",
                                grafana=connector,
                                cost_delta_micros=coerce_cost_micros(
                                    row.get("cost_micros")
                                ),
                            )
                        )
                budgets = project_budgets(policies)
                spent = project_spend_micros(rows)
                if budget_breached(spent, budgets["daily_budget_micros"]):
                    actions.append(
                        throttle_station(
                            store,
                            station="ingest",
                            project_id=job.project_id,
                            job_id=job.id,
                            reason=f"daily budget spent={spent}",
                            grafana=connector,
                            cost_delta_micros=spent,
                        )
                    )
                    _cite_spend_line(store, job, spent)
            finally:
                if owned and connector is not None:
                    connector.close()
            job.cost_micros = 0
            job.result = {"actions": actions, "jobs_scanned": len(rows)}
            if actions:
                job.status = "throttled"
                job.error = "spend_enforced"
                outcome = "throttled"
            else:
                outcome = "pass"
            log.info(
                "spend scan done",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "actions": len(actions),
                },
            )
            return job
        finally:
            record_job(
                STATION,
                duration_s=timed() - started,
                cost_micros=job.cost_micros,
                outcome=outcome,
                project_id=job.project_id,
            )


def _cite_spend_line(store: FirestoreStore, job: Job, spent: int) -> None:
    from datetime import datetime, timezone

    from backend.jobs.models import utc_now_iso

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{job.project_id}:{date}"
    existing = store.get_doc("pc-morning-reports", key) or {
        "date": date,
        "verdicts": [],
    }
    verdicts = list(existing.get("verdicts") or [])
    verdicts.append(
        {
            "station": STATION,
            "verdict": "throttled",
            "summary": f"daily spend {spent} micros — intake paused",
            "cost_micros": spent,
        }
    )
    store.set_doc(
        "pc-morning-reports",
        key,
        {**existing, "date": date, "generated_at": utc_now_iso(), "verdicts": verdicts},
    )
