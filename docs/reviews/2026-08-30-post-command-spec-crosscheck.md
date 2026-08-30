# Spec Crosscheck: `post-command` (Martini Shot)
Date: 2026-08-30 09:39 | Verdict: **FAIL** (initial run — 3 blockers + 1 missing artifact) | Re-run below after amendment A7

## Inputs
- Constitution: `docs/constitution.md@1` (Active)
- Spec: `docs/specs/2026-08-26-post-command-feature-spec.md` — Status **Approved**, amended 2026-08-28 (incl. A5 Stage 1a)
- Plan: `docs/plans/2026-08-26-post-command-plan.md` — amended 2026-08-28, A6 orchestration block 2026-08-29
- Tasks: **MISSING at initial run** — no `docs/plans/2026-08-26-post-command-tasks.md`

## Owner rulings recorded this session (2026-08-30)
1. **Stage 1a stays in scope as amended** (A5) — Phase 3a tasks remain in spec §5 + plan, exactly as the plan already gates them: Phase 3a starts **only after G3 passes** (`plan:118`, `plan:152`).
2. **This sprint builds Stage 1 only**: Phases 1→3 (spine A/B/C → G1 → stations D-1..D-7 → G2 → hero/dub depth → G3) + the Phase-4 supervisor slice + Phase-6 rehearsal. Phase 3a and Stage-2 leftovers (I-1) stay parked behind G3/the Sep-7 rule. The plan already encodes this; it is a build-order ruling, not a scope cut.
3. G0 evidence stands: Veo path proven (bg-swap flicker 0.00992; scene-extend 0.00327; GO verdict, commit `a42a069`). Omni research deferred until after Stage 1 → D-9/D-10 model selection (Omni vs Veo per op) resolves at Phase-3a entry via eval + ADR.

## Checks (initial run, 2026-08-30 09:39)

| ID | Check | Verdict | Evidence |
|----|-------|---------|----------|
| A | Spec readiness | **WARN** | Status Approved ✓ (`spec:1`); zero `[NEEDS CLARIFICATION]` markers ✓; Open Questions "None" ✓ (`spec:283`). No FR-N/NFR-N numbering exists — requirements are per-station capability blocks with embedded ACs (S0..S14 + Supervisor, `spec:128-209`). Accepted as domain-equivalent; traceability is per-station. |
| B | Constitution coverage | **FAIL** | C-5.3 (`constitution.md:35`), C-2.4 (`constitution.md:16`), C-8.1 (`constitution.md:49`) addressed by no spec section, no plan task, no DoD line; no `## Constitution Waivers` section exists. All other rules map: C-1→zero-mock + integrity gate; C-2.1/2.2→spec §1/§3 + B-2; C-3→TDD/EDD mode columns + thresholds.yaml; C-4→spec §6 + A-1/B-3/H-4; C-5.1→F-3 + .gitignore; C-5.2→§7.2; C-6→§3/§9; C-7→§10 + D-7 + Budget Guardrails; C-8.2→ADR plan §9. |
| C | Spec→Plan traceability | **WARN** | Every Stage-1 station maps to named tasks with AC-carrying DoDs: S0→A-1..A-3+B-3 · S0b→A-5 · S1→D-1 · S2→D-5/D-6 · S3→D-2 · S4→E-2 · S5→D-3/D-4 · S5b→D-7 · Supervisor→B-1..B-3+H-1..H-3 · FE→C-1/H-3 · Stage 1a→Phase 3a · rehearsal→J-0..J-6. Gap: **AC-S0.2** (`spec:131`, Tempo/Mimir visibility) has no named test target — only exercised manually at Gate G1 (`plan:95`). |
| D | Plan→Spec traceability | **PASS (conditional)** | No plan task implements behavior absent from the spec (checked station-by-station; §7.2 auth is spec-amended, not creep; Spend Control is spec S5b; Stage 1a tasks trace to spec §5 Stage-1a block). Conditional: plan tasks don't cite C-N IDs explicitly — mode columns encode them (TDD=C-3.1, EDD=C-3.3, evidence dirs=C-3.5). The tasks file carries explicit `Refs:` columns, closing this. |
| E | Task quality | **PASS** | Every task carries Mode + After/RED + DoD; none vague. F-1..F-4, S-1..S-3, G0 already executed with committed evidence (commits through `958337e`). |
| F | Out-of-Scope adherence | **PASS** | Spec §8 Non-Goals (`spec:252`): no plan task implements multi-tenant RBAC (§7.2 Google sign-in gates decision writes only — compliant), mobile, non-Google models (C-2.1 holds repo-wide), client integrations, UI i18n, or SLAs. |

