"""ADK finishing team construction (Runner is invoked in live evals)."""

from __future__ import annotations

import json

from backend.supervisor.adk_finishing import (
    ORCHESTRATOR_NAME,
    build_finishing_team,
    build_station_agent,
)
from backend.supervisor.finishing_loop import PROPOSE_STATIONS


def test_finishing_team_is_parallel_then_orchestrator() -> None:
    root = build_finishing_team(settings=None, context={"clip_uri": "gs://x"})
    assert root.name == "finishing_root"
    assert len(root.sub_agents) == 2
    parallel, boss = root.sub_agents
    assert parallel.name == "finishing_attendance"
    assert [child.name for child in parallel.sub_agents] == [
        f"finish_{station}" for station in PROPOSE_STATIONS
    ]
    assert "finish_ingest" not in [child.name for child in parallel.sub_agents]
    assert "finish_loudness" not in [child.name for child in parallel.sub_agents]
    assert "finish_pickups" not in [child.name for child in parallel.sub_agents]
    assert boss.name == ORCHESTRATOR_NAME
    assert "gemini" in str(boss.model).lower() or boss.model


def test_jobs_from_notes_auto_enqueue() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect import validate_inspect_note

    note = validate_inspect_note(
        {
            "station": "loudness",
            "agent": "loudness_strategy",
            "status": "needs_work",
            "impact": "high",
            "kind": "defect",
            "summary": "unhearable",
            "cost_estimate_micros": 80_000,
            "proposal": {"kind": "station_job", "station": "loudness", "args": {}},
            "shot_id": "shot-1",
        }
    )
    jobs = jobs_from_notes(
        [note],
        project_id="p",
        source_uri="gs://b/c.mp4",
        shot_id="shot-1",
        scene_understanding={
            "ingested": True,
            "spoken_words": "The door is open.",
            "scene": "A blue field.",
        },
    )
    assert len(jobs) == 1
    assert jobs[0].station == "loudness"
    assert jobs[0].status == "queued"
    assert jobs[0].result.get("finishing") is True
    assert jobs[0].result.get("ingested") is True
    assert jobs[0].result.get("spoken_words") == "The door is open."
    assert "blue" in str(jobs[0].result.get("scene") or "")
    handoff = jobs[0].result.get("handoff") or {}
    assert handoff.get("version") == 1
    assert handoff.get("scene", {}).get("ingested") is True


def test_reorder_skips_passed_items() -> None:
    from backend.supervisor.worklist import reorder_items

    doc = {
        "items": [
            {"id": "a", "status": "passed", "station": "loudness"},
            {"id": "b", "status": "waiting", "station": "extend"},
            {"id": "c", "status": "waiting", "station": "relight"},
        ]
    }
    out = reorder_items(doc, ["c", "b", "a"])
    ids = [item["id"] for item in out["items"]]
    assert ids[0] == "c"
    assert "a" in ids


def test_d9_extend_is_an_adk_station_agent() -> None:
    """Walk-away loop: Extend looks, suggests, then the worker executes."""
    agent = build_station_agent(
        "extend",
        settings=None,
        context={"clip_uri": "gs://b/clip.mp4", "shot_id": "shot-12"},
    )
    assert agent.name == "finish_extend"
    instruction = str(agent.instruction).lower()
    assert "mid-thought" in instruction or "keep rolling" in instruction
    assert "draft" in instruction
    tool_names = [getattr(tool, "name", "") or "" for tool in (agent.tools or [])]
    assert any("extend" in name for name in tool_names)


def test_extend_looker_has_must_nice_and_leave_buckets() -> None:
    agent = build_station_agent(
        "extend",
        settings=None,
        context={"clip_uri": "gs://b/clip.mp4"},
    )
    text = str(agent.instruction).lower()
    assert "must" in text
    assert "leave" in text or "status=ok" in text or "status = ok" in text
    assert "breath" in text or "nice" in text
    assert "do not propose" in text or "no proposal" in text


def test_extend_inspect_suggests_a_draft_station_job() -> None:
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "extend",
                "status": "needs_work",
                "impact": "medium",
                "kind": "defect",
                "summary": "The line is cut mid-thought",
            }
        ),
        "extend",
    )
    assert note.agent == "extend"
    assert note.proposal["kind"] == "station_job"
    assert note.proposal["station"] == "extend"
    assert note.proposal["args"]["tier"] == "draft"


