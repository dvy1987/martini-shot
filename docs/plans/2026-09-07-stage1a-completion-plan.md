# Stage 1a Completion Plan — handoff for the next agent

Written 2026-09-07 by the previous agent. **Historical execution plan.**

**Current-state reconciliation, 2026-09-08:** The main Stage 1a lookers, walk-away finishing path, live spend-pricing and rank evidence, supervisor retry evidence, current Cloud Run deployment path, and current judge-facing documentation have since landed. The opening handoff below still contains the older “96 jobs pending” and “live rank/spend pending” assumptions. Treat those paragraphs as historical provenance, not as current status. For current truth, use `README.md`, `docs/judge-guide.md`, `docs/pending-work.md`, and `docs/memory/current-state.md`.

The remaining active items from this plan are the full-gate coverage gap, any unfinished E-3 evidence not already archived, and the final running-product rehearsal. Do not re-run billable evaluations that already passed without a new owner-approved reason.

---

## 0. Read first (in this order, ~10 min)

1. `AGENTS.md` (root) + `backend/AGENTS.md` — constitution rules C-1..C-8,
   TDD/EDD split, zero-mock law.
2. This document, fully.
3. `docs/memory/agent-handoffs.md` — top entry only.
4. `docs/plans/2026-08-26-post-command-tasks.md` — only the A10-4 row (done)
   and the G3 / H-1h/i/j rows.

## 1. Historical state at handoff

The following section records what was true when this plan was written. It is retained for provenance and is not a current release checklist.

- HEAD on `main`, everything pushed. All work committed.
- **96 REAL billable jobs are sitting in the Firestore lease queue**
  (E-3 batch: 8 episodes × 3 languages × 4 stations, est. ~$0.10 total,
  owner-approved). They have NOT been processed — no worker has run since
  seeding. This is the first thing to do.
- Owner pre-approved the E-3 billable run. Owner wants ALL raw outputs
  archived under `docs/evidence/E-3/raw/` for the demo.
- A shared API-resilience layer exists and is tested
  (`backend/core/api_resilience.py`, `tests/test_api_resilience.py`, 9 green)
  but call sites are NOT yet rewired (see Workstream A1).

## 2. Environment rules (Windows, PowerShell 5.1) — memorize

- **No `&&` or `||`.** Chain with `;`. Check `$LASTEXITCODE` when it matters.
- Python: always `.venv\Scripts\python.exe -m ...` (never bare `python`).
- Tests: `.venv\Scripts\python.exe -m pytest tests\test_<name>.py -q`
- Gates before declaring any task done: `.venv\Scripts\python.exe -m ruff format <files>` then `ruff check` then `mypy backend/` then full pytest.
- Pre-commit hook runs ruff-format on staged files. Format BEFORE `git add`.
  If a commit is aborted by the hook, `git status`, re-`git add`, retry. If
  PowerShell prints exit 1 with stderr noise, verify with `git log -1` —
  commits often succeed anyway.
- Commit style: `feat(<scope>): <imperative summary>` — match `git log --oneline -5`.
- Push after every slice. Never force-push.

## 3. Workstream A — E-3 batch execution (do this FIRST)

### A1. Rewire API call sites through the shared resilience layer (~30 min, TDD already done)

`backend/core/api_resilience.py` provides `call_with_resilience(fn, *,
is_transient, retry_after, attempts=4, base, cap, jitter, sleep)`. Rule:
**only idempotent calls may be wrapped** (GETs, synthesize, renders).
Read it, then:

1. `backend/core/generative.py` — 4 raw `urllib.request.urlopen` sites:
   - TTS synthesize POST (~line 95): DELETE its inline 5xx-only retry loop;
     wrap the request in `call_with_resilience` (default predicates already
     classify `HTTPError` 429/5xx + `URLError` and honor `Retry-After`).
   - artifact URI GET (~line 208): same wrapper.
   - `veo_extend._call` (~line 276): same wrapper (predictLongRunning +
     fetchPredictOperation are idempotent).
   - Veo GCS video GET (~line 312): same wrapper.
   Suggested helper inside generative.py:
   `_resilient_urlopen(request, timeout)` that calls
   `call_with_resilience(lambda: urllib.request.urlopen(request, timeout=timeout))`.
   Read the response INSIDE the wrapped lambda so the whole urlopen+read is
   one try-unit.
