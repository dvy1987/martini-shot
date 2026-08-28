# AGENTS.md — Martini Shot

## Skill Invocation — Non-Negotiable
Skills in `.agents/skills/` (and global `~/.agents/skills/`) are mandatory workflows, not optional reference. When a request matches a skill — by its `description` triggers or the Orchestration Map below — open that `SKILL.md` and follow its steps BEFORE answering or acting. This holds on every host that surfaces these skills, Cursor included.
- Match before acting: scan available skills before any non-trivial task.
- Invoking = opening `SKILL.md` and executing its workflow. Naming it, or saying you "would" use it, does not count.
- "Task seems simple" / "I already know how" is NOT grounds to skip.
- Skip a matching skill ONLY if the user explicitly says "don't use skills" / "skip the skill" / names a different tool.

## Project Overview
Martini Shot (codename `post-command`): an observability-native post-production cockpit (Agentic Cinema hackathon, Grafana track, deadline 2026-09-09). Python 3.12/FastAPI backend on Cloud Run drives 16 instrumented "station" jobs over a Firestore lease queue; React+Vite frontend (Replit-hosted) visualizes them; an ADK supervisor agent diagnoses and fixes failures via Grafana Cloud MCP. Non-standard: zero-mock integrity law (constitution C-1.*), TDD for deterministic code vs EDD eval suites for generative features, telemetry as a product feature (C-4.*).

## Key Commands
```
Install:     python -m pip install -r requirements-dev.txt   (then: python -m pre_commit install)
Lint:        make lint            (ruff check + format check)
Type check:  make typecheck       (mypy backend/)
Test single: python -m pytest tests/test_<module>.py -q
Test all:    make test
Eval check:  make eval-check      (thresholds.yaml structure gate, C-3.4)
Integrity:   make integrity       (C-1.2 no-mocks grep)
Full gate:   make check           (run before declaring ANY task done)
```
Frontend commands (npm) land with scaffold task C-1 — see `frontend/AGENTS.md`.

## Project Structure (non-obvious only)
- `docs/constitution.md` — BINDING invariants C-1..C-8; every plan task cites it; violations reject work.
- `docs/plans/2026-08-26-post-command-plan.md` — task IDs (A-1, D-3, G0...) are the shared language; read only the phase you execute.
- `ideas/AO-STATION-MAP.md` — mission briefing; Amendments A1–A4 (Integrity Charter) binding.
- `backend/stations/<name>/` — 16 station dirs; each gets a README when built (C-8.1). `spend/` = Spend Control (acts: throttle/stop/approve).
- `backend/evals/` — EDD suites: datasets/, metrics/, thresholds.yaml (numeric bars, C-3.4).
- `fixtures/` — labeled synthetic INPUT media only, per-file README (C-1.3). Committed. Never faked functionality.
- `docs/evidence/<task-id>/` — DoD evidence per task; gates G0–G5 require it (C-3.5).
- `infra/grafana/` — dashboards + alert rules as code (C-4.5).
- `frontend/` + `backend/` deploy independently (C-6.1); only contract is versioned `/api/v1` HTTP + SSE.
- `docs/memory/` — agent continuity (Session Lifecycle below).

## Code Style
Canonical backend pattern — every station/job handler conforms:
```python
@tracer.start_as_current_span("station.loudness.run")
async def run_loudness(job: Job) -> JobResult:
    with metrics_duration(job.station):            # pc_job_duration_seconds
        result = await measure(job.input_refs)     # real work, no mocks (C-1.1)
        job.cost_micros += estimate_cost(result)   # integer micro-units (C-6.4)
        log.info("loudness done", extra={"job_id": job.id, "station": job.station,
                                         "project_id": job.project_id})  # C-4.2
    return JobResult(status="pass", cost_micros=job.cost_micros)
```
- ruff format + ruff check; mypy (config in `mypy.ini`). UTC ISO-8601 timestamps; money as integer micro-units (C-6.4).
- TypeScript strict in `frontend/`, no `any`. No LLM call inside an HTTP request path >30 s (C-6.5) — long work goes through jobs.

## Non-Obvious Patterns
- **Zero mocks anywhere (C-1.*, Integrity Charter A2):** no fake functionality, no mock backends, no canned outputs. Labeled synthetic INPUT fixtures are fine; faked capability is deception, flagged CRITICAL. `make integrity` + pre-commit enforce the grep.
- **TDD vs EDD split (C-3.*):** deterministic modules get failing-test-first; generative capabilities get dataset+metric+numeric threshold BEFORE the feature. No eval, no merge.
- **Grafana is the audit trail (C-4.3):** every autonomous agent intervention writes an annotation referencing `job_id`; incidents for quarantine/spend enforcement. Metric/annotation contracts live in spec §6 — never invent new naming schemes.
- **Lease-based jobs (C-6.3):** Firestore transactions, idempotent per `job_id`; retries assumed. Never add a synchronous alternative.
- **Captions are a sub-check inside Delivery (S5)** — not a station, not a screen. Spend Control is a station that ACTS.
- **Scope frozen in 4 stages (Amendment A4):** Stage 1 core → 2 compliance → 3 audio/library → 4 editing. Re-cutting stages needs owner amendment; build stations via plan tasks, never improvised features.
- **MCP auth duality (ADR 0001):** hosted Grafana MCP = one-time browser OAuth (dev machine ok); OSS `grafana/mcp-grafana` + service-account token = headless fallback behind `MCP_MODE`.

## Boundaries

### Allowed without asking
- Reading anything; running make/pytest/ruff/mypy targets; file-scoped test runs
- Writing tests (TDD/EDD), eval datasets, fixtures with README (C-1.3), docs, ADRs, memory
- Security, secrets handling, auth wiring (owner granted full autonomy)
- Station scaffolding per plan tasks; new files in standard directories

