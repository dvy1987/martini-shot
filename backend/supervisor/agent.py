"""Supervisor agent assembly (plan B-1, spec §5, ADR-0002 model pinning).

Builds the real google-adk LlmAgent with the Post Supervisor persona,
the pinned text model, and seed tools over the real spine (Firestore).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore, get_firestore
from backend.core.models import TEXT_MODEL
from backend.supervisor.autonomy import Autonomy, AutonomyMode
from backend.supervisor.registry import ToolRegistry

PERSONA = """You are the Post Supervisor of Martini Shot, an observability-native
post-production cockpit. You watch 16 instrumented station jobs running over a
Firestore lease queue. Your job: when a job fails or drifts (budget, loudness,
handoff), read the real telemetry, diagnose the root cause from evidence, and
propose a precise fix.

Rules you never break:
- Propose, don't mutate: in propose-only mode, act-class tools (retry, stop,
  quarantine) are refused — return a proposal citing job_id and evidence.
- Every claim must cite evidence: a trace ID, a PromQL result, a log line, or
  a job document you actually read.
- Every intervention you take is annotated against job_id (audit trail).
- Cost discipline: prefer diagnosis over re-runs; never re-run a job without
  naming the failure mode you expect to clear.
"""


def _make_tools(store: FirestoreStore) -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(description="Read a job document by job_id from the lease queue")
    def read_job(job_id: str) -> dict:
        doc = store.get_doc("pc-jobs", job_id)
        return doc if doc is not None else {"error": f"job {job_id} not found"}

    @registry.tool(
        description="List recently failed jobs with station and failure reason"
    )
    def list_failed_jobs(limit: int = 10) -> list[dict]:
        rows = store.list_where("pc-jobs", "status", "==", "failed", limit=limit)
        return [
            {
                "job_id": r.get("job_id") or r.get("id"),
                "station": r.get("station"),
                "reason": r.get("failure_reason") or r.get("reason"),
            }
            for r in rows
        ]

    @registry.tool(description="Retry a failed job (act-class; propose-only blocks)")
    def retry_job(job_id: str) -> dict:
        raise NotImplementedError("wired through the lease queue in a later task")

    return registry


def build_supervisor(
    settings: Settings, *, autonomy: Autonomy | None = None
) -> LlmAgent:
    store = get_firestore(settings)
    registry = _make_tools(store)
    mode = (autonomy or Autonomy.from_env({})).mode
    return LlmAgent(
        name="post_supervisor",
        model=TEXT_MODEL,
        instruction=PERSONA,
        description="Post Supervisor: diagnoses failed station jobs from real telemetry",
        tools=registry.adk_tools(allow_act=mode is AutonomyMode.ACT),
    )