2. `backend/supervisor/otel_ai.py` `run_agent_call` (~line 116): replace the
   inline `for attempt in range(3)` 429-only loop with
   `call_with_resilience(..., attempts=3, is_transient=lambda e: "429" in str(e) or "503" in str(e))`.
3. Add one test per site is NOT required (layer is unit-tested); instead run
   the full suite + `make lint` + `make typecheck`.
4. Commit: `feat(core): route all outbound API calls through api_resilience`.

### A2. Historical E-3 batch instruction: process the queued jobs

- The worker runs inside the API lifespan (`backend/api/app.py`, `_run_worker`)
  OR can be driven directly. Preferred: a tiny runner
  `scripts/e3_run_worker.py` that imports the real queue + `worker_loop`
  from `backend/jobs/worker.py` the same way `scripts/g2_gate.py` imports
  `process_job_id`. Run it in a background terminal:
  `.venv\Scripts\python.exe scripts\e3_run_worker.py`
- Do NOT re-run `scripts/e3_seed.py` unless you verified the batch is
  missing jobs — it is idempotent but re-submits cost-check anyway. Read it
  before deciding.
- Monitor: poll the `pc-jobs` Firestore collection for
  `batch_id = "e3-..."` (see `fixtures/e3_batch/manifest.json` and
  `docs/evidence/E-3/seed.json` for the exact ids) counting terminal states
  (`pass`/`fail`/`needs_human`). Expect 96 terminal within minutes (24 dub
  jobs are the expensive ones: Chirp TTS per line).
- If a job fails with a transient HTTP error, A1's wrapper should have
  absorbed it; a persistent failure is a REAL failure — record it, do not
  force-retry more than the queue's own attempt policy allows.

### A3. Archive raw outputs (owner directive — do not skip)

- Copy every raw artifact the run produces into `docs/evidence/E-3/raw/`:
  dub WAVs (download from GCS `gs://martini-shot-media/...` paths referenced
  in job results), per-job result JSONs, and a batch summary JSON
  (counts by station × status, total `cost_micros`).
- Small files (<2MB each) go into git directly; note GCS paths in the
  summary for anything larger.
- Evidence doc: `docs/evidence/E-3/README.md` — one page: manifest, cost,
  outcomes, links to raw files. This is the demo story (8 eps × 3 langs).

### A4. Commit + push

`feat(e3): batch run complete - raw outputs archived for demo` — include
runner script, evidence, raw archive. Update the tasks-plan E-3 row to ✅.

## 4. Workstream B — Stage 1a completion (H-1h, H-1i, H-1j)

Datasets + thresholds ALREADY seeded (verify: `backend/evals/datasets/
continuity_judgment.jsonl`, `creative_finishing_judgment.jsonl`,
`visual_qc_judgment.jsonl` + matching entries in
`backend/evals/thresholds.yaml`). Do NOT re-seed; do NOT edit thresholds
unless a live eval run proves a miss (rule: every tuning traces to a real
model miss — never tune on vibes).

Build each agent by EXACTLY copying the 9×-proven pattern. Reference
implementations (read one before starting):
`backend/supervisor/station_agents/dub_qc.py` (simplest),
`caption_remediation.py` (closed-loop), `extend_qc.py` (two-strike gates).

Pattern per agent (all steps required):

1. **TDD first**: `tests/test_<agent>.py` — test SCHEMA validation
   (`validate_station_decision`, field is `decision` NOT `disposition`;
   `StationDecision` is a dataclass — `.decision`), prompt construction
   contains the dataset's case facts, fence-tolerant JSON parse, fail-loud
   on invalid output, exactly ONE `run_agent_call` per invocation, and the
   agent's HARD GATE (below) enforced in code, not just prompt.
2. **Agent module** `backend/supervisor/station_agents/<name>.py`:
   SCHEMA dict → `build_prompt(context)` → one `run_agent_call` →
   `validate_station_decision` → `deterministic_suggestion` fallback ladder.
