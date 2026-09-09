"""D-9 Extend station — deterministic parts (TDD, RED-first).

Contracts (plan task D-9, A8; Omni-primary per decision log 2026-09-04):
- Cost estimation is a real price table (integer micros, C-6.4): 720p
  ~= $0.10/s output, 360p ~= 1/3 of that; sub-second durations ceil.
- The extend prompt follows the docs' simple style (elaborate prompts
  caused a generation refusal in the G0/Omni probes).
- The station is dispatched like every other station (one dispatch table).
- Draft QC gate: a render whose flicker breaches the continuity gate does
  NOT silently pass — it lands as needs_human with the scores attached.
- Every render is an ALTERNATE (never an overwrite) — integration-tested
  live by the EDD run (scripts/extend_eval.py), not mocked here (C-1.1).
"""

from __future__ import annotations

import pytest


def test_omni_transport_timeout_is_retryable() -> None:
    from backend.core.generative import is_omni_transport_timeout

    assert is_omni_transport_timeout(TimeoutError("The write operation timed out"))
    assert is_omni_transport_timeout(
        RuntimeError(
            "RetryError: Timeout of 120.0s exceeded, last exception: "
            "('Connection aborted.', TimeoutError('The write operation timed out'))"
        )
    )
    assert not is_omni_transport_timeout(RuntimeError("recitation"))
    from backend.core.generative import estimate_extend_cost_micros

    # 720p ~= $0.10/s -> 100_000 micros per second; Vertex bills per output
    # second, so a 1.1s render bills 2 seconds (integer math, ceil).
    assert estimate_extend_cost_micros(7.0) == 700_000
    assert estimate_extend_cost_micros(1.1) == 200_000
    # Sub-second still bills a full second minimum (Vertex bills per second).
    assert estimate_extend_cost_micros(0.2) == 100_000
    # 360p is roughly one third of 720p (33334 micros/s x 7s).
    assert estimate_extend_cost_micros(7.0, resolution="360p") == 233_338
    with pytest.raises(ValueError):
        estimate_extend_cost_micros(0.0)
    with pytest.raises(ValueError):
        estimate_extend_cost_micros(-1.0)
    with pytest.raises(ValueError):
        estimate_extend_cost_micros(3.0, resolution="8k")


def test_extend_prompt_follows_docs_simple_style() -> None:
    from backend.core.generative import build_extend_prompt

    prompt = build_extend_prompt("Scene 12 — chaser")
    assert "Extend this video" in prompt
    assert "Keep everything else the same" in prompt
    # Elaborate instructions caused refusals in the probe: the builder must
    # not stuff long narrative directions into the prompt.
    assert len(prompt) < 400


def test_extend_station_is_dispatched() -> None:
    from backend.stations import run as dispatch
    from backend.stations.extend.run import STATION

    assert STATION == "extend"
    assert "extend" in dispatch.STATION_NAMES
    # Exactly one extend entry: the unknown-station guard must not fire for
    # it, and no duplicate dispatch paths may exist.
    assert dispatch.STATION_NAMES.count("extend") == 1


def test_extend_draft_qc_gate() -> None:
    from backend.stations.extend.run import (
        FLICKER_GATE,
        FLICKER_SPIKE_GATE,
        draft_qc_decision,
        resolution_for_tier,
    )

    assert FLICKER_GATE == 0.02
    assert draft_qc_decision(0.0031) == "pass"
    assert draft_qc_decision(0.0199) == "pass"
    assert draft_qc_decision(0.02) == "needs_human"
    assert draft_qc_decision(0.5) == "needs_human"
    # 2026-09-09 demo: a real, localized single-frame corruption scored
    # ~0.005 mean (well under gate) — the whole-clip average dilutes one
    # bad frame across dozens of clean ones. The worst-frame spike must
    # still gate it even when the mean alone would pass.
    assert draft_qc_decision(0.003, spike=0.003) == "pass"
    assert draft_qc_decision(0.003, spike=FLICKER_SPIKE_GATE) == "needs_human"
    assert resolution_for_tier("draft") == "360p"
    assert resolution_for_tier("master") == "720p"
    assert resolution_for_tier("") == "360p"


def test_veo_payload_extraction() -> None:
    """Veo's fetchPredictOperation returns either inline base64 video bytes
    or a GCS URI; an LRO error (e.g. unsupported duration) must surface as a
    readable exception, never a silent empty render."""
    import base64

    from backend.core.generative import extract_veo_video

    b64 = base64.b64encode(b"mp4-bytes").decode()
    done = {
        "done": True,
        "response": {"videos": [{"bytesBase64Encoded": b64}]},
    }
    assert extract_veo_video(done) == b"mp4-bytes"

    done_gcs = {
        "done": True,
        "response": {"videos": [{"gcsUri": "gs://b/out.mp4"}]},
    }
    assert extract_veo_video(done_gcs) == "gs://b/out.mp4"

    errored = {
        "done": True,
        "error": {"code": 3, "message": "Unsupported output video duration 8 seconds"},
    }
    try:
        extract_veo_video(errored)
        raise AssertionError("LRO error must raise")
    except RuntimeError as exc:
        assert "Unsupported output video duration" in str(exc)

    filtered = {"done": True, "response": {"raiMediaFilteredCount": 1}}
    try:
        extract_veo_video(filtered)
        raise AssertionError("filtered response must raise")
    except RuntimeError:
        pass


