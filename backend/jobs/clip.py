"""Operator-facing clip name, before/after refs, and metadata for a job."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from backend.core.gcs import object_key
from backend.jobs.models import Job

Side = Literal["before", "after"]


def clip_name(ref: str) -> str:
    text = (ref or "").strip()
    if not text:
        return ""
    try:
        key = object_key(text)
    except ValueError:
        key = text.replace("\\", "/")
    return Path(key).name


def resolve_clip_ref(job: Job, side: Side) -> str | None:
    before = str(job.input_refs[0]) if job.input_refs else ""
    if side == "before":
        return before or None
    artifact = str((job.result or {}).get("artifact_ref") or "")
    if artifact:
        return artifact
    if job.station == "ingest":
        return before or None
    if job_has_after_change(job):
        return before or None
    return None


def job_has_after_change(job: Job) -> bool:
    result = job.result or {}
    before = str(job.input_refs[0]) if job.input_refs else ""
    artifact = str(result.get("artifact_ref") or "")
    if artifact and artifact != before:
        return True
    return bool(clip_metadata(job))


def clip_metadata(job: Job) -> dict[str, Any]:
    return apply_watch_notes({}, job.result or {})


def apply_watch_notes(
    meta: dict[str, Any], source: dict[str, Any] | None
) -> dict[str, Any]:
    """Copy scene / spoken words into clip metadata without wiping filled fields."""
    bag = dict(source or {})
    nested = bag.get("scene_understanding")
    if isinstance(nested, dict):
        bag = {**nested, **bag}
    for key in ("spoken_words", "scene"):
        value = bag.get(key)
        if (
            isinstance(value, str)
            and value.strip()
            and not str(meta.get(key) or "").strip()
        ):
            meta[key] = value.strip()
    handoff = bag.get("handoff")
    if isinstance(handoff, dict) and isinstance(handoff.get("scene"), dict):
        apply_watch_notes(meta, handoff["scene"])
    probe = bag.get("probe")
    if isinstance(probe, dict):
        for key in ("duration_s", "fps", "codec", "has_audio", "width", "height"):
            if key in probe and key not in meta:
                meta[key] = probe[key]
    else:
        for key in ("duration_s", "fps", "codec", "has_audio", "width", "height"):
            if key in bag and key not in meta:
                meta[key] = bag[key]
    return meta


def project_watch_notes(job: Job, store: Any | None) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if store is None:
        return extra
    origin = str(job.input_refs[0]) if job.input_refs else ""
    project_id = job.project_id
    try:
        shots = store.list_where("pc-shots", "project_id", project_id)
    except Exception:
        shots = []
    for shot in shots:
        title = str(shot.get("title") or "")
        if origin and title != origin:
            continue
        nested = shot.get("scene_understanding")
        if isinstance(nested, dict):
            apply_watch_notes(extra, nested)
    try:
        rows = store.list_where("pc-jobs", "project_id", project_id)
    except Exception:
        rows = []
    for row in rows:
        refs = [str(ref) for ref in list(row.get("input_refs") or [])]
        if origin and origin not in refs:
            continue
        apply_watch_notes(extra, dict(row.get("result") or {}))
    return extra


def clip_playback_path(job_id: str, side: Side) -> str:
    return f"/api/v1/jobs/{job_id}/clip/{side}/media"


def clip_body(
    job: Job,
    side: Side,
    *,
    extra: dict[str, Any] | None = None,
    gcs: Any | None = None,
) -> dict[str, Any]:
    ref = resolve_clip_ref(job, side)
    if not ref:
        raise KeyError(side)
    metadata = clip_metadata(job)
    if extra:
        apply_watch_notes(metadata, extra)
    if gcs is not None:
        url = gcs.signed_download_url(object_key(ref), expires_minutes=60)
    else:
        url = clip_playback_path(job.id, side)
    return {
        "job_id": job.id,
        "side": side,
        "clip_name": clip_name(ref),
        "url": url,
        "expires_in_minutes": 60,
        "metadata": metadata,
    }
