"""D-15 Revision Room — version lineage, diff, affected spans, staleness."""

from __future__ import annotations

import uuid

import pytest

from backend.revision import alignment as revision


@pytest.fixture(autouse=True)
def _isolated_revision_collections(monkeypatch, run_id):
    monkeypatch.setattr(revision, "VERSIONS", f"it-scripts-{run_id}")
    monkeypatch.setattr(revision, "ALIGNMENTS", f"it-align-{run_id}")
    yield


def test_diff_spans_maps_inserts_and_replacements() -> None:
    diffs = revision.diff_spans("Hello world", "Hello there world")
    kinds = {item.kind for item in diffs}
    assert "insert" in kinds or "replace" in kinds
    assert any("there" in item.new_text for item in diffs)


def test_affected_spans_use_interval_overlap() -> None:
    diffs = revision.diff_spans("aaa bbb ccc", "aaa XXX ccc")
    alignment = [
        {
            "span_id": "sp-1",
            "start_char": 0,
            "end_char": 3,
            "shot_id": "shot-a",
            "language": "en",
        },
        {
            "span_id": "sp-2",
            "start_char": 4,
            "end_char": 7,
            "shot_id": "shot-b",
            "language": "en",
        },
        {
            "span_id": "sp-3",
            "start_char": 8,
            "end_char": 11,
            "shot_id": "shot-c",
            "language": "de",
        },
    ]
    hits = revision.affected_spans(diffs, alignment)
    shot_ids = {shot for hit in hits for shot in hit["affected_shot_ids"]}
    assert "shot-b" in shot_ids
    assert "shot-a" not in shot_ids


def test_stale_version_edit_is_rejected(env) -> None:
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    first = revision.create_version(
        env, project_id=project_id, text="v1", based_on_version_id=None
    )
    revision.create_version(
        env,
        project_id=project_id,
        text="v2",
        based_on_version_id=first["version_id"],
    )
    with pytest.raises(revision.StaleVersionError):
        revision.create_version(
            env,
            project_id=project_id,
            text="stale",
            based_on_version_id=first["version_id"],
        )


def test_revision_agent_abstains_without_impact() -> None:
    import json

    from backend.supervisor.station_agents.revision_room import parse_revision_decision

    decision = parse_revision_decision(
        json.dumps(
            {
                "agent": "revision_room",
                "decision": "propose_regeneration",
                "reason": "regenerate everything just in case",
                "confidence": "low",
            }
        ),
        [{"affected_shot_ids": [], "affected_span_ids": []}],
    )
    assert decision.decision == "abstain"
    assert decision.overridden is True
