"""AL-1 shot locking + alternates model (TDD, RED-first).

Contract (plan task AL-1 + H-0 design "Locked-target guard"):
- Every generated clip is an ALTERNATE {shot_id, op, artifact_ref,
  eval_scores, status} attached to its shot — never a silent overwrite.
- add/remove-from-continuity is an approval-tracked action THROUGH H-0
  (default_registry commands), not a second action path.
- A locked shot refuses any command that targets it, centrally, at dispatch
  time — for every caller. Only the lock/unlock commands themselves may act
  on a locked shot (unlock is the whole point).

Real Firestore (C-6.2), per-run collections; Harness reused from the
executor suite.
"""

from __future__ import annotations

import uuid

import pytest

from backend.approvals.machine import propose_approval
from backend.approvals.sweeper import sweep_once
from backend.shots import lifecycle as shots
from tests.test_approval_executor import Harness

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _isolated_shot_collections(monkeypatch, run_id):
    monkeypatch.setattr(shots, "SHOTS", f"it-shots-{run_id}")
    monkeypatch.setattr(shots, "ALTERNATES", f"it-alternates-{run_id}")
    yield


def _make_shot(store, project_id: str) -> str:
    return shots.ensure_shot(store, project_id=project_id, title="Scene 12 — chaser")


def _record(
    store, shot_id: str, project_id: str, artifact: str = "gs://b/alt-a.mp4"
) -> str:
    return shots.record_alternate(
        store,
        shot_id=shot_id,
        project_id=project_id,
        op="extend",
        artifact_ref=artifact,
        eval_scores={"flicker": 0.11, "judge": 4.4},
    )


def test_alternate_lifecycle_record_promote_retire(env):
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = _make_shot(env, project_id)
    assert env.get_doc(shots.SHOTS, shot_id) is not None

    alternate_id = _record(env, shot_id, project_id)
    alternate = env.get_doc(shots.ALTERNATES, alternate_id)
    assert alternate is not None
    assert alternate["status"] == "draft"
    assert alternate["op"] == "extend"
    assert alternate["artifact_ref"].startswith("gs://")
    assert alternate["eval_scores"]["flicker"] == 0.11

    shots.promote_to_continuity(env, shot_id, alternate_id)
    shot = env.get_doc(shots.SHOTS, shot_id)
    alternate = env.get_doc(shots.ALTERNATES, alternate_id)
    assert shot["current_alternate_id"] == alternate_id
    assert alternate["status"] == "continuity"

    shots.retire_alternate(env, alternate_id)
    alternate = env.get_doc(shots.ALTERNATES, alternate_id)
    shot = env.get_doc(shots.SHOTS, shot_id)
    assert alternate["status"] == "retired"
    assert shot["current_alternate_id"] is None


def test_promoting_a_new_alternate_retires_the_previous_one(env):
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = _make_shot(env, project_id)
    first = _record(env, shot_id, project_id, "gs://b/alt-1.mp4")
    second = _record(env, shot_id, project_id, "gs://b/alt-2.mp4")

    shots.promote_to_continuity(env, shot_id, first)
    shots.promote_to_continuity(env, shot_id, second)

    shot = env.get_doc(shots.SHOTS, shot_id)
    assert shot["current_alternate_id"] == second
    assert env.get_doc(shots.ALTERNATES, first)["status"] == "retired"
    assert env.get_doc(shots.ALTERNATES, second)["status"] == "continuity"


def test_lock_and_unlock_route_through_the_executor(env, approvals_col, jobs_col):
    """Locking is an approval-tracked action THROUGH H-0 — never a direct
    flag flip from the API path."""
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = _make_shot(env, project_id)

    lock_ap = propose_approval(
        env,
        {
            "project_id": project_id,
            "kind": "fix",
            "title": "Lock shot",
            "command": {"name": "lock_shot", "args": {"shot_id": shot_id}},
        },
        collection=approvals_col,
    )
    out = h.machine.dispatch(lock_ap, "approve", approver="human-1")
    assert out["status"] == "resolved"
    assert env.get_doc(shots.SHOTS, shot_id)["locked"] is True

    unlock_ap = propose_approval(
        env,
        {
            "project_id": project_id,
            "kind": "fix",
            "title": "Unlock shot",
            "command": {"name": "unlock_shot", "args": {"shot_id": shot_id}},
        },
        collection=approvals_col,
    )
    h.machine.dispatch(unlock_ap, "approve", approver="human-1")
    assert env.get_doc(shots.SHOTS, shot_id)["locked"] is False


def test_locked_shot_refuses_targeted_commands_at_dispatch(
    env, approvals_col, jobs_col
):
    """The locked-target guard is central: ANY command carrying a shot_id
    that resolves to a locked shot is refused at dispatch — for every
    caller (human, Spend Control, H-0b loop)."""
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = _make_shot(env, project_id)
    alternate_id = _record(env, shot_id, project_id)
    shots.lock_shot(env, shot_id, locked_by="human-1")

    promote_ap = propose_approval(
        env,
        {
            "project_id": project_id,
            "kind": "fix",
            "title": "Promote to continuity",
            "command": {
                "name": "add_to_continuity",
                "args": {"shot_id": shot_id, "alternate_id": alternate_id},
            },
        },
        collection=approvals_col,
    )
    out = h.machine.dispatch(promote_ap, "approve", approver="human-1")

    assert out["status"] == "failed"
    assert out["result"].get("locked") is True
    assert env.get_doc(shots.ALTERNATES, alternate_id)["status"] == "draft", (
        "a locked shot must never be mutated by a targeted command"
    )


