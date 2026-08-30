# Tasks: `post-command` — agent-pickable task list
Generated: 2026-08-30 (SDD `/tasks` step) from `docs/plans/2026-08-26-post-command-plan.md` (amended A7) · Spec: `docs/specs/2026-08-26-post-command-feature-spec.md` (Approved) · Constitution: `docs/constitution.md@1`
Crosscheck: `docs/reviews/2026-08-30-post-command-spec-crosscheck.md` — PASS (after A7)

**Sprint scoping (owner ruling 2026-08-30):** this sprint builds **Stage 1 only** (Phases 1→3 + supervisor slice + rehearsal). Phase 3a (Stage 1a) stays in the plan as amended (A5) but is **parked behind Gate G3** — do not start 3a tasks until G3 passes. Stage-2 leftovers (I-1) only if ahead of schedule on Sep 7.

**Rules every task inherits (A6, plan §Orchestration):** workers may build; only the orchestrator reviews diffs, observes RED, runs `make check`, and commits. Evidence goes to `docs/evidence/<task-id>/`. No task is done without its DoD evidence.

---

## DONE (do not re-open; evidence committed)
| ID | What | Evidence |
|---|---|---|
| F-1..F-4 | Accounts, repo init (CI-lite, pre-commit, license), MCP auth ADR 0001 | commits through `958337e`; `docs/adr/0001-mcp-auth.md` |
| F-3b | Fresh-source attestation — **tracked, lands in README at J-4** (C-2.4) | J-4 checklist |
| S-1..S-3 + Gate G0 | Spike: fixtures/spike/ + bg-swap + scene-extend + GO verdict | `docs/evidence/G0/` (VERDICT.md, flicker_scores.json, videos), commit `a42a069` |

## SPRINT — Lane A: Core spine (orchestrator-led after A-1 worker demotion)
| ID | Task | Mode | Refs | Target | After | DoD |
|---|---|---|---|---|---|---|
| A-1 | `core/config.py` (env precedence) + structured logging + OTel init (OTLP traces/metrics/logs via real exporter class, no mock exporters) + FastAPI app factory + **error middleware: no stack traces/env in responses (C-5.3)** + centralize model IDs in `core/models.py`; align AGENTS.md Generative-Depth pin wording (ADR 0002: GA `-001` IDs, Veo proven) | TDD | C-4.1, C-4.2, C-5.3, AC-S0.2 prep | `backend/core/`, `backend/api/app.py` | F-3 | unit tests config precedence + error responses (RED observed); exporter-initialized flag true in harness; app boots |
| A-2 | GCS wrapper (signed up/down URLs) + Firestore wrappers | TDD | C-6.2 | `backend/core/gcs.py`, `backend/core/firestore.py` | F-2 | integration test: create/upload/download/delete real object + temp doc (dev bucket) |
| A-3 | Job model + Firestore lease queue: submit/lease/heartbeat/complete/fail/requeue-on-expiry; idempotent per job_id | TDD | C-6.3, AC-S0.1 | `backend/jobs/` | A-2 | AC-S0.1 chaos test: real subprocess kill mid-job → second worker completes exactly once |
| A-4 | ffmpeg/ffprobe wrapper: duration/fps/codec probe, loudness filter invocation, frame extract/reassemble | TDD | C-3.1, AC-S2.2(p1) | `backend/core/media.py` | A-1 | round-trip tests on fixtures/spike; ±1 frame |
| A-5 | Handoff Validator silent mode: turnover-manifest checks at station transitions; block + annotate on discrepancy | TDD | C-4.3, AC-S0b.1 | `backend/jobs/handoff.py` | A-3 | missing-manifest-file fixture blocks with reason code; complete manifest passes; annotation written |