def test_extend_proposal_approve_enqueues_real_job(env, run_id, monkeypatch) -> None:
    """D-9 chain, propose→approve→enqueue (real Firestore, spine API): an
    approved extend proposal enqueues a deterministic-id `extend` job whose
    result carries the shot and source. The render itself is EDD-covered."""
    import uuid

    from backend.api import spine
    from backend.api.app import create_app
    from backend.core.config import get_settings, reset_settings
    from backend.shots import lifecycle as shots

    monkeypatch.setattr(spine, "DELIBERATIONS", f"it-deliberations-{run_id}")
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = shots.ensure_shot(env, project_id=project_id, title="D-9 chain test")

    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    from fastapi.testclient import TestClient

    headers = {"X-API-Key": settings.api_key}
    with TestClient(app) as client:
        proposed = client.post(
            f"/api/v1/shots/{shot_id}/extend",
            headers=headers,
            json={
                "source_uri": f"gs://{settings.gcs_bucket}/probes/shot-01-meadow.mp4",
                "reason": "extend the chaser for the demo",
            },
        )
        assert proposed.status_code == 200
        approval_id = proposed.json()["approval_id"]

        approved = client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            headers=headers,
            json={"decision": "approve", "reason": "go"},
        )
        assert approved.status_code == 200

        job_id = f"ext-{approval_id}"
        job_doc = env.get_doc("pc-jobs", job_id)
        assert job_doc is not None, "approved extend must enqueue a real job"
        assert job_doc["station"] == "extend"
        assert job_doc["status"] == "queued"
        assert job_doc["result"]["shot_id"] == shot_id
        assert job_doc["result"]["tier"] == "draft"
        assert job_doc["input_refs"][0].startswith("gs://")

        # Idempotent redrive: submitting the same deterministic id must not
        # duplicate (the sweeper may re-drive a crashed fast action).
        approved2 = client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            headers=headers,
            json={"decision": "approve", "reason": "re-drive"},
        )
        assert approved2.status_code in (200, 409)

        # Signed-media route answers for a stored artifact (upload a stub
        # object first — real GCS, real signing).
        from backend.core.gcs import get_gcs

        key = f"projects/{project_id}/extends/{job_id}.mp4"
        get_gcs(settings).upload_bytes(
            key, b"stub-not-a-render", content_type="video/mp4"
        )
        media = client.get("/api/v1/alternates/alt-missing/media", headers=headers)
        assert media.status_code == 404

        shots.record_alternate(
            env,
            shot_id=shot_id,
            project_id=project_id,
            op="extend",
            artifact_ref=f"gs://{settings.gcs_bucket}/probes/shot-01-meadow.mp4",
            eval_scores={"flicker": 0.003},
            tier="draft",
        )
        master = client.post(
            f"/api/v1/shots/{shot_id}/master",
            headers=headers,
            json={
                "op": "extend",
                "source_uri": f"gs://{settings.gcs_bucket}/probes/shot-01-meadow.mp4",
            },
        )
        assert master.status_code == 200
        master_id = master.json()["approval_id"]
        master_ok = client.post(
            f"/api/v1/approvals/{master_id}/decision",
            headers=headers,
            json={"decision": "approve", "reason": "draft passed"},
        )
        assert master_ok.status_code == 200
        master_job = env.get_doc("pc-jobs", f"mst-ext-{master_id}")
        assert master_job is not None
        assert master_job["station"] == "extend"
        assert master_job["result"]["tier"] == "master"


def _omni_record(**overrides: object) -> dict:
    row: dict = {
        "render_model": "gemini-omni-1.1-flash-preview",
        "omni_fallback": False,
        "flicker": 0.003,
        "qc_decision": "pass",
        "alternate_status": "draft",
        "start_maker": "omni",
    }
    row.update(overrides)
    return row


def test_extend_quality_rejects_veo_fallback() -> None:
    from backend.evals.extend_quality import summarize_extend_quality

    omni = summarize_extend_quality([_omni_record()])
    assert omni["pass"] is True
    assert omni["omni_render_rate"] == 1.0
    assert omni["mean_output_flicker"] < 0.02

    veo = summarize_extend_quality(
        [
            _omni_record(
                render_model="veo-3.1-fast-generate-001",
                omni_fallback=True,
                omni_error="recitation",
            )
        ]
    )
    assert veo["pass"] is False
    assert veo["omni_render_rate"] == 0.0
    assert "omni_fallback" in veo["fail_reason"]


def test_extend_quality_rejects_flicker_breach_and_empty() -> None:
    from backend.evals.extend_quality import summarize_extend_quality

    hot = summarize_extend_quality([_omni_record(flicker=0.03)])
    assert hot["pass"] is False
    empty = summarize_extend_quality([])
    assert empty["pass"] is False
    missing_master = summarize_extend_quality(
        [_omni_record(tier="draft")], min_drafts=1, min_masters=1
    )
    assert missing_master["pass"] is False
    assert "too_few_masters" in missing_master["fail_reason"]
