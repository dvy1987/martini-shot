"""ADK finishing team construction (Runner is invoked in live evals)."""

from __future__ import annotations

from backend.supervisor.adk_finishing import ORCHESTRATOR_NAME, build_finishing_team
from backend.supervisor.inspect import ROSTER


def test_finishing_team_is_parallel_then_orchestrator() -> None:
    root = build_finishing_team(settings=None, context={"clip_uri": "gs://x"})
    assert root.name == "finishing_root"
    assert len(root.sub_agents) == 2
    parallel, boss = root.sub_agents
    assert parallel.name == "finishing_attendance"
    assert [child.name for child in parallel.sub_agents] == [
        f"finish_{station}" for station in ROSTER
    ]
    assert len(parallel.sub_agents) == 11
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
        [note], project_id="p", source_uri="gs://b/c.mp4", shot_id="shot-1"
    )
    assert len(jobs) == 1
    assert jobs[0].station == "loudness"
    assert jobs[0].status == "queued"
    assert jobs[0].result.get("finishing") is True


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
