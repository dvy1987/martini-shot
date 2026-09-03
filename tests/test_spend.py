"""D-7 Spend Control detectors and act-class Grafana writes (AC-S5b.1/.2)."""

from backend.stations.spend.act import throttle_station
from backend.stations.spend.detect import (
    budget_breached,
    is_runaway,
    project_spend_micros,
)
from backend.stations.spend.policy import load_policies, station_policy
from backend.supervisor.mcp import GrafanaMcpConnector
from tests.test_supervisor_mcp import RecordingSession


class _Store:
    def __init__(self) -> None:
        self.docs: dict[tuple[str, str], dict] = {}

    def get_doc(self, collection: str, doc_id: str) -> dict | None:
        return self.docs.get((collection, doc_id))

    def set_doc(self, collection: str, doc_id: str, data: dict) -> None:
        self.docs[(collection, doc_id)] = dict(data)

    def list_where(self, collection: str, field: str, value: object) -> list[dict]:
        out = []
        for (col, _id), data in self.docs.items():
            if col == collection and data.get(field) == value:
                out.append({"id": _id, **data})
        return out

    def transactional_update(self, collection: str, doc_id: str, mutate) -> None:
        # In-memory double: single-threaded unit tests, so read-apply-write is
        # equivalent; the real transactional guarantee is covered against real
        # Firestore by tests/test_approval_executor.py.
        doc = self.get_doc(collection, doc_id) or {}
        self.set_doc(collection, doc_id, mutate(doc))


def test_runaway_40_requeues_trips_policy() -> None:
    policies = load_policies()
    n = int(station_policy(policies, "pickups")["runaway_requeues"])
    assert is_runaway(40, n) is True
    assert is_runaway(n - 1, n) is False


def test_daily_budget_breach() -> None:
    jobs = [
        {"cost_micros": 200, "updated_at": "2026-09-01T10:00:00Z"},
        {"cost_micros": 400, "updated_at": "2026-09-01T11:00:00Z"},
    ]
    from datetime import datetime, timezone

    spent = project_spend_micros(
        jobs, now=datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    )
    assert spent == 600
    assert budget_breached(spent, 500) is True
    assert budget_breached(spent, 600) is True
    assert budget_breached(spent, 601) is False


def test_throttle_writes_approval_and_grafana() -> None:
    store = _Store()
    session = RecordingSession(
        ["create_annotation", "create_incident", "list_datasources"]
    )
    connector = GrafanaMcpConnector._for_session(session)
    result = throttle_station(
        store,  # type: ignore[arg-type]
        station="pickups",
        project_id="g2",
        job_id="job-runaway",
        reason="runaway retries attempts=40",
        grafana=connector,
        cost_delta_micros=12,
    )
    assert result["action"] == "throttle"
    approval = store.get_doc("pc-approvals", result["approval_id"])
    assert approval is not None
    assert approval["kind"] == "spend"
    assert approval["status"] == "proposed"
    intake = store.get_doc("pc-control", "intake")
    assert intake is not None and "pickups" in intake["paused_stations"]
    names = [name for name, _ in session.calls]
    assert "create_annotation" in names or "add_annotation" in names
    assert "create_incident" in names


def test_throttle_survives_grafana_outage() -> None:
    """Commit-first, emit-after (pre-mortem): a Grafana outage must never
    fail the protective action — the hold and the approval are committed,
    the observability writes are best-effort."""
    store = _Store()
    session = RecordingSession(
        ["create_annotation", "create_incident", "list_datasources"]
    )
    original_call = session.call_tool

    async def exploding(name: str, args: dict) -> dict:
        if name in {"create_annotation", "add_annotation", "create_incident"}:
            raise RuntimeError("grafana unavailable")
        return await original_call(name, args)

    session.call_tool = exploding  # type: ignore[method-assign]
    connector = GrafanaMcpConnector._for_session(session)
    result = throttle_station(
        store,  # type: ignore[arg-type]
        station="pickups",
        project_id="g2-outage",
        job_id="job-outage",
        reason="runaway retries attempts=40",
        grafana=connector,
        cost_delta_micros=12,
    )
    assert result["action"] == "throttle"
    approval = store.get_doc("pc-approvals", result["approval_id"])
    assert approval is not None and approval["status"] == "proposed"
    intake = store.get_doc("pc-control", "intake")
    assert intake is not None and "pickups" in intake["paused_stations"]
    assert result["grafana"].get("error"), "the outage must be recorded, not hidden"


def test_run_spend_throttles_seeded_40x_runaway() -> None:
    from backend.core.config import Settings
    from backend.jobs.models import Job
    from backend.stations.spend.run import run_spend

    store = _Store()
    store.set_doc(
        "pc-jobs",
        "job-runaway",
        {
            "id": "job-runaway",
            "station": "pickups",
            "project_id": "g2",
            "attempts": 40,
            "cost_micros": 9,
        },
    )
    session = RecordingSession(
        ["create_annotation", "create_incident", "list_datasources"]
    )
    connector = GrafanaMcpConnector._for_session(session)
    job = Job(station="spend", project_id="g2", input_refs=[])
    result = run_spend(job, store, Settings(), grafana=connector)  # type: ignore[arg-type]
    assert result.status == "throttled"
    assert result.result["actions"]
    intake = store.get_doc("pc-control", "intake")
    assert intake is not None and "pickups" in intake["paused_stations"]


