"""Batch Orchestrator (A10/E-3): plans the station chain per episode×language
manifest item, estimates cost BEFORE any billable run, and submits jobs
through the real lease queue with deterministic (idempotent) job ids.

TDD: the deterministic surface (validation, planning, cost estimate, id
composition) is tested here; the real agent plan + Firestore submission are
exercised by the EDD eval and integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.supervisor.orchestrator import (
    BATCH_STATIONS,
    batch_job_id,
    build_batch_jobs,
    estimate_batch_cost,
    load_manifest,
    plan_chain,
    submit_batch,
    validate_agent_chain,
)

MANIFEST = {
    "batch_id": "batch-demo-01",
    "approved": True,
    "items": [
        {
            "episode_id": "ep-01",
            "source_ref": "fixtures/batch-demo/ep-01-source.wav",
            "shot_id": "shot-ep-01",
            "languages": ["es-ES", "fr-FR"],
            "scripts": {
                "es-ES": "Bienvenido a Martini Shot.",
                "fr-FR": "Bienvenue dans Martini Shot.",
            },
        },
        {
            "episode_id": "ep-02",
            "source_ref": "fixtures/batch-demo/ep-02-source.wav",
            "shot_id": "shot-ep-02",
            "languages": ["de-DE"],
            "scripts": {"de-DE": "Willkommen bei Martini Shot."},
        },
    ],
}


def _write_manifest(tmp_path: Path, manifest) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


def test_vocabulary_is_the_real_runnable_stations():
    assert set(BATCH_STATIONS) == {"ingest", "dub", "loudness", "delivery"}


def test_load_manifest_accepts_approved_manifest(tmp_path):
    items = load_manifest(_write_manifest(tmp_path, MANIFEST))
    assert len(items) == 3  # 2 episodes × languages expand per item×lang
    assert items[0]["episode_id"] == "ep-01"
    assert items[0]["language"] == "es-ES"


def test_load_manifest_refuses_unapproved_batch(tmp_path):
    manifest = {**MANIFEST, "approved": False}
    with pytest.raises(ValueError, match="approved"):
        load_manifest(_write_manifest(tmp_path, manifest))


def test_load_manifest_refuses_duplicate_item_language(tmp_path):
    manifest = {
        **MANIFEST,
        "items": [{**MANIFEST["items"][0], "languages": ["es-ES", "es-ES"]}],
    }
    with pytest.raises(ValueError, match="duplicate"):
        load_manifest(_write_manifest(tmp_path, manifest))


def test_default_chain_is_the_fixed_station_order():
    item = {"episode_id": "ep-01", "language": "es-ES"}
    assert plan_chain(item) == ["ingest", "dub", "loudness", "delivery"]


def test_batch_job_ids_are_deterministic_and_unique():
    a = batch_job_id("batch-demo-01", "ep-01", "es-ES", "dub")
    b = batch_job_id("batch-demo-01", "ep-01", "es-ES", "dub")
    assert a == b  # idempotent re-submission (C-6.3)
    assert a != batch_job_id("batch-demo-01", "ep-01", "fr-FR", "dub")
    assert a.startswith("cyc-batch-demo-01-")
    for station in ("ingest", "loudness", "delivery"):
        assert batch_job_id("batch-demo-01", "ep-01", "es-ES", station) != a


def test_estimate_costs_every_item_language_before_any_billable_run():
    estimate = estimate_batch_cost(MANIFEST["items"])
    # 3 item×language pairs; each pays TTS characters + one agent judgment.
    assert estimate["jobs"] == 3
    assert estimate["total_micros"] > 0
    assert estimate["per_job_micros"] == pytest.approx(
        estimate["total_micros"] / 3, rel=0.01
    )
    assert estimate["total_usd"] < 1.0  # demo batch is cents, not dollars


def test_validate_agent_chain_accepts_subsequence_of_default():
    # The agent may TRIM the deterministic chain (advisory) but never invent
    # stations or reorder it.
    assert validate_agent_chain(["ingest", "dub", "delivery"], "es-ES") == [
        "ingest",
        "dub",
        "delivery",
    ]
    with pytest.raises(ValueError, match="vocabulary"):
        validate_agent_chain(["ingest", "extend", "delivery"], "es-ES")
    with pytest.raises(ValueError, match="order"):
        validate_agent_chain(["dub", "ingest", "delivery"], "es-ES")
    with pytest.raises(ValueError, match="empty"):
        validate_agent_chain([], "es-ES")


# --- job building + submission (C-6.3) --------------------------------------


def _manifest_with_shots(tmp_path: Path):
    manifest = {
        "batch_id": "batch-demo-01",
        "approved": True,
        "items": [
            {
                "episode_id": "ep-01",
                "source_ref": "fixtures/batch-demo/ep-01-source.wav",
                "shot_id": "shot-ep-01",
                "languages": ["es-ES"],
                "scripts": {"es-ES": "Bienvenido a Martini Shot."},
            }
        ],
    }
    return load_manifest(_write_manifest(tmp_path, manifest))


def test_build_batch_jobs_one_job_per_chain_station(tmp_path):
    from backend.jobs.models import Job
    from backend.supervisor.orchestrator import build_batch_jobs

    items = _manifest_with_shots(tmp_path)
    jobs = build_batch_jobs(items)
    assert [j.station for j in jobs] == ["ingest", "dub", "loudness", "delivery"]
    dub = jobs[1]
    assert isinstance(dub, Job)
    assert dub.id == batch_job_id("batch-demo-01", "ep-01", "es-ES", "dub")
    assert dub.input_refs == ["fixtures/batch-demo/ep-01-source.wav"]
    # The dub station's contract: ssml + shot_id + language ride in result.
    assert dub.result["ssml"] == "<speak>Bienvenido a Martini Shot.</speak>"
    assert dub.result["shot_id"] == "shot-ep-01"
    assert dub.result["language"] == "es-ES"
    assert dub.result["batch_id"] == "batch-demo-01"


def test_build_batch_jobs_is_idempotent_across_calls(tmp_path):
    from backend.supervisor.orchestrator import build_batch_jobs

    items = _manifest_with_shots(tmp_path)
    again = build_batch_jobs(items)
    assert [j.id for j in again] == [j.id for j in build_batch_jobs(items)]


def test_submit_batch_is_idempotent_at_the_queue(tmp_path):
    """Integration: resubmitting the same plan must not double-create jobs
    (C-6.3) — the queue's per-id idempotency absorbs the retry."""
    import uuid

    from backend.core.config import get_settings
    from backend.core.firestore import get_firestore
    from backend.jobs.queue import FirestoreLeaseQueue

    settings = get_settings()
    assert settings.gcp_project_id, "real-service law C-6.2"
    queue = FirestoreLeaseQueue(
        get_firestore(settings), collection=f"it-jobs-orch-{uuid.uuid4().hex[:10]}"
    )
    jobs = build_batch_jobs(_manifest_with_shots(tmp_path))
    submit_batch(queue, jobs)
    submit_batch(queue, jobs)  # duplicate submission must be a no-op
    leased = queue.lease("w-1", ["ingest", "dub", "loudness", "delivery"])
    assert leased is not None
    assert leased.id in {j.id for j in jobs}
    queue.forget(leased.id)


