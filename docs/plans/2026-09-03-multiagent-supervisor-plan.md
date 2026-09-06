# Plan: Multi-Agent Specialist Team for the Post Supervisor (Amendment A9)

Date: 2026-09-03 | Status: Approved for execution | Owner ruling: multi-agent structure wanted (2026-09-03)
Supersedes: nothing removed — **amends** `docs/plans/2026-09-02-h0b-budgeted-supervisor-plan.md` in place (one addendum, see §7); does not touch its owner rulings (no action cap, envelope covers continuity, self-correction rules).
Depends on: H-0 (approval→action executor — **DONE**, `docs/evidence/H-0/`), B-2/B-2b (Grafana MCP tools — done), B-3 (AI Observability — done), D-1/D-2/D-4/D-7 (Stage-1 stations whose output the specialists read — done).
Consumed by: H-0b (budgeted autonomy loop — plan of record, unchanged mechanics, new evidence source).

## 0. Where this came from, and my critical review of it

Another agent proposed a hierarchical specialist team (Post Supervisor → Reliability
Investigator / Delivery QC / Localization / Spend Guardian → Verification Agent → H-0) plus an
8-step build order. The owner asked me to review it critically, not rubber-stamp it, and turn it
into an executable plan. Verdict: **the shape is right and I'm building it**, with five concrete
deviations, each because I checked it against what's actually in this repo and this SDK version,
not against a generic idea of "multi-agent":

1. **Localization Agent is deferred, not built now.** Its whole job is judging dub timing/voice
   quality — but Dub QC (E-2) hasn't shipped; there is no dubbed artifact in the system yet. Building
   an agent with nothing real to specialize in is an empty shell — not mocked AI (C-1.1 is about fake
   *outputs*, not empty scope) but it wastes a build slot on a persona with zero live capability. It
   ships in the same slice as E-2, using the exact pattern this plan establishes for the other four.
2. **No ADK `Runner`/`sub_agents` transfer of control.** I checked: nothing in this repo has ever
   invoked `google.adk.runners.Runner` — `build_supervisor()` constructs an `LlmAgent` object that is
   never run. The one real, working, tested invocation pattern is `otel_ai.py::run_supervisor_text`,
   a direct `google.genai.Client().models.generate_content()` call (proven in B-3, `cost_micros=400`
   evidence on file). `google-genai==2.20.0`'s `GenerateContentConfig` already accepts plain Python
   callables in `tools=` (automatic function calling) and `responseSchema`+`responseMimeType` for
   typed JSON output — verified against the installed SDK, not assumed. Building specialists as
   direct calls through a small extension of the already-proven B-3 pattern is materially lower risk
   under a 5-day runway than debugging a brand-new ADK Runner/session-service integration from
   scratch. `LlmAgent`/ADK scaffolding stays in the repo for a future live-chat surface; it is not
   the transport for this deliberation pipeline.
3. **Parallelism is real `asyncio.gather`, not "the model decided to call two tools at once."**
   Specialist fan-out is deterministic Python, not dependent on Gemini's parallel-function-call
   heuristics. This is also what makes routing (who gets consulted) TDD-testable instead of only
   EDD-judged — only the *content* of a specialist's finding is a judgment call.