## SPRINT — Lane B: Supervisor skeleton
| ID | Task | Mode | Refs | Target | After | DoD |
|---|---|---|---|---|---|---|
| B-1 | ADK agent scaffold: Post-Supervisor persona, tool registry, autonomy toggle (propose-only default) — **worker output awaiting orchestrator review** | TDD | C-2.1, AC-A.1 prep | `backend/supervisor/` | F-3 | registry + toggle unit tests (A6: diff review + own gate run) |
| B-2 | Grafana MCP connector: hosted client w/ OAuth persistence + OSS/service-account env-flag switch; tool surface: search_dashboards, query_promql, query_loki, search_traces, add_annotation, create_incident | TDD | C-2.2, C-4.3 | `backend/supervisor/mcp.py` | F-4 | REAL round-trip: annotation written + read back via API; response JSON archived; zero mocks |
| B-3 | AI Observability instrumentation: tokens, cost, latency per agent call | TDD | C-4.4 | `backend/supervisor/otel_ai.py` | A-1, B-1 | one real agent call visible in AI Observability (screenshot evidence) |

## SPRINT — Lane C: Frontend + G1
| ID | Task | Mode | Refs | Target | After | DoD |
|---|---|---|---|---|---|---|
| C-1 | FE interim shell: API client `/api/v1`, SSE hook, routed pages per spec §7 — **worker output awaiting orchestrator review** (skeleton already committed 2026-08-28; review remaining deltas) | TDD (client) | C-6.1, §7.1 | `frontend/` | F-3 | contract tests vs backend OpenAPI; gates green (`npm run build/test/lint/typecheck`) |
| G1 | **Gate G1 run** (orchestrator only): real MP4 → FE upload → job → minimal ingest (arrival+checksum) → trace/metrics/logs in Grafana Explore → supervisor writes real investigation annotation w/ job_id → SSE updates UI | integration | AC-S0.2, C-4.*, C-2.2 | `docs/evidence/G1/` | A-1..A-5, B-1..B-2, C-1 | evidence pack: trace ID + 3 PromQL queries + Loki line + annotation JSON + SSE capture (A7) |

## SPRINT — Phase 2: deterministic stations (parallel after A-4; each = RED first, then green, evidence + README)
| ID | Task | Station | Mode | Refs | DoD |
|---|---|---|---|---|---|
| D-1 | Ingest full: probe, corruption detect, audio-sync spot check, quarantine flow | S1 | TDD | AC-S1.1/.2, C-4.3 | corrupted MP4 fixture → `quarantined` + annotation; ≥90% coverage parser/checksum; station README (C-8.1) |
| D-2 | Loudness engine: ebur128 parse, stem heuristic, verdict tables, M&E check | S3 | TDD | AC-S3.1 | ±0.3 dB vs ffmpeg reference; boundary-case verdict matrix; `pc_loudness_lufs` exported; README |
| D-3 | Caption validator sub-check: SRT/VTT/TTML parsers + rule engine w/ rule IDs (consumed by D-4, no own screen) | S5 | TDD | AC-S5.2 | golden files valid + 7 violation classes; 90% coverage; README |
| D-4 | Delivery & Compliance pack: YAML profiles + evaluator delegating D-2+D-3 | S5 | TDD | AC-S5.1 | compliant/violating matrix per profile; unknown destination rejected; report renders in FE; README |
| D-7 | **Spend Control**: cost aggregation from `cost_micros`; YAML policies (per-job cap, retry cap, hourly/daily budgets, runaway ≥N re-queues); ACT: throttle/stop/approve; annotation + incident | S5b | TDD | AC-S5b.1/.2, C-7.* | seeded 40× runaway → throttled; budget breach → intake paused; approvals route to inbox; **adversarial pass mandatory (money)**; README |
| D-5 | Pickups pipeline: frame loop, anchor-prompt builder, prev-frame conditioning, reassembly | S2 | EDD | AC-S2.1, C-3.3 | dataset manifest (10 clips) + flicker metric + thresholds.yaml BEFORE feature; eval runs; JSONL archived; README |
| D-6 | Pickups QC + auto-retry: breach → strengthen anchors → ×2 → needs_human; visible to D-7 | S2 | TDD+EDD | AC-S2.2 | retry state machine tests; threshold-breach sim from REAL eval outputs; cost estimator ±20%; README |
| G2 | **Gate G2 run** (orchestrator only): all deterministic stations through real queue; Spend Control throttles a seeded runaway; dashboards live; FE shows results | — | — | G2 list | evidence pack archived |