### Ask first (owner is non-technical: present plain-language trade-offs, product impact)
- Deploying/provisioning (Cloud Run, Replit, Firebase, GCP/Grafana resources) or anything that bills credits (eval batches > $5 also need `--yes`, C-7.2)
- Frontend visual design decisions (run the frontend-design chain; approve the "feels like X" direction)
- New dependencies or dev tooling; deviations from the approved plan (reordering across gates, scope changes)

### Never
- Mock, stub, or simulate AI functionality; commit fake outputs or replayed data presented as live (C-1.*)
- Non-Google AI models/APIs at runtime; non-MCP Grafana usage (C-2.*)
- Commit secrets, `.env`, tokens, service-account JSONs (C-5.1)
- Edit approved spec/plan without an owner-approved amendment (spec §11)

## User Context
- **Strong at:** product story, film/post-production domain judgment, demo narrative, scoping.
- **Agents lead on:** everything technical — architecture, code, testing, DevOps, security — deciding with rigor (below) and translating trade-offs to plain language.
- **Working style:** owner approves product implications, not code. Demo beats (batch: 8–10 eps × ~30 langs) matter more than feature count. Submit ≥24 h before deadline.

## Agent-Led Architecture & Design
The owner cannot evaluate architecture/design choices, so the agent OWNS them — apply full rigor, never pick the first option, never defer the technical call to the owner.

Before ANY architectural decision (data model, API/module boundaries, framework/library choice, state, auth, persistence, deployment, scaling):
1. `brainstorming` — frame 2–4 approaches, get direction approval.
2. `deep-thinking` (`first-principles`, `pre-mortem`, `assumption-mapping`, `second-order`) — pressure-test before committing.
3. `api-and-interface-design` for boundaries; `source-driven-development` to ground framework choices in official docs (cite versions).
4. Present a plain-language trade-off (options + cost/speed/risk/user impact); get approval on the PRODUCT implication, not the code.
5. Record via `architectural-decision-log`. Never ship a decision the owner couldn't explain in one plain sentence.

Before ANY UI/UX work: `frontend-design` → `design-direction` (2–3 distinct directions) → `design-system` (DESIGN.md + tokens) → build → `design-review` (must pass). Translate the chosen direction into product terms for approval.

## Session Lifecycle — Mandatory

### Session Start
**The first user message in any session triggers `memory-startup`, regardless of content** — a bare "hi", a task, an error log, all count. Run it BEFORE answering, before any other skill, before any task action:
1. Invoke `memory-startup` (bounded load: routing index + latest handoff + relevant decisions only — never every file).
2. Read the latest entry in `docs/memory/agent-handoffs.md` for expected next steps.
3. Run `git status` + `git log --oneline -5`; confirm repo state matches the handoff.
4. In 2–4 lines state: (a) recovered context, (b) planned next action, (c) drift from handoff. Wait for confirm/redirect.
Skip only if the user says "fresh start" / "ignore prior context" / "skip memory". No prior memory: report that and continue. If `memory-startup` already ran this conversation, it self no-ops.

### During & End of Session
Memory sub-skills auto-fire at producer events, not only when asked: after writing a changelog/ADR/spec/plan, after a major commit (>20 files or breaking), after creating/editing a skill, and before session end — consult the `memory` skill's Mandatory Auto-Trigger Checkpoints and invoke the listed sub-skill. Skipping a checkpoint loses durable context.

## Orchestration Map

### Phase: Agent Harness (run once per project)
Trigger: after project-setup / retroactive backfill, OR agent misbehavior (see harness-engineering)
Flow: harness-generation → eval-rubric-design → eval-pipeline → [harness-evolution when agents keep failing]. Manifest: `docs/harness/manifest.json` · eval stub: `docs/harness/eval-interface.md` · drift gate: `make harness-check` (governance: `docs/harness/governance.md`).
Plain language: "Agent reliability setup — rules + checks so agents follow the project and improve when they fail."

### Phase: SDD Execution (this project's main loop)
Trigger: any build work. Constitution + spec + plan are APPROVED.
Flow: `/tasks` (plan → agent-pickable task list) → `/analyze` (spec-crosscheck gate) → `/implement` (test-driven-development + eval suites) per slice.
- Every task's DoD evidence goes to `docs/evidence/<task-id>/`; failed gate = fix or demote, never mock (C-1.*).
- **G0 spike is the FIRST build action** (real Gemini bg-swap on 3 frames) — nothing generative starts before it passes.
- Parallel tracks per the plan's Parallelization Map (Phase 1: A∥B∥C; Phase 2: deterministic ∥ EDD once A-4 lands).

### Phase: Amendment
Trigger: a gap or ruling forces a spec/plan change
Flow: propose diff → owner approves → edit spec/plan → log in `docs/skill-outputs/SKILL-OUTPUTS.md` + AO amendments. Never edit silently.

### Phase: Review & Release
Trigger: gate passed / feature complete
Flow: technical-debt-audit (after gates) → generate-changelog → gate evidence check → next phase. G5 freeze: video recorded only from the running product.

### Thinking (available in any phase)
Trigger: uncertainty, high-stakes decision, "think about this"
Flow: deep-thinking (auto-selects: inversion, pre-mortem, assumption-mapping, etc.)

## Skill Reference
Security: `secure-skill` family, `app-security-hardening` · Testing: `test-driven-development`, `eval-*` family · Observability: `agent-observability`, `run-trace`, `fault-localize` · Frontend: `frontend-design` + sub-skills · SDD router: `spec-driven-development` · Unsure which skill? `project-orchestrator`.
