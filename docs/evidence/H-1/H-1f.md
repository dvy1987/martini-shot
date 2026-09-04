# H-1f — Deliberations surfacing: API, SSE, and the FE agent panel

Task: multi-agent supervisor plan, H-1f (frontend/agent panel + deliberation.completed SSE).
Method: TDD both sides (backend RED-first, FE vitest RED-first). No mocks; real Firestore docs.

## Contracts shipped

### Backend
1. **`GET /api/v1/projects/{project_id}/deliberations?job_id=`** (spine.py) — lists real
   `pc-deliberations` docs scoped to the project, optionally filtered to one job, newest
   first. Shaped as `{cycle_id, case_id, created_at, trigger, specialists, verdict,
   recommendation, status}`. Test: `test_spine_lists_deliberations_for_job` (RED 404 → GREEN).
2. **`on_complete` callback on `run_deliberation_cycle`** — after the record is persisted,
   the cycle hands the record to an injected callback (best-effort: a raising callback never
   fails the cycle). This is the wiring point for `hub.publish(project_id,
   "deliberation.completed", record)` when the worker path (H-0b / H-1g shadow run) invokes
   the cycle; no production caller exists yet, so nothing publishes today — the SSE event
   type is contracted on the FE and the payload is the full record. Test:
   `test_cycle_notifies_on_complete_for_sse` (RED unexpected-kwarg → GREEN).
3. **Record gains denormalized `project_id`** (from the trigger) so the project-scoped
   `list_where` query works.

### Frontend
1. **Types** (`types/api.ts`): `Deliberation`, `RankedAction`; `deliberation.completed`
   added to the `SseEvent` union (payload = record).
2. **Client logic TDD** (`lib/deliberations.ts` + `lib/deliberations.test.ts`):
   `upsertDeliberation` (cache upsert by cycle_id, no mutation), `dissentForJob`
   (dissent lines from the newest deliberation for a job), `deliberationFromSseEvent`
   (strict guard; malformed payloads rejected).
3. **Endpoint** (`api/endpoints.ts`): `listDeliberations(projectId, jobId?)`.
4. **`AgentPanel`** (`components/AgentPanel.tsx` + test): renders the real record —
   specialists consulted (✓ = verifier-approved), rejected claims with reasons, ranked
   actions with cost + reversibility, dissent block (danger). Empty record renders
   "no ranked actions" — nothing invented.
5. **`InvestigationDrawer`**: new optional `deliberation` prop; panel renders under the
   case file when a deliberation exists for the job, silent otherwise.
6. **`TimelineRoute`**: fetches `listDeliberations(projectId, inspectedJobId)` while the
   drawer is open; newest record goes to the panel.
7. **`App.tsx`**: `deliberation.completed` SSE → upserts into the
   `["deliberations", projectId]` react-query cache (shared key with the fetchers).
8. **`ApprovalsRoute` ApprovalCard**: disagreement line — when the newest deliberation for
   the approval's job carries dissent lines, they render as a danger-bordered
   "Agents disagree: …" note. Dissent is an exception-first signal on the decision surface.

## Gates
- Backend: `tests/test_deliberation.py` 9/9 (2 new), `test_shot_locking.py` + `test_errors.py`
  green after the spine change (20/20 across the three files).
- ruff check + format clean; mypy clean on `spine.py` + `deliberation.py`.
- Frontend: vitest 76/76 (new: 3 lib tests + 2 AgentPanel + 1 drawer integration),
  `tsc --noEmit` clean, eslint clean, `npm run build` succeeds.