## SPRINT — Phase 3: hero depth + Dub QC
| ID | Task | Station | Mode | Refs | DoD |
|---|---|---|---|---|---|
| E-2 | Dub timing QC: TTS dubs (SSML pacing), duration-delta, envelope cross-correlation sync, Gemini listen-classify | S4 | EDD | AC-S4.1 | eval JSONL; playable dub pair in FE; README |
| E-3 | Batch demo seed (start early — TTS slow + billable): 8–10 eps × 3 languages dubs + captions; cost estimate printed pre-run | fixtures | manual+scripts | C-7.2 | manifest committed; dry-run cost print; first episode seeded |
| G3 | **Gate G3 run**: hero ops hold bars on ≥3 fresh shots; Dub QC within thresholds; raw evidence clips | — | — | — | Stage 1 complete end-to-end — guaranteed fallback submission |

## SPRINT — Phase 4: supervisor intelligence
| ID | Task | Mode | Refs | DoD |
|---|---|---|---|---|
| H-1 | Investigation chains: alert→PromQL→LogQL→Tempo playbooks; severity rubric; proposal formatting | EDD (rubric) | AC-A.1, C-4.3 | seeded corrupt-file scenario: annotation w/ correct job_id + root cause ≤120 s, asserted via Grafana query (no mocks) |
| H-2 | Morning report generator: Gemini summarization over real telemetry excerpts w/ citations; cites Spend Control lines | EDD | AC-A.2 | faithfulness rubric ≥4/5 on 5 seeded scenarios |
| H-3 | Approvals inbox FE + autonomy toggle enforcement; Spend Control escalations land same inbox | TDD | §7.2, C-4.3 | toggle honored in agent middleware tests; S5b approvals render/resolve |
| H-4 | Dashboards + alert rules as code finalized | config | C-4.5 | `infra/grafana/` provisions cleanly via API; screenshots archived |

## SPRINT — Phase 6: rehearsal + submission (sequential)
| ID | Task | Refs | DoD |
|---|---|---|---|
| J-0 | Batch readiness: 8–10 eps × 3 langs traverse pipeline; system-scale dashboards | C-1.6 | batch journey screenshots; per-language coverage report |
| J-1 | Full journey seed: short traverses every station; supervisor handles seeded faults (announced list) | C-1.4, AC-A.1 | per-station assertions; morning report compiles |
| J-2 | Chaos pass: worker kills, OAuth refresh, OTLP flap; Spend Control bounds runaway | C-6.3 | recovery log; no orphaned leases; spend inside policy |
| J-3 | Replit hosting swap rehearsal | §7.3 | both URLs live; rollback doc |
| J-4 | README final: stranger-rerunnable quickstart + honest limitations + **fresh-source attestation (C-2.4, F-3b)** | C-1.6, C-2.4 | fresh-agent walkthrough passes |
| J-5 | 3-min video FROM THE RUNNING PRODUCT; announced fault injections; captions EN | C-1.5 | raw takes + final cut in `docs/evidence/video/` |
| J-6 | Devpost submission ≥24 h early | C-2.3 | confirmation screenshot |

## PARKED — Phase 3a: Stage 1a (A5; **starts only after G3 passes**)
AL-1 Alternates model+API (TDD) → D-9 Extend (EDD; Omni-vs-Veo per op decided by eval + ADR — Veo `-001` path already proven at G0, Omni research parked until now) → D-10 Corrections (EDD) → E-1 Relight Studio (EDD) → D-11 Draft-first orchestration (TDD+EDD) → D-12 Coverage (EDD) → D-15 Revision Room (EDD+TDD) → D-16 Camera Language (EDD) → stretch: D-13 Transition Forge, D-14 Versioning. Gate G3a. Post-deadline: I-1..I-4 (Stage 2 remainder), I-5..I-9 (Stages 3–4).