def test_extend_complete_shot_is_ok_with_no_job() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "extend",
                "status": "ok",
                "impact": "none",
                "kind": "none",
                "summary": "The two-shot already lands. Do not extend.",
                "cost_estimate_micros": 0,
            }
        ),
        "extend",
    )
    assert note.status == "ok"
    assert note.proposal == {}
    jobs = jobs_from_notes(
        [note],
        project_id="p",
        source_uri="gs://b/table.mp4",
        shot_id="shot-complete",
    )
    assert jobs == []


def test_extend_extra_air_is_low_improvement_draft() -> None:
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "extend",
                "status": "needs_work",
                "impact": "low",
                "kind": "improvement",
                "summary": "The beat lands; a breath of air at the end would help.",
            }
        ),
        "extend",
    )
    assert note.kind == "improvement"
    assert note.impact == "low"
    assert note.proposal["args"]["tier"] == "draft"


def test_extend_finishing_job_is_executable_draft_render() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect import validate_inspect_note

    note = validate_inspect_note(
        {
            "station": "extend",
            "agent": "extend",
            "status": "needs_work",
            "impact": "medium",
            "kind": "defect",
            "summary": "Shot dies mid-gesture",
            "cost_estimate_micros": 3_000_000,
            "proposal": {
                "kind": "station_job",
                "station": "extend",
                "args": {"prompt": "Keep rolling through the line"},
            },
            "shot_id": "shot-12",
        }
    )
    jobs = jobs_from_notes(
        [note],
        project_id="p",
        source_uri="gs://b/clip.mp4",
        shot_id="shot-12",
    )
    assert len(jobs) == 1
    job = jobs[0]
    assert job.station == "extend"
    assert job.input_refs == ["gs://b/clip.mp4"]
    assert job.result["shot_id"] == "shot-12"
    assert job.result["tier"] == "draft"
    assert "Keep rolling" in str(job.result.get("prompt") or "")
    assert job.result.get("finishing") is True


def test_orchestrator_rank_payload_includes_scene_bag() -> None:
    from backend.supervisor.adk_finishing import rank_payload

    payload = rank_payload(
        remaining_micros=1_000,
        shot_order={"shot-1": 0},
        candidates=[{"id": "loudness::shot-1", "station": "loudness"}],
        scene_by_shot={
            "shot-1": {
                "ingested": True,
                "spoken_words": "Hello.",
                "scene": "A doorway.",
            }
        },
    )
    assert payload["scene_by_shot"]["shot-1"]["ingested"] is True
    assert payload["scene_by_shot"]["shot-1"]["spoken_words"] == "Hello."


def test_complete_bag_rank_keeps_extend_behind_hearability() -> None:
    from backend.supervisor.inspect import validate_inspect_note
    from backend.supervisor.rank_impl import rank_complete_bag

    loud = validate_inspect_note(
        {
            "station": "loudness",
            "agent": "loudness_strategy",
            "status": "needs_work",
            "impact": "high",
            "kind": "defect",
            "summary": "unhearable",
            "cost_estimate_micros": 80_000,
            "proposal": {"kind": "station_job", "station": "loudness", "args": {}},
            "shot_id": "shot-a",
        }
    )
    ext = validate_inspect_note(
        {
            "station": "extend",
            "agent": "extend",
            "status": "needs_work",
            "impact": "medium",
            "kind": "defect",
            "summary": "dies mid-thought",
            "cost_estimate_micros": 3_000_000,
            "proposal": {"kind": "station_job", "station": "extend", "args": {}},
            "shot_id": "shot-a",
        }
    )
    plan = rank_complete_bag(
        None,
        [loud, ext],
        shot_order={"shot-a": 0},
        remaining_micros=50_000_000,
        adk_text=json.dumps(
            {
                "order": ["loudness::shot-a", "extend::shot-a"],
                "dependencies": [
                    {
                        "before": "loudness::shot-a",
                        "after": "extend::shot-a",
                        "reason": "mix before generating more picture",
                    }
                ],
                "reason": "hear the line, then keep rolling",
            }
        ),
    )
    assert [note.station for note in plan.ordered] == ["loudness", "extend"]
    assert plan.blocked_by["extend::shot-a"] == ["loudness::shot-a"]