## Findings (initial run)

1. **[BLOCKER] Required tasks artifact missing** — `docs/plans/2026-08-26-post-command-tasks.md` does not exist; SDD phase order (`/tasks` before `/analyze`) was collapsed. — fix: generate it from the plan (agent-pickable slices for this sprint's Stage-1 scope, per-task `Refs: C-x / AC-y`, Phase 3a marked "starts only after G3", completed F/S tasks marked done).
2. **[BLOCKER] C-5.3 unaddressed** (constitution.md:35 — error responses must not leak stack traces/env) — no task or DoD owns it. — fix: extend **A-1** DoD.
3. **[BLOCKER] C-2.4 unaddressed** (constitution.md:16 — all source fresh during contest window) — nothing attests it. — fix: add plan line **F-3b**.
4. **[BLOCKER] C-8.1 unaddressed** (constitution.md:49 — station READMEs) — no station DoD mentions the README. — fix: append shared DoD clause to D-1..D-7 and E-2.
5. **[WARN] AC-S0.2 has no named test target** (spec:131) — only the G1 gate exercises it manually. — fix: extend Gate G1 line with evidence requirement.
6. **[INFO] Model-pin drift in AGENTS.md** — "Generative Depth" section still says Omni serves `-preview` and Omni-first; ADR 0002 + G0 record the GA `-001` suffix convention and Veo as the proven video path. — fix: align wording when A-1 lands (model IDs centralize in `backend/core/models.py`).
7. **[INFO] Sprint build-order ruling recorded** (§Owner rulings, item 2) — Stage 1 only this sprint; Phase 3a untouched behind its existing G3 gate.

---

# Re-run: 2026-08-30 (after amendment A7 + tasks file generation) — Verdict: **PASS**

## Actions taken
- **A7 applied to `docs/plans/2026-08-26-post-command-plan.md`** (owner-approved this session):
  - A-1 DoD extended with C-5.3 clause (error middleware, no stack traces/env in responses, unit-tested) → closes Finding 2
  - New F-3b line (fresh-source attestation at J-4) → closes Finding 3
  - Shared C-8.1 station-README clause appended to D-1..D-7 + E-2 DoDs → closes Finding 4
  - Gate G1 line extended: AC-S0.2 evidence (trace ID + 3 PromQL queries + Loki line) archived under `docs/evidence/G1/` → closes Finding 5
- **`docs/plans/2026-08-26-post-command-tasks.md` generated** with explicit `Refs:` (C-x / AC-y) per task, sprint scoping, done-markers → closes Findings 1 and the conditional on Check D
- Finding 6 (INFO): tracked as an A-1 work item, not a gate blocker
- Finding 7 (INFO): recorded, no action required

## Checks (re-run)

| ID | Check | Verdict | Evidence |
|----|-------|---------|----------|
| A | Spec readiness | PASS | unchanged from initial run (Approved, zero CLs) |
| B | Constitution coverage | **PASS** | C-5.3→plan A-1 DoD; C-2.4→plan F-3b; C-8.1→plan D-1..D-7/E-2 DoD clause; no waivers needed |
| C | Spec→Plan traceability | **PASS** | AC-S0.2 now has named evidence target at Gate G1 (`plan:95` area, amended); all other mappings unchanged |
| D | Plan→Spec traceability | **PASS** | tasks file carries explicit C-N/AC refs; no unref'd tasks |
| E | Task quality | **PASS** | tasks file: every task has DoD + target component + mode |
| F | Out-of-Scope adherence | PASS | unchanged |

## Verdict: **PASS** — implementation may begin.

Next: `/implement` — `incremental-implementation` + `test-driven-development`, red-green per slice from AC skeletons. A6 worker review (B-1, Track C) is QC of already-dispatched work and proceeds in parallel with this gate, not behind it.
