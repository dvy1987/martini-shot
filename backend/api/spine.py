"""Spine HTTP: projects, jobs, ingest upload, SSE (spec §7, gate G1)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.events import EventHub
from backend.api.present import approval_to_api, job_to_api, project_to_api
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.jobs.models import Job, utc_now_iso
from backend.jobs.queue import FirestoreLeaseQueue
from backend.stations.ingest.run import STATION

log = logging.getLogger("pc.api")
PROJECTS = "pc-projects"
APPROVALS = "pc-approvals"
REPORTS = "pc-morning-reports"


class DecisionIn(BaseModel):
    decision: str
    reason: str | None = Field(default=None)


def install_spine_routes(
    app: FastAPI,
    *,
    queue: FirestoreLeaseQueue,
    store: FirestoreStore,
    gcs: GCSMedia,
    hub: EventHub,
) -> None:
    @app.get("/api/v1/projects")
    def list_projects() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for snap in store.client.collection(PROJECTS).stream():
            doc = snap.to_dict() or {}
            project_id = doc.get("project_id") or snap.id
            jobs = queue.list_for_project(project_id)
            out.append(
                project_to_api(
                    project_id=project_id,
                    title=str(doc.get("title") or project_id),
                    created_at=str(doc.get("created_at") or utc_now_iso()),
                    jobs=jobs,
                )
            )
        out.sort(key=lambda row: str(row.get("created_at") or ""))
        return out

    @app.get("/api/v1/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        doc = store.get_doc(PROJECTS, project_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no such project")
        jobs = queue.list_for_project(project_id)
        return project_to_api(
            project_id=project_id,
            title=str(doc.get("title") or project_id),
            created_at=str(doc.get("created_at") or utc_now_iso()),
            jobs=jobs,
        )

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = queue.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such job")
        return job_to_api(job)

    @app.post("/api/v1/projects/{project_id}/ingest")
    async def ingest_clip(
        project_id: str, file: Annotated[UploadFile, File()]
    ) -> dict[str, Any]:
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="file name required",
            )
        payload = await file.read()
        if not payload:
            raise HTTPException(
                status_code=400,
                detail="empty file",
            )
        job = Job(station=STATION, project_id=project_id, input_refs=[])
        key = f"projects/{project_id}/ingest/{job.id}/{file.filename}"
        gcs.upload_bytes(key, payload, content_type=file.content_type or "video/mp4")
        job.input_refs = [key]
        if store.get_doc(PROJECTS, project_id) is None:
            store.set_doc(
                PROJECTS,
                project_id,
                {
                    "project_id": project_id,
                    "title": "Gate G1" if project_id == "g1" else project_id,
                    "created_at": utc_now_iso(),
                },
            )
        queue.submit(job)
        hub.publish(project_id, "job.updated", {"job": job_to_api(job)})
        log.info(
            "ingest accepted",
            extra={
                "job_id": job.id,
                "station": STATION,
                "project_id": project_id,
            },
        )
        return job_to_api(job)

    @app.get("/api/v1/approvals")
    def list_approvals() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for snap in store.client.collection(APPROVALS).stream():
            doc = snap.to_dict() or {}
            if not doc.get("approval_id"):
                doc["approval_id"] = snap.id
            rows.append(approval_to_api(doc))
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
        return rows

    @app.post("/api/v1/approvals/{approval_id}/decision")
    def decide_approval(approval_id: str, body: DecisionIn) -> dict[str, Any]:
        if body.decision not in {"approve", "reject"}:
            raise HTTPException(
                status_code=400, detail="decision must be approve or reject"
            )
        doc = store.get_doc(APPROVALS, approval_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no such approval")
        if str(doc.get("status") or "") != "proposed":
            raise HTTPException(status_code=409, detail="approval is not proposed")
        next_status = "approved" if body.decision == "approve" else "rejected"
        store.set_doc(
            APPROVALS,
            approval_id,
            {
                **doc,
                "approval_id": approval_id,
                "status": next_status,
                "decision_reason": body.reason,
            },
        )
        merged = {**doc, "approval_id": approval_id, "status": next_status}
        return approval_to_api(merged)

    @app.get("/api/v1/projects/{project_id}/reports/morning")
    def morning_report(project_id: str, date: str) -> dict[str, Any]:
        doc = store.get_doc(REPORTS, f"{project_id}:{date}")
        if doc is None:
            raise HTTPException(status_code=404, detail="no morning report")
        return {
            "date": str(doc.get("date") or date),
            "generated_at": str(doc.get("generated_at") or utc_now_iso()),
            "verdicts": list(doc.get("verdicts") or []),
        }

    @app.get("/api/v1/projects/{project_id}/events")
    async def project_events(project_id: str, request: Request) -> StreamingResponse:
        subscriber = hub.subscribe(project_id)

        async def gen() -> Any:
            try:
                yield ": ping\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(subscriber.get(), timeout=30)
                    except TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                hub.unsubscribe(project_id, subscriber)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