4. **Verification Agent's rejection is a hard filter, not a down-weight.** A rejected finding's
   proposed actions never reach the ranked list. This mirrors the reversibility rule the owner
   already set in H-0b ("not-reversible candidates never enter the ranked list at all — this is
   stronger than weighted down") — same shape, applied to evidence quality instead of reversibility.
5. **H-0b's document is not rewritten.** Its owner rulings (no action-count cap, envelope covers
   continuity adds, self-correction can't re-fight a human) stand verbatim. This plan only changes
   *where H-0b's step 2 ("collect candidates") gets its evidence from* — see §7.

Everything else in the source proposal — the agent roster's professional-judgment framing ("agents
represent domains, not one-per-station"), typed findings that can't mutate jobs, only H-0 executes,
parent `deliberation_id` + child spans, FE must show who participated and where they disagreed, and
the 8-step build order — is sound and kept.

## 1. What's real today (verified 2026-09-03, not assumed)

- `backend/supervisor/agent.py::build_supervisor()` — one `LlmAgent`, one flat `ToolRegistry`, never
  actually run by anything in the codebase (grep-verified: `build_supervisor` has no caller).
- `backend/supervisor/otel_ai.py::run_supervisor_text()` — the one proven live-call pattern: direct
  `genai.Client`, `TEXT_MODEL` (`gemini-3.7-flash`, thinking HIGH), records `cost_micros`/tokens/
  latency via `record_ai_usage`. This is the pattern every specialist call extends.
- `backend/supervisor/registry.py` / `autonomy.py` — tool registration + act-class gating, reusable
  as-is for narrower per-specialist registries (specialists simply never register an `act=True` tool).
- `backend/approvals/{machine,commands,sweeper}.py` — H-0, done, the only action-dispatch path.
- `google-adk==2.8.0` provides `LlmAgent`, `SequentialAgent`, `ParallelAgent`, `LoopAgent`,
  `AgentTool` — real primitives, unused so far. Noted for future use (§9 Non-Goals), not this slice.
- `google-genai==2.20.0`'s `GenerateContentConfig` accepts `tools: list[Callable]` and
  `responseSchema` — confirmed against the installed package, not the docs alone.
- Stage-1 station outputs a Delivery QC / Spend Guardian specialist would read are real and done:
  loudness (D-2), delivery+captions (D-4), Spend Control (D-7), ingest quarantine (D-1).
- `frontend/src/components/InvestigationDrawer.tsx` is the existing per-job case-file drawer — the
  natural home for "which agents looked at this, what they found, where they disagreed."
- SSE envelope (spec §7.1) is forward-compatible by contract ("clients MUST ignore unknown `type`
  values") — adding a new event type is additive, not a breaking change.

## 2. Architecture

```
 trigger (failed/stuck/quarantined job, QC score breach, spend signal — a system event, H-0b §Deliberation loop step 1)
                                   |
                         build_case(trigger)              <- deterministic, TDD (backend/supervisor/case.py)
                                   |
                         route_specialists(case)           <- deterministic table, TDD
                                   |
              +--------------------+--------------------+-----------------------+
              v                    v                     v                      v
   Reliability          Delivery QC Agent        Spend Guardian        (Localization Agent
   Investigator        (loudness/delivery/       (cost ledger,          — deferred to E-2,
   (Grafana MCP,        captions QC reports)      retry history,         same pattern)
    traces, logs,                                 Spend Control)
    job reads)
              |                    |                     |
              +--------------------+---------------------+
                                   | (asyncio.gather — real parallel Gemini calls)
                                   v
                     each returns a typed Finding
                     (claim + evidence_citations + proposed_actions; NO act-class tools)
                                   |
                                   v
                          Verification Agent
                 (challenges unsupported/stale/resolved claims;
                  rejection = hard filter, findings excluded, not down-weighted)
                                   |
                                   v
                         Post Supervisor synthesis
                (H-0b's existing leverage-ranking formula, now scored over
                 verified findings instead of raw telemetry — §7)
                                   |
                                   v
                    ranked Recommendation + DeliberationRecord
                    (Firestore pc-deliberations/{cycle_id} + Grafana annotation)
                                   |
                    +--------------+--------------+
                    v                             v
        ACT mode & envelope room:        propose-only / envelope empty:
        dispatch via H-0 (unchanged)     surface in approvals inbox (H-3)
                                          + morning report (H-2)
```

### 2.1 Data contracts — `backend/supervisor/case.py` (new)

```python
@dataclass(frozen=True)
class Claim:
    text: str
    evidence_ref: str  # trace_id | promql query+result | log line | firestore doc path
    confidence: Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ProposedAction:
    command_name: str  # matches an H-0 ApprovalCommand name — never invented ad hoc
    args: dict[str, Any]
    cost_estimate_micros: int
    reversible: (
        bool  # False => Verification/synthesis must exclude, never just down-rank
    )


@dataclass(frozen=True)
class Case:
    case_id: str
    version: int
    created_at: str  # UTC ISO-8601 (C-6.4)
    trigger: dict[str, Any]  # {kind, job_id?, project_id, station?, signal}
    evidence: dict[
        str, Any
    ]  # pre-fetched: job doc, recent QC report, spend snapshot — shared baseline


@dataclass(frozen=True)
class Finding:
    specialist: str  # e.g. "reliability_investigator"
    case_id: str
    claims: list[Claim]
    proposed_actions: list[ProposedAction]


@dataclass(frozen=True)
class Verdict:
    case_id: str
    rejected: list[tuple[str, str]]  # (claim evidence_ref, rejection reason)
    approved_specialists: list[str]
    overall_confidence: Literal["low", "medium", "high"]
```

`Finding`/`Verdict`/`Case` are plain dataclasses, not pydantic ADK schemas — they are produced from
`responseSchema`-constrained JSON (google-genai structured output) and parsed/validated on our side,
same trust boundary the project already applies to any external JSON (job docs, MCP tool results).

### 2.2 Invocation helper — extend `otel_ai.py`, don't fork it

Generalize `run_supervisor_text` into `run_agent_call(settings, *, span_name, persona, prompt,
tools=(), response_schema=None) -> dict` — same cost/token/latency instrumentation, same
`record_ai_usage`, parameterized persona/tools/schema so every specialist, the verifier, and the
supervisor synthesis step all go through **one** instrumented call site (keeps C-4.4 coverage total
by construction — no specialist can accidentally skip metering). `span_name` becomes a
`gen_ai.agent.name`-style span attribute so Grafana can filter per-specialist cost — this is the
"child spans per agent" requirement from the source proposal, delivered via the existing tracer.

### 2.3 Orchestrator — `backend/supervisor/deliberation.py` (new)

```python
async def run_deliberation_cycle(
    trigger: dict, settings: Settings
) -> DeliberationRecord:
    case = build_case(trigger, store)  # TDD
    names = route_specialists(case)  # TDD, table-driven
    findings = await asyncio.gather(
        *(invoke_specialist(n, case, settings) for n in names)
    )
    verdict = await invoke_verifier(case, findings, settings)  # hard filter
    filtered = apply_verdict(findings, verdict)  # TDD
    recommendation = await invoke_supervisor_synthesis(
        case, filtered, verdict, settings
    )  # = H-0b step 3, unchanged formula
    record = persist_deliberation(
        case, findings, verdict, recommendation, store
    )  # Firestore + Grafana annotation
    await dispatch_or_propose(
        recommendation, autonomy, envelope, settings
    )  # H-0b step 4/6, unchanged
    return record
```

Runs as a background job only (`C-6.5` — never inline in an HTTP request), same as H-0b already
specifies.

### 2.4 Routing table (deterministic, TDD — `route_specialists`)

| Trigger category | Specialists invoked |
|---|---|
| job `failed` / stuck lease / crash-recovered | Reliability Investigator + (station-specific QC agent if applicable) |
| loudness/delivery/caption QC breach | Delivery QC Agent + Reliability Investigator |
| quarantine (ingest) | Reliability Investigator |
| spend breach / runaway / daily-budget approach | Spend Guardian + Reliability Investigator |
| dub QC breach (post-E-2) | Localization Agent + Reliability Investigator |
| pickups retry ceiling / needs_human | Delivery QC Agent + Reliability Investigator |

Reliability Investigator is included by default for any genuine failure signal (root-cause is
always in scope); Spend Guardian is included whenever cost is part of the trigger. This table is a
plain Python dict of `str -> list[str]`, unit-tested directly — no LLM call decides "who gets asked."

## 3. Agent roster

| Agent | Responsibility | Tools (all read-only; zero `act=True`) | Real capability today? | New files |
|---|---|---|---|---|
| Post Supervisor (exists, extended) | Synthesize findings into a ranked recommendation (H-0b's leverage formula); does not gather evidence itself anymore | none new — consumes `Finding`/`Verdict` objects | Yes (B-1, extended here) | `backend/supervisor/synthesis.py` |
| Reliability Investigator | Root-cause a failed/stuck/quarantined job from real telemetry | `read_job`, `list_failed_jobs`, Grafana MCP `query_promql`/`query_loki`/`search_traces` (all already registered, B-2b) | Yes | `backend/supervisor/agents/reliability_investigator.py` |
| Delivery QC Agent | Interpret already-computed loudness/delivery/caption verdicts; judge delivery/handoff readiness | new `read_qc_report(job_id)` wrapping D-2/D-3/D-4 output docs | Yes (D-2/D-3/D-4 done) | `backend/supervisor/agents/delivery_qc.py` |
| Spend Guardian | Challenge render/retry plans against budget reality | `project_spend_micros`, `project_budgets` (existing `backend/stations/spend/*`, read-only wrap) | Yes (D-7 done) | `backend/supervisor/agents/spend_guardian.py` |
| Verification Agent | Reject unsupported/stale/already-resolved claims and unsafe proposed actions | none (adversarial review of the given Case+Findings only — cheapest, fastest call by design) | Yes | `backend/supervisor/agents/verification.py` |
| Localization Agent | Assess dub timing/meaning/voice quality | Chirp/waveform read tools (do not exist yet) | **No — deferred to E-2 slice** | ships with E-2, same pattern as above |

Stage 1a (unchanged sequencing from the source proposal — genuinely gated on AL-1 + D-9 landing
first, see §6):

| Agent | Responsibility | Depends on |
|---|---|---|
| Continuity Agent | Understands locks, neighboring shots, alternate eligibility | AL-1 (alternates model) |
| Creative Finishing Agent | Plans Extend/corrections/relight, draft→master progression | D-9 (Extend), AL-1 |
| Visual QC Agent | Independently reviews generated drafts, requests bounded revisions | D-9, real flicker/QC metrics (G0-proven) |

## 4. Frontend plan

- **`InvestigationDrawer.tsx`**: new collapsible section "Agent panel" (same disclosure pattern as
  existing "Show evidence"/"Show transcript") rendering, per `deliberation_id` on the job: specialist
  name, one-line claim, evidence link (deep-link to Grafana where possible), Verification verdict
  (approved/rejected + why), and the final ranked recommendation with leverage-score breakdown.
  Sourced from a new `GET /api/v1/deliberations/{cycle_id}` (mirrors the existing job/approval GET
  pattern in `backend/api/spine.py`); `Job` gains an optional `deliberation_id` field.
- **New SSE event** `deliberation.completed` — additive per spec §7.1 ("clients MUST ignore unknown
  `type`"): `{type, at, payload: {cycle_id, case_id, specialists: [...], recommendation_summary}}`.
  Add to `frontend/src/types/api.ts`'s `SseEvent` union.
- **Approvals inbox** (`ApprovalsRoute.tsx`): card gains a "supervisor consulted" line surfacing
  agreement/dissent, e.g. "Reliability Investigator + Spend Guardian agreed; Delivery QC dissented —
  flagged premature." This is the literal "disagreement visible" requirement from the source
  proposal — without it the multi-agent system is invisible and the hackathon story is lost.

## 5. Observability (C-4.2/C-4.3/C-4.4)

- One `deliberation_id` per cycle; every specialist/verifier/synthesis call carries it as a span
  attribute (parent-child relationship visible in Grafana Tempo without needing ADK's own tracing).
- Every specialist call's cost/tokens/latency recorded via the generalized `run_agent_call` (§2.2) —
  no specialist can silently skip metering because there is exactly one call site.
- Every real dispatch still goes through H-0's existing single Grafana-annotation writer — unchanged.
- Cost order of magnitude: a cycle now makes ~4-6 flash-tier calls (3 specialists + verifier +
  synthesis) instead of 1. At the pinned `gemini-3.7-flash` rates already in `otel_ai.py`
  ($0.75/$3.75 per M input/output tokens) this is still cents per cycle, not dollars — inside both
  the daily house cap and the $20 nightly envelope, and visible on the existing per-day spend metric
  + 80% alert (C-7.1). No new cost-control mechanism needed.

## 6. Build order (executable — task IDs for `docs/plans/2026-08-26-post-command-tasks.md`)

Matches the source proposal's 8 steps, reconciled against what's already done:

1. ~~Repair H-0 correctness blockers~~ — **already done**, tranches 1+2 committed, evidence on file.
2. **H-1a Case + routing + orchestrator plumbing** (TDD) — `case.py`, `deliberation.py`, routing
   table, `run_agent_call` generalization. No real specialist personas yet — this slice proves the
   fan-out/fan-in/persist mechanics with the *existing* single supervisor call standing in for one
   specialist, so the control flow is tested before multiplying personas.
3. **H-1b Reliability Investigator + H-1c Delivery QC Agent + H-1d Spend Guardian + H-1e Verification
   Agent** (one commit each, TDD for tool wiring/schema validation + EDD for judgment quality per
   agent — mirrors the D-1..D-7 one-station-per-commit pattern already used in this sprint).
4. **Run Stage-1 failures through the team in propose-only mode** — seed real failure fixtures
   (reuse G2's seeded runaway + a seeded loudness/AR failure), observe real `pc-deliberations`
   documents + Grafana annotations + FE panel end-to-end. This is the evidence gate for step 2-4,
   not a separate task ID — folds into H-1b..H-1e's DoD.
5. **AL-1** (alternates model) — genuinely independent of the specialist team (different files, no
   shared state); **may run in parallel** with steps 2-4 if a second track is available. Sequencing
   in the tasks file stays AL-1 after H-1e only to keep one agent's attention on one thing at a time;
   split into a parallel track explicitly if the owner wants to move faster under the 5-day runway.
6. **D-9 Extend** — unchanged from A8.
7. **Continuity Agent + Creative Finishing Agent + Visual QC Agent** — genuinely gated on AL-1+D-9
   (Continuity reasons over alternates/locks that don't exist before AL-1; Creative Finishing
   triggers Extend proposals that don't exist before D-9). Same build pattern as step 3.
8. **Decision-quality EDD gate, extended** (amends H-0b §Decision-quality hardening, does not
   replace it) — add delegation-correctness (TDD, routing table is deterministic), disagreement-
   handling and abstention dimensions (EDD, `eval-judge` rubric) to the existing
   `deliberation_ranking_quality` suite. New adversarial cases: two specialists' findings conflict;
   a specialist's evidence goes stale between fan-out and synthesis; Verification correctly vetoes a
   plausible-but-wrong finding. This gate — not a new one — is what H-0b already requires before ACT
   mode; it now scores multi-agent-produced tables instead of single-agent ones.
9. **Enable budgeted autonomy (H-0b ACT mode)** — unchanged trigger condition from H-0b's existing
   Definition of Done: does not flip until the (now-extended) rubric eval clears threshold.

### Task table (add to tasks file, Phase 3a-team, before AL-1; see §7 for the tasks-file edit)

| ID | Task | Mode | Refs | DoD |
|---|---|---|---|---|
| H-1a | Case model + deterministic routing table + `run_agent_call` (generalizes `otel_ai.run_supervisor_text`) + orchestrator skeleton (`deliberation.py`) | TDD | C-6.5, C-6.4 | unit tests: case built from real job doc; routing table covers every trigger category in §2.4; orchestrator persists a `pc-deliberations` doc from a single-specialist stand-in call |
| H-1b | Reliability Investigator agent | TDD+EDD | C-2.1, C-4.3 | real Gemini call w/ Grafana MCP tools scoped to read-only; finding schema validated; EDD: root-cause accuracy on ≥3 seeded real failures |
| H-1c | Delivery QC Agent | TDD+EDD | AC-S3.1, AC-S5.1 | `read_qc_report` reads real D-2/D-4 output; EDD: correctly distinguishes genuine breach from borderline-pass on seeded cases |
| H-1d | Spend Guardian agent | TDD+EDD | AC-S5b.1/.2, C-7.* | reads real Spend Control state; EDD: challenges an underpriced retry plan on a seeded case |
| H-1e | Verification Agent + hard-filter wiring into synthesis | TDD+EDD | — | grep-test: rejected finding's actions never reach the ranked list; EDD: correctly vetoes a plausible-but-wrong finding on an adversarial case |
| H-1f | FE: Agent panel in `InvestigationDrawer` + `deliberation.completed` SSE event + approvals-card disagreement line | TDD (client) | spec §7.1 | contract test for new SSE type; drawer renders a real `pc-deliberations` doc end-to-end |
| H-1g | Multi-agent shadow run: Stage-1 seeded failures through the full team, propose-only, evidence archived | integration | C-1.* | `docs/evidence/H-1/`: real `pc-deliberations` docs + Grafana annotations + FE screenshot, no mocked candidates |

`H-2`/`H-3`/`H-4` (morning report, approvals inbox FE, dashboards-as-code) are unchanged in scope —
they now render richer, multi-agent inputs instead of single-agent ones; no task-ID change needed.

## 7. Integration with H-0b (addendum, not a rewrite)

Append this to `docs/plans/2026-09-02-h0b-budgeted-supervisor-plan.md` under a new "Addendum
2026-09-03" heading (do not edit its existing owner-ruling text):

> Step 2 ("Collect candidates") of the deliberation loop is now: `build_case` → `route_specialists`
> → parallel specialist `Finding`s → `Verification` hard-filter (§Architecture, this plan). Step 3
> ("Score each candidate") is unchanged — the leverage formula
> (`unblocks_weight / cost_micros`, reversibility as hard exclusion) now scores
> `ProposedAction`s carried on verified `Finding`s instead of directly-queried telemetry. Every other
> owner ruling in this document (no action-count cap, envelope covers continuity adds, self-
> correction can't re-fight a human, ACT-mode gated on the rubric eval) is unchanged and this
> addendum does not reopen any of them. The rubric eval's dataset is extended per
> `docs/plans/2026-09-03-multiagent-supervisor-plan.md` §6 step 8 (delegation/disagreement/
> abstention dimensions) — same suite name (`deliberation_ranking_quality`), same gate, richer cases.

## 8. Testing plan

- **TDD** (deterministic control flow — RED first, per C-3.1): `build_case`, `route_specialists`,
  `run_deliberation_cycle`'s gather/persist/dispatch-or-propose flow, `apply_verdict` hard-filter,
  the "no specialist registers an act-class tool" grep-test (extends H-0's single-writer grep-test
  pattern), crash-mid-fan-out recovery (reuses H-0's idempotent dispatch — a killed cycle doesn't
  double-charge or double-dispatch on resume).
- **EDD** (generative judgment — versioned dataset + numeric threshold before "done", per C-3.3):
  per-specialist judgment quality on seeded real-failure fixtures; the extended
  `deliberation_ranking_quality` rubric (delegation correctness, disagreement handling, abstention) —
  gates H-0b's ACT mode, not this slice's propose-only shadow run.
- **Adversarial** (money + evidence, per C-7 discipline already applied to Spend Control): a finding
  with a garbage/negative cost estimate is excluded (reuse `coerce_cost_micros`); a stale-evidence
  finding is caught by Verification, not silently ranked.

## 9. Non-Goals (this slice)

- ADK `Runner`/`SequentialAgent`/`ParallelAgent`/`AgentTool` — real, available (`google-adk==2.8.0`),
  intentionally not used here (§0.2). Revisit only if a live interactive agent-chat surface is
  scoped later; the deliberation pipeline is fine as direct-call orchestration.
- Localization Agent build — ships with E-2 (§0.1), not before.
- A UI for editing the ranked table before dispatch — same "autonomous-then-reportable, not
  autonomous-with-a-preview-step" non-goal H-0b already declared.
- Cross-cycle memory/learning between deliberations — each cycle is independent; no agent "remembers"
  a prior cycle's outcome beyond what's in Firestore/Grafana (avoids an unbounded new state surface
  under time pressure).

## 10. Definition of Done (whole slice)

- [ ] `docs/evidence/H-1/` contains real `pc-deliberations/{cycle_id}` documents from ≥3 distinct
      real Stage-1 failure/breach scenarios (no mocked candidates, per C-1).
- [ ] Grafana shows a parent `deliberation_id` with per-specialist child spans, cost, and latency
      for each cycle (C-4.2/C-4.4).
- [ ] `InvestigationDrawer` renders the agent panel from a real deliberation; a judge can see which
      specialists ran, what each concluded, and where they disagreed.
- [ ] Verification's hard-filter is proven by grep-test AND by one real adversarial case where it
      actually vetoes a finding.
- [ ] `deliberation_ranking_quality` eval (extended per §6 step 8) documented with pass/fail against
      `thresholds.yaml`, even though ACT mode itself stays gated behind H-0b's existing rule.
- [ ] `docs/plans/2026-08-26-post-command-tasks.md` reflects H-1a..H-1g in place of the old flat H-1
      row; H-0b's document carries the §7 addendum.