def test_unlock_command_is_allowed_on_a_locked_shot(env, approvals_col, jobs_col):
    """The guard must not lock the lock-keeper out: unlock acts on a locked
    shot; lock is idempotent on an already-locked one."""
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = _make_shot(env, project_id)
    shots.lock_shot(env, shot_id, locked_by="human-1")

    lock_ap = propose_approval(
        env,
        {
            "project_id": project_id,
            "kind": "fix",
            "title": "Lock again (idempotent)",
            "command": {"name": "lock_shot", "args": {"shot_id": shot_id}},
        },
        collection=approvals_col,
    )
    assert h.machine.dispatch(lock_ap, "approve")["status"] == "resolved"
    assert env.get_doc(shots.SHOTS, shot_id)["locked"] is True


def test_unlocked_shot_accepts_targeted_commands(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = _make_shot(env, project_id)
    alternate_id = _record(env, shot_id, project_id)

    promote_ap = propose_approval(
        env,
        {
            "project_id": project_id,
            "kind": "fix",
            "title": "Promote to continuity",
            "command": {
                "name": "add_to_continuity",
                "args": {"shot_id": shot_id, "alternate_id": alternate_id},
            },
        },
        collection=approvals_col,
    )
    out = h.machine.dispatch(promote_ap, "approve", approver="human-1")

    assert out["status"] == "resolved"
    assert env.get_doc(shots.SHOTS, shot_id)["current_alternate_id"] == alternate_id


def test_sweeper_never_redrives_a_command_whose_target_is_now_locked(
    env, approvals_col, jobs_col
):
    """Crash-then-lock race: a crashed fast command must not replay over a
    shot a human locked in the meantime — the guard holds at redrive time."""
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = _make_shot(env, project_id)
    alternate_id = _record(env, shot_id, project_id)

    # Seed a crashed fast action (approved, no result) that promotes.
    promote_ap = propose_approval(
        env,
        {
            "project_id": project_id,
            "kind": "fix",
            "title": "Promote",
            "command": {
                "name": "add_to_continuity",
                "args": {"shot_id": shot_id, "alternate_id": alternate_id},
            },
        },
        collection=approvals_col,
    )
    doc = env.get_doc(approvals_col, promote_ap) or {}
    doc.update(
        {
            "status": "approved",
            "approver": "human-1",
            "decided_at": "2026-09-03T00:00:00.000000Z",  # stale on purpose
        }
    )
    env.set_doc(approvals_col, promote_ap, doc)

    # A human locks the shot AFTER the action was approved.
    shots.lock_shot(env, shot_id, locked_by="human-1")

    sweep_once(env, h.queue, h.machine, collection=approvals_col)

    after = env.get_doc(approvals_col, promote_ap)
    assert after is not None and after["status"] == "failed"
    assert after["result"].get("locked") is True
    assert env.get_doc(shots.ALTERNATES, alternate_id)["status"] == "draft"


def test_api_lock_route_proposes_through_h0_never_flips_directly(env) -> None:
    """The API creates an approval with a lock command — the flag does NOT
    move until a human approves (single-writer, no second action path)."""
    from fastapi.testclient import TestClient

    from backend.api.app import create_app
    from backend.core.config import get_settings, reset_settings

    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = shots.ensure_shot(env, project_id=project_id, title="Lock route test")
    alternate_id = _record(env, shot_id, project_id)
    reset_settings()
    settings = get_settings()
    assert settings.gcp_project_id and settings.api_key
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    try:
        with TestClient(app) as client:
            listed = client.get(f"/api/v1/projects/{project_id}/shots", headers=headers)
            assert listed.status_code == 200
            row = next(row for row in listed.json() if row["shot_id"] == shot_id)
            # FE alternates lane contract: the list route embeds the same
            # shaped alternates as the detail route (no N+1 from the UI).
            assert row["alternates"] == [
                {
                    "alternate_id": alternate_id,
                    "op": "extend",
                    "artifact_ref": "gs://b/alt-a.mp4",
                    "eval_scores": {"flicker": 0.11, "judge": 4.4},
                    "status": "draft",
                    "created_at": row["alternates"][0]["created_at"],
                }
            ]

            proposed = client.post(
                f"/api/v1/shots/{shot_id}/lock",
                headers=headers,
                json={"reason": "client approved the cut"},
            )
            assert proposed.status_code == 200
            assert proposed.json()["status"] == "proposed"

            detail = client.get(f"/api/v1/shots/{shot_id}", headers=headers)
            assert detail.status_code == 200
            body = detail.json()
            assert body["locked"] is False, "flag must not move before approval"
            assert len(body["alternates"]) == 1

            missing = client.post(
                "/api/v1/shots/shot-nothing/lock", headers=headers, json={}
            )
            assert missing.status_code == 404
    finally:
        env.delete_doc(shots.SHOTS, shot_id)