def test_run_spend_over_cap_and_daily_budget() -> None:
    from datetime import datetime, timezone

    from backend.core.config import Settings
    from backend.jobs.models import Job, utc_now_iso
    from backend.stations.spend.run import run_spend

    store = _Store()
    store.set_doc(
        "pc-jobs",
        "job-hot",
        {
            "id": "job-hot",
            "station": "pickups",
            "project_id": "g2b",
            "attempts": 1,
            "cost_micros": 25_000_000,
            "updated_at": utc_now_iso(),
        },
    )
    session = RecordingSession(
        ["create_annotation", "create_incident", "list_datasources"]
    )
    connector = GrafanaMcpConnector._for_session(session)
    job = Job(station="spend", project_id="g2b", input_refs=[])
    result = run_spend(job, store, Settings(), grafana=connector)  # type: ignore[arg-type]
    assert result.status == "throttled"

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    store.set_doc(
        "pc-jobs",
        "job-budget",
        {
            "id": "job-budget",
            "station": "spend",
            "project_id": "g2c",
            "attempts": 1,
            "cost_micros": 600_000_000,
            "updated_at": utc_now_iso(),
        },
    )
    store.set_doc(
        "pc-morning-reports",
        f"g2c:{date}",
        {"date": date, "verdicts": [{"station": "ingest"}]},
    )
    daily = Job(station="spend", project_id="g2c", input_refs=[])
    daily_result = run_spend(daily, store, Settings(), grafana=connector)  # type: ignore[arg-type]
    assert daily_result.status == "throttled"
    report = store.get_doc("pc-morning-reports", f"g2c:{date}")
    assert report is not None
    assert any(v.get("station") == "spend" for v in report["verdicts"])


def test_run_spend_pass_and_skip_blank_station() -> None:
    from backend.core.config import Settings
    from backend.jobs.models import Job, utc_now_iso
    from backend.stations.spend.run import run_spend

    store = _Store()
    store.set_doc(
        "pc-jobs",
        "job-ok",
        {
            "id": "job-ok",
            "station": "loudness",
            "project_id": "g2d",
            "attempts": 1,
            "cost_micros": 12,
            "updated_at": utc_now_iso(),
        },
    )
    store.set_doc(
        "pc-jobs",
        "job-blank",
        {
            "id": "job-blank",
            "station": "",
            "project_id": "g2d",
            "attempts": 0,
            "cost_micros": 0,
            "updated_at": utc_now_iso(),
        },
    )
    session = RecordingSession(
        ["create_annotation", "create_incident", "list_datasources"]
    )
    connector = GrafanaMcpConnector._for_session(session)
    job = Job(station="spend", project_id="g2d", input_refs=[])
    result = run_spend(job, store, Settings(), grafana=connector)  # type: ignore[arg-type]
    assert result.status != "throttled"
    assert result.result["jobs_scanned"] == 2


def test_run_spend_survives_missing_grafana_binary() -> None:
    from backend.core.config import Settings
    from backend.jobs.models import Job
    from backend.stations.spend.run import run_spend

    store = _Store()
    store.set_doc(
        "pc-jobs",
        "job-runaway",
        {
            "id": "job-runaway",
            "station": "pickups",
            "project_id": "g2e",
            "attempts": 40,
            "cost_micros": 9,
        },
    )
    settings = Settings(mcp_mode="oss", mcp_grafana_bin="C:\\missing-mcp-grafana.exe")
    job = Job(station="spend", project_id="g2e", input_refs=[])
    result = run_spend(job, store, settings, grafana=None)  # type: ignore[arg-type]
    assert result.status == "throttled"
    intake = store.get_doc("pc-control", "intake")
    assert intake is not None and "pickups" in intake["paused_stations"]


def test_pause_all_and_resume() -> None:
    from backend.stations.spend.control import (
        is_intake_paused,
        pause_intake,
        resume_intake,
    )

    store = _Store()
    store.set_doc("pc-control", "intake", {"paused_all": True})
    assert is_intake_paused(store, "ingest") is True  # type: ignore[arg-type]
    pause_intake(store, "loudness", "test")  # type: ignore[arg-type]
    resume_intake(store, "loudness")  # type: ignore[arg-type]
    assert is_intake_paused(store, "loudness") is True  # type: ignore[arg-type]
    store.set_doc("pc-control", "intake", {"paused_stations": ["loudness"]})
    resume_intake(store, "loudness")  # type: ignore[arg-type]
    assert is_intake_paused(store, "loudness") is False  # type: ignore[arg-type]


def test_retries_exhausted() -> None:
    from backend.stations.spend.detect import retries_exhausted

    assert retries_exhausted(3, 2) is True
    assert retries_exhausted(2, 2) is False