3. **Eval script** `scripts/<agent>_eval.py` copying
   `scripts/extend_qc_eval.py` — runs the dataset through the REAL model
   (billed), scores per-case accuracy, writes JSONL to
   `docs/evidence/<task>/`.
4. **Validation run**: must hit the threshold (≥0.8 mean_case_accuracy) on
   the dataset. If below: read every miss, fix the PROMPT (add an explicit
   decision rule), re-run. If a fix overshoots (previously-passing case
   flips), the rule was too vague — replace it with an ORDERED decision
   ladder (see `spend_steward.py` for the pattern). Iterate honestly.
5. **Official gate**: 3 consecutive runs at/above threshold. All 3 JSONLs
   archived to `docs/evidence/<task>/`.
6. Commit per agent: `feat(a10-x/<agent>): ...` + evidence commit. Push.

The three agents and their HARD GATES (gate in CODE — the constitution
checks these):

- **H-1h Continuity Agent** (`continuity_judgment` dataset): read-only
  alternates/locks tools. HARD GATE: it must never propose an action that
  targets a locked cut, except `add_to_continuity` (approval-tracked).
  Test: a prompt containing a locked-cut target yields either a refusal
  suggestion or a compliant action — never a direct overwrite.
- **H-1i Creative Finishing Agent** (`creative_finishing_judgment`): 
  draft-first HARD GATE: any render proposal must be flagged
  `draft: true` with draft-tier cost estimate; master-tier proposals are
  rejected in code until a draft passes QC.
- **H-1j Visual QC Agent** (`visual_qc_judgment`): HARD GATE: a draft that
  breaches QC limits is never waved through (status must be
  fail/bounded_revision/needs_human — never pass with a breach present).

After all three: run `make check` (full gate) + `make eval-check`.

## 5. Workstream C — G3 gate (Stage 1 completion bar)

G3 = the guaranteed-fallback submission quality bar:
1. Hero ops hold bars on ≥3 fresh shots (use E-3 outputs if they qualify —
   they are fresh).
2. Dub QC agent within thresholds on the E-3 batch evidence.
3. Raw evidence clips archived (A3 gives you this).
4. FE playable dub pair: pick ONE episode's original + dubbed WAV from
   `docs/evidence/E-3/raw/`, wire into the FE player view (there is
   existing dub-pair UI from earlier tasks — grep `dub` in `frontend/src/`).
   `npm run build` + `npm run typecheck` must pass.
Record `docs/evidence/G3/README.md` with links, then commit.

## 5. Historical post-Stage-1a queue

The following tasks were written before the current documentation and live-evidence updates. Use `docs/pending-work.md` for the current release decision.

- Phase 4 scoped: H-2/H-3/H-4 (morning report, Firebase sign-in, approval
  UI polish) — demo-scoped only.
- J-line: J-0..J-6 submission checklist, video recorded ONLY from the
  running product (G5 freeze).

## 7. Guardrails (violations = rejected work)

- NO mocks/stubs/simulated AI anywhere (C-1.*). `make integrity` must pass.
- Never edit approved spec/plan without owner-approved amendment.
- Billable evals > $5 need owner `--yes`. E-3's ~$0.10 run is pre-approved;
  anything NEW that bills beyond that: ASK.
- Never commit `.env`, tokens, service-account JSONs (C-5.1).
- Never auto-retry non-idempotent writes (annotations/incidents) — that is
  why `call_with_resilience` must not wrap MCP `call_tool`.
- Real model misses only drive prompt tuning. One miss = add one explicit
  rule; re-run; if another case flips, use an ordered ladder.

## 8. Known pitfalls from this session (already solved — don't rediscover)

- PowerShell `-replace` on JSON mangles escapes — edit JSON by hand or with Python.
- `LeaseQueue` → actual class is `FirestoreLeaseQueue`.
- lavfi `volume` is not an input option → use `-af volume=0.2`.
- `urllib.error.HTTPError` subclasses must subclass the REAL class for type-based classification.
- `StationDecision` contract field is `decision`, not `disposition`.
- Eval harness bug cost one billable run once (KeyError 'cues') — dry-run the eval script on 1 case before the full dataset.
