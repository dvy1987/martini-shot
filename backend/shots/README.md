# Shots & Alternates station (AL-1)

Shot locking and the alternates model (plan task AL-1, spec §5 Stage 1a,
Amendment A8).

## What lives here

- `lifecycle.py` — Firestore-backed lifecycle over two collections:
  - `pc-shots`: `{shot_id, project_id, title, locked, locked_by, locked_at, current_alternate_id}`
  - `pc-alternates`: `{alternate_id, shot_id, project_id, op, artifact_ref, eval_scores, status}`
    with `status ∈ {draft, continuity, retired}`.

## The rules

1. **Never overwrite.** Every generated clip is recorded via
   `record_alternate` as an ALTERNATE in `draft`. Promoting it to the shot's
   current cut goes through the `add_to_continuity` command; the previous
   cut's alternate is retired (kept, so revert is possible).
2. **Locks are central, not per-caller.** `lock_shot` sets `locked` on the
   shot document; the approval executor's locked-target guard
   (`ApprovalStateMachine._locked_target_result`) refuses ANY command whose
   `args.shot_id` resolves to a locked shot — for humans, Spend Control and
   the H-0b deliberation loop alike. Only `lock_shot`/`unlock_shot` are
   exempt (`LOCK_COMMANDS`), because unlock is the whole point.
3. **Continuity changes are approval-tracked through H-0.** There is no
   second action path: `add_to_continuity` / `remove_from_continuity` are
   fast-lane idempotent commands on `default_registry`
   (`backend/approvals/commands.py`); the API only *proposes* (see spine
   routes `POST /api/v1/shots/{shot_id}/lock|unlock`).

## API surface (`/api/v1`)

- `GET /projects/{project_id}/shots` — shot list with lock + current-cut state
- `GET /shots/{shot_id}` — shot detail with all alternates
- `POST /shots/{shot_id}/lock` / `POST /shots/{shot_id}/unlock` — propose an
  approval (decision via the standard approvals decision endpoint)

## Consumers

- D-9 (Extend) records its renders as alternates with `op="extend"`.
- H-1h Continuity Agent reasons over locks + alternates (gated on this task).
- H-0b's continuity adds ride the same approval-tracked commands.
