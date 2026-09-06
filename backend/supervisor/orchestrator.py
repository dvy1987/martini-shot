"""Batch Orchestrator (A10, E-3): plans the station chain per episode×language
manifest item, estimates cost BEFORE any billable run (C-7.2), and submits
jobs through the real Firestore lease queue with deterministic, idempotent
job ids (C-6.3).

Bounded by construction (spec): only manifest items, only the real plannable
station vocabulary, fixed chain order. The orchestrator AGENT may trim the
deterministic chain (advice under advisement, owner ruling) but never invents
stations or reorders — `validate_agent_chain` fails loud, and the caller
falls back to the deterministic plan marked `decision_mode:
deterministic_fallback` (visible, never silent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.jobs.models import Job

# The stations a batch plan may route through — the REAL runnable handlers
# (backend/stations/<name>/run.py). Spend is a control station, not a chain
# step; extend/pickups are shot-level ops outside the episode×language batch.
BATCH_STATIONS: tuple[str, ...] = ("ingest", "dub", "loudness", "delivery")

# Order ordinal per station — the agent's chain must preserve this order.
_ORDER = {station: i for i, station in enumerate(BATCH_STATIONS)}

# Cost model (C-6.4 integer micros). TTS: Chirp 3 HD list $30/1M chars.
# Dub QC agent: measured flash-tier cost ~2,500 micros per judgment (E-2
# eval actuals). Ingest/loudness/delivery: deterministic stations, ~0.
TTS_MICROS_PER_CHAR = 30
AGENT_JUDGMENT_MICROS = 2_500


def load_manifest(path: Path) -> list[dict[str, Any]]:
    """Load and validate an APPROVED batch manifest; expand to one planning
    item per (episode, language). Fail loud on anything malformed — a batch
    must never run on a half-parsed manifest."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest.get("approved"):
        raise ValueError("batch manifest is not approved — refuse to plan (C-7.2)")
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("batch manifest has no items")
    batch_id = str(manifest.get("batch_id") or "")
    if not batch_id:
        raise ValueError("batch manifest requires batch_id")
    expanded: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        episode_id = str(item.get("episode_id") or "")
        source_ref = str(item.get("source_ref") or "")
        shot_id = str(item.get("shot_id") or "")
        languages = item.get("languages") or []
        scripts = item.get("scripts") or {}
        if not episode_id or not source_ref or not shot_id or not languages:
            raise ValueError(
                "manifest item malformed: episode_id/source_ref/shot_id/"
                "languages required"
            )
        for language in languages:
            key = (episode_id, str(language))
            if key in seen:
                raise ValueError(f"duplicate manifest item: {key}")
            seen.add(key)
            expanded.append(
                {
                    "batch_id": batch_id,
                    "episode_id": episode_id,
                    "source_ref": source_ref,
                    "shot_id": shot_id,
                    "language": str(language),
                    "script": str(scripts.get(str(language)) or ""),
                }
            )
    return expanded


def plan_chain(item: dict[str, Any]) -> list[str]:
    """Deterministic default chain for one item×language: ingest the source,
    dub it, loudness-QC the result, build the delivery pack. The ADVICE the
    orchestrator agent plans against."""
    del item  # the default chain is uniform per item×language today
    return list(BATCH_STATIONS)


def validate_agent_chain(chain: list[str], _language: str) -> list[str]:
    """The agent's chain must be a SUBSEQUENCE of the deterministic chain —
    same vocabulary, same relative order, non-empty. Fail loud otherwise."""
    if not chain:
        raise ValueError("agent chain is empty")
    if any(station not in BATCH_STATIONS for station in chain):
        raise ValueError(f"agent chain leaves the station vocabulary: {chain}")
    ordinals = [_ORDER[station] for station in chain]
    if ordinals != sorted(ordinals) or len(set(ordinals)) != len(ordinals):
        raise ValueError(f"agent chain breaks the fixed station order: {chain}")
    return list(chain)


def batch_job_id(batch_id: str, episode_id: str, language: str, station: str) -> str:
    """Deterministic job id — resubmitting the same plan item is a no-op at
    the queue (C-6.3 idempotency)."""
    return f"cyc-{batch_id}-{episode_id}-{language}-{station}"


def estimate_batch_cost(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Dry-run cost estimate for the whole batch — printed BEFORE any
    billable run (C-7.2). Accepts the RAW manifest items (episode×language
    not yet expanded). Real rate card, integer micros (C-6.4)."""
    jobs = 0
    total = 0
    for item in items:
        for language in item.get("languages") or []:
            jobs += 1
            chars = len(str((item.get("scripts") or {}).get(str(language)) or ""))
            total += chars * TTS_MICROS_PER_CHAR + AGENT_JUDGMENT_MICROS
    return {
        "jobs": jobs,
        "total_micros": total,
        "per_job_micros": int(total / jobs) if jobs else 0,
        "total_usd": round(total / 1_000_000, 2),
    }


def build_batch_jobs(items: list[dict[str, Any]]) -> list["Job"]:
    """One Job per (item, chain station) with DETERMINISTIC ids — resubmitting
    the same plan is a no-op at the queue (C-6.3). The dub job carries the
    station's full contract (ssml/shot_id/language) in result; every job
    carries the batch context for the audit trail (C-4.2)."""
    from backend.jobs.models import Job

    jobs: list[Job] = []
    for item in items:
        chain = plan_chain(item)
        context = {
            "batch_id": item["batch_id"],
            "episode_id": item["episode_id"],
            "language": item["language"],
            "script": item["script"],
            "shot_id": item["shot_id"],
        }
        for station in chain:
            result = dict(context)
            if station == "dub":
                result["ssml"] = f"<speak>{item['script']}</speak>"
            jobs.append(
                Job(
                    station=station,
                    project_id=str(item.get("project_id") or "batch"),
                    input_refs=[item["source_ref"]],
                    id=batch_job_id(
                        item["batch_id"],
                        item["episode_id"],
                        item["language"],
                        station,
                    ),
                    result=result,
                )
            )
    return jobs


def submit_batch(queue: Any, jobs: list[Any]) -> None:
    """Submit all batch jobs. Idempotent per deterministic job id (C-6.3):
    the queue swallows already-exists; a duplicate submission is a no-op."""
    for job in jobs:
        queue.submit(job)