def test_d10_corrections_is_an_adk_station_agent() -> None:
    """Walk-away loop: Corrections looks, names the defect, then the worker executes."""
    agent = build_station_agent(
        "corrections",
        settings=None,
        context={"clip_uri": "gs://b/cafe-sign.mp4", "shot_id": "shot-sign"},
    )
    assert agent.name == "finish_corrections"
    instruction = str(agent.instruction).lower()
    assert "signage" in instruction or "sign" in instruction
    assert "draft" in instruction
    assert "alternate" in instruction
    tool_names = [getattr(tool, "name", "") or "" for tool in (agent.tools or [])]
    assert any("corrections" in name for name in tool_names)


def test_corrections_looker_has_must_nice_and_leave_buckets() -> None:
    agent = build_station_agent(
        "corrections",
        settings=None,
        context={"clip_uri": "gs://b/cafe-sign.mp4"},
    )
    text = str(agent.instruction).lower()
    assert "must" in text or "required" in text or "defect" in text
    assert "leave" in text or "status=ok" in text or "status = ok" in text
    assert "do not propose" in text or "no proposal" in text


def test_corrections_inspect_suggests_a_draft_station_job() -> None:
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "corrections",
                "status": "needs_work",
                "impact": "high",
                "kind": "defect",
                "summary": "The café sign still says CLOSED",
            }
        ),
        "corrections",
    )
    assert note.agent == "corrections"
    assert note.proposal["kind"] == "station_job"
    assert note.proposal["station"] == "corrections"
    assert note.proposal["args"]["tier"] == "draft"
    assert "CLOSED" in str(note.proposal["args"].get("intent") or note.summary)


def test_corrections_finishing_job_is_executable_draft_edit() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect import validate_inspect_note

    note = validate_inspect_note(
        {
            "station": "corrections",
            "agent": "corrections",
            "status": "needs_work",
            "impact": "high",
            "kind": "defect",
            "summary": "Café sign says CLOSED",
            "cost_estimate_micros": 3_000_000,
            "proposal": {
                "kind": "station_job",
                "station": "corrections",
                "args": {"intent": "Replace the café sign text with OPEN"},
            },
            "shot_id": "shot-sign",
        }
    )
    jobs = jobs_from_notes(
        [note],
        project_id="p",
        source_uri="gs://b/cafe-sign.mp4",
        shot_id="shot-sign",
    )
    assert len(jobs) == 1
    job = jobs[0]
    assert job.station == "corrections"
    assert job.input_refs == ["gs://b/cafe-sign.mp4"]
    assert job.result["shot_id"] == "shot-sign"
    assert job.result["tier"] == "draft"
    assert "OPEN" in str(job.result.get("intent") or "")
    assert job.result.get("finishing") is True


def test_corrections_inspect_covers_prop_removal() -> None:
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "corrections",
                "status": "needs_work",
                "impact": "medium",
                "kind": "improvement",
                "summary": "Unmotivated paper cup on the table",
            }
        ),
        "corrections",
    )
    assert note.proposal["args"]["tier"] == "draft"
    assert "cup" in str(note.proposal["args"]["intent"]).lower()


def test_corrections_clean_clip_is_ok_with_no_job() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "corrections",
                "status": "ok",
                "impact": "none",
                "kind": "none",
                "summary": "No wrong signage, graphic, or unmotivated prop.",
                "cost_estimate_micros": 0,
            }
        ),
        "corrections",
    )
    assert note.status == "ok"
    assert note.proposal == {}
    jobs = jobs_from_notes(
        [note],
        project_id="p",
        source_uri="gs://b/florist.mp4",
        shot_id="shot-clean",
    )
    assert jobs == []


def test_relight_looker_has_must_nice_and_leave_buckets() -> None:
    agent = build_station_agent(
        "relight",
        settings=None,
        context={"clip_uri": "gs://b/dark.mp4"},
    )
    text = str(agent.instruction).lower()
    assert agent.name == "finish_relight"
    assert "must" in text
    assert "leave" in text or "status=ok" in text
    assert "preset" in text
    assert "do not propose" in text or "no proposal" in text
    assert "already matches" in text


def test_relight_inspect_stamps_named_preset_and_draft() -> None:
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "relight",
                "status": "needs_work",
                "impact": "high",
                "kind": "defect",
                "summary": "Faces lost in shadow",
            }
        ),
        "relight",
    )
    assert note.proposal["station"] == "relight"
    assert note.proposal["args"]["tier"] == "draft"
    assert note.proposal["args"]["preset"] == "practical_lamp"


def test_relight_leave_it_is_ok_with_no_job() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "relight",
                "status": "ok",
                "impact": "none",
                "kind": "none",
                "summary": "Lighting already matches; faces readable.",
                "cost_estimate_micros": 0,
            }
        ),
        "relight",
    )
    assert note.status == "ok"
    assert note.proposal == {}
    jobs = jobs_from_notes(
        [note],
        project_id="p",
        source_uri="gs://b/florist.mp4",
        shot_id="shot-lit",
    )
    assert jobs == []