# --- orchestrator agent planning (deterministic surface) ---------------------


def test_planning_prompt_carries_item_context_and_vocabulary():
    from backend.supervisor.station_agents.orchestrator import build_planning_prompt

    prompt = build_planning_prompt(
        {"episode_id": "ep-01", "language": "es-ES", "script": "Hola."},
        default_chain=["ingest", "dub", "loudness", "delivery"],
    )
    assert "ep-01" in prompt and "es-ES" in prompt
    assert "ingest" in prompt and "dub" in prompt
    assert "trim" in prompt.lower() or "advis" in prompt.lower()


def test_plan_item_accepts_valid_agent_chain_and_marks_override():
    from backend.supervisor.station_agents.orchestrator import plan_item

    def fake_call(settings, prompt, **kwargs):
        return {
            "model": "m",
            "text": json.dumps(
                {
                    "agent": "orchestrator",
                    "chain": ["dub", "loudness"],
                    "reason": "source already ingested upstream",
                    "confidence": "high",
                }
            ),
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_micros": 100,
            "latency_ms": 1.0,
        }

    chain, doc = plan_item(
        object(),
        {"episode_id": "ep-01", "language": "es-ES"},
        default_chain=["ingest", "dub", "loudness", "delivery"],
        run_agent_call=fake_call,
    )
    assert chain == ["dub", "loudness"]
    assert doc["overridden"] is True
    assert doc["decision_mode"] == "agent"


def test_plan_item_falls_back_visibly_on_bad_payload():
    from backend.supervisor.station_agents.orchestrator import plan_item

    def bad_call(settings, prompt, **kwargs):
        return {
            "model": "m",
            "text": json.dumps({"agent": "orchestrator", "chain": ["extend"]}),
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_micros": 100,
            "latency_ms": 1.0,
        }

    chain, doc = plan_item(
        object(),
        {"episode_id": "ep-01", "language": "es-ES"},
        default_chain=["ingest", "dub", "loudness", "delivery"],
        run_agent_call=bad_call,
    )
    assert chain == ["ingest", "dub", "loudness", "delivery"]
    # Visible, never silent (A10 spec): the fallback is recorded on the doc.
    assert doc["decision_mode"] == "deterministic_fallback"