def test_relight_finishing_job_carries_preset() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect import validate_inspect_note

    note = validate_inspect_note(
        {
            "station": "relight",
            "agent": "relight",
            "status": "needs_work",
            "impact": "high",
            "kind": "defect",
            "summary": "Faces unreadable",
            "cost_estimate_micros": 3_000_000,
            "proposal": {
                "kind": "station_job",
                "station": "relight",
                "args": {"preset": "noir"},
            },
            "shot_id": "shot-dark",
        }
    )
    jobs = jobs_from_notes(
        [note],
        project_id="p",
        source_uri="gs://b/dark.mp4",
        shot_id="shot-dark",
    )
    assert len(jobs) == 1
    assert jobs[0].station == "relight"
    assert jobs[0].result["preset"] == "noir"
    assert jobs[0].result["tier"] == "draft"


def test_coverage_looker_has_must_nice_and_leave_buckets() -> None:
    agent = build_station_agent(
        "coverage",
        settings=None,
        context={"clip_uri": "gs://b/cafe.mp4"},
    )
    text = str(agent.instruction).lower()
    assert "must" in text
    assert "geography" in text
    assert "leave" in text or "status=ok" in text
    assert "do not propose" in text or "no proposal" in text
    assert "two-shot" in text or "ots" in text
    assert "hands" in text or "insert" in text


def test_coverage_inspect_uses_clip_as_subject_reference() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "coverage",
                "status": "needs_work",
                "impact": "medium",
                "kind": "defect",
                "summary": "Cannot tell where we are",
            }
        ),
        "coverage",
    )
    assert note.proposal["args"]["angle"] in {
        "reverse_angle",
        "close_up",
        "wide_establishing",
        "over_the_shoulder",
        "insert",
    }
    jobs = jobs_from_notes(
        [note],
        project_id="p",
        source_uri="gs://b/cafe.mp4",
        shot_id="shot-geo",
    )
    assert jobs[0].result["reference_uris"] == ["gs://b/cafe.mp4"]
    assert jobs[0].result["tier"] == "draft"


def test_coverage_leave_it_is_ok_with_no_job() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "coverage",
                "status": "ok",
                "impact": "none",
                "kind": "none",
                "summary": "Geography already clear.",
                "cost_estimate_micros": 0,
            }
        ),
        "coverage",
    )
    assert (
        jobs_from_notes(
            [note],
            project_id="p",
            source_uri="gs://b/florist.mp4",
            shot_id="shot-cov",
        )
        == []
    )


def test_camera_language_looker_has_must_nice_and_leave_buckets() -> None:
    agent = build_station_agent(
        "camera_language",
        settings=None,
        context={
            "clip_uri": "gs://b/table.mp4",
            "requested_movement": "dolly_tracking",
        },
    )
    text = str(agent.instruction).lower()
    assert "must" in text
    assert "leave" in text or "status=ok" in text
    assert "dolly" in text or "vocabulary" in text
    assert "still life" in text or "dialogue" in text
    assert "do not invent a dolly" in text


def test_camera_language_inspect_stamps_movement() -> None:
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "camera_language",
                "status": "needs_work",
                "impact": "low",
                "kind": "improvement",
                "summary": "Locked-off; a motivated dolly would help",
                "proposal": {
                    "kind": "station_job",
                    "station": "camera_language",
                    "args": {"movement": "dolly_tracking"},
                },
            }
        ),
        "camera_language",
    )
    assert note.proposal["args"]["movement"] == "dolly_tracking"
    assert note.proposal["args"]["tier"] == "draft"


def test_camera_language_leave_it_is_ok_with_no_job() -> None:
    from backend.supervisor.finishing_loop import jobs_from_notes
    from backend.supervisor.inspect_impl import parse_inspect_text

    note = parse_inspect_text(
        json.dumps(
            {
                "station": "camera_language",
                "status": "ok",
                "impact": "none",
                "kind": "none",
                "summary": "This still life should stay locked-off.",
                "cost_estimate_micros": 0,
            }
        ),
        "camera_language",
    )
    assert (
        jobs_from_notes(
            [note],
            project_id="p",
            source_uri="gs://b/florist.mp4",
            shot_id="shot-cam",
        )
        == []
    )
