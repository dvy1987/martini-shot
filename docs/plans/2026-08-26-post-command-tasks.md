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
| A-1 ✅ done 2026-08-30 | `core/config.py` (env precedence) + structured logging + OTel init (OTLP traces/metrics/logs via real exporter class, no mock exporters) + FastAPI app factory + **error middleware: no stack traces/env in responses (C-5.3)** + centralize model IDs in `core/models.py`; align AGENTS.md Generative-Depth pin wording (ADR 0002: GA `-001` IDs, Veo proven) | TDD | C-4.1, C-4.2, C-5.3, AC-S0.2 prep | `backend/core/`, `backend/api/app.py` | F-3 | unit tests config precedence + error responses (RED observed); exporter-initialized flag true in harness; app boots — **evidence: `docs/evidence/A-1/`, gate green 27/27** |
| A-2 ✅ done 2026-08-30 | GCS wrapper (signed up/down URLs) + Firestore wrappers | TDD | C-6.2 | `backend/core/gcs.py`, `backend/core/firestore.py` | F-2 | integration test: create/upload/download/delete real object + temp doc (dev bucket) — **evidence: `docs/evidence/A-2/`, 4/4 real-service tests, commit `715db8c`** |
| A-3 ✅ done 2026-08-30 | Job model + Firestore lease queue: submit/lease/heartbeat/complete/fail/requeue-on-expiry; idempotent per job_id | TDD | C-6.3, AC-S0.1 | `backend/jobs/` | A-2 | AC-S0.1 chaos test: real subprocess kill mid-job → second worker completes exactly once — **evidence: `docs/evidence/A-3/` (exactly-once ledger + attempts==2), transactional owner guards, coverage gate wired (95.4%)** |
| A-4 ✅ done 2026-08-30 | ffmpeg/ffprobe wrapper: duration/fps/codec probe, loudness filter invocation, frame extract/reassemble | TDD | C-3.1, AC-S2.2(p1) | `backend/core/media.py` | A-1 | round-trip tests on fixtures/spike; ±1 frame — **evidence: `docs/evidence/A-4/`, 3/3 real-binary tests on G0 fixtures** |
| A-5 ✅ done 2026-08-30 | Handoff Validator silent mode: turnover-manifest checks at station transitions; block + annotate on discrepancy | TDD | C-4.3, AC-S0b.1 | `backend/jobs/handoff.py` | A-3 | missing-manifest-file fixture blocks with reason code; complete manifest passes; annotation written — **evidence: `docs/evidence/A-5/`, 8/8 incl. real-Firestore annotation w/ job_id** |

## SPRINT — Lane B: Supervisor skeleton
| ID | Task | Mode | Refs | Target | After | DoD |
|---|---|---|---|---|---|---|
| B-1 ✅ done 2026-08-30 | ADK agent scaffold: Post-Supervisor persona, tool registry, autonomy toggle (propose-only default) — rebuilt by orchestrator (A6 worker reverted) | TDD | C-2.1, AC-A.1 prep | `backend/supervisor/` | F-3 | registry + toggle unit tests — **evidence: `docs/evidence/B-1/`, 7/7, real LlmAgent w/ pinned TEXT_MODEL** |
| B-2 ✅ done 2026-09-01 | Grafana MCP connector: OSS stdio + SA token (hosted OAuth persistence still F-4); live annotation round-trip | TDD | C-2.2, C-4.3 | `backend/supervisor/mcp.py` | F-4 | REAL round-trip archived — **evidence: `docs/evidence/B-2/`, commit `4aaa6d5`** |
| B-3 ✅ done 2026-09-02 | AI Observability instrumentation: tokens, cost, latency per agent call | TDD | C-4.4 | `backend/supervisor/otel_ai.py` | A-1, B-1 | one real Vertex text call; **evidence: `docs/evidence/B-3/`** (`cost_micros=400`) |

## SPRINT — Lane C: Frontend + G1
| ID | Task | Mode | Refs | Target | After | DoD |
|---|---|---|---|---|---|---|
| C-1 ✅ remainder 2026-09-02 | FE shell + live contract tests vs running `/api/v1` (health open, error envelope, SSE type/at/payload). Did **not** change 401 body (no `message` on middleware deny) | TDD (client) | C-6.1, C-5.2/.3, §7.1 | `frontend/src/api/contract.test.ts` | F-3 | 67 FE tests; API unchanged |
| G1 ✅ 2026-09-01 | **Gate G1 run** (orchestrator): real MP4 → ingest (arrival+checksum) → traces/metrics/logs in Grafana → annotation w/ job_id → SSE queued→running→pass | integration | AC-S0.2, C-4.*, C-2.2 | `docs/evidence/G1/` (`gate.json`, `sse.ndjson`, README) | A-1..A-5, B-1..B-2 | job `job-12f1bb8f8b98` pass; trace `1558b20e2f5b0e99fd29d2dd40627bfd`; 3 PromQL + Loki line + annotation id 4 |

## SPRINT — Phase 2: deterministic stations (parallel after A-4; each = RED first, then green, evidence + README)
| ID | Task | Station | Mode | Refs | DoD |
|---|---|---|---|---|---|
| D-1 ✅ done 2026-09-02 | Ingest full: probe, corruption detect, audio-sync spot check, quarantine flow | S1 | TDD | AC-S1.1/.2, C-4.3 | bit-flipped slate → `quarantined`; README `backend/stations/ingest/README.md` |
| D-2 ✅ done 2026-09-02 | Loudness engine: ebur128 parse, stem heuristic, verdict tables, M&E check | S3 | TDD | AC-S3.1 | `pc_loudness_lufs`; README `backend/stations/loudness/README.md` |
| D-3 ✅ done 2026-09-02 | Caption validator sub-check: SRT/VTT/TTML parsers + rule engine w/ rule IDs (consumed by D-4, no own screen) | S5 | TDD | AC-S5.2 | goldens in `fixtures/captions/`; `tests/test_captions.py` |
| D-4 ✅ done 2026-09-02 | Delivery & Compliance pack: YAML profiles + evaluator delegating D-2+D-3 | S5 | TDD | AC-S5.1 | streaming/broadcast/social YAML; README `backend/stations/delivery/README.md` |
| D-7 ✅ done 2026-09-02 | **Spend Control**: cost aggregation from `cost_micros`; YAML policies; ACT: throttle/stop/approve; annotation + incident | S5b | TDD | AC-S5b.1/.2, C-7.* | 40× runaway → throttled; adversarial tests; README `backend/stations/spend/README.md` |
| D-5 ✅ done 2026-09-02 | Pickups pipeline: frame loop, anchor-prompt builder, prev-frame conditioning, reassembly | S2 | EDD | AC-S2.1, C-3.3 | identity QC (no Veo); eval `docs/evidence/D-5/`; thresholds.yaml |
| D-6 ✅ done 2026-09-02 | Pickups QC + auto-retry: breach → strengthen anchors → ×2 → needs_human; visible to D-7 | S2 | TDD+EDD | AC-S2.2 | retry tests use real G0 flicker scores |
| G2 ✅ 2026-09-02 | **Gate G2 run**: deterministic stations through real queue; Spend Control throttles a seeded runaway | — | — | G2 list | **evidence: `docs/evidence/G2/`** (project `g2-6d2d7919`, runaway throttled) |

## SPRINT — Phase 3a-early: Extend + real approval-action loop (owner ruling 2026-09-02, amendment A8)

**Amendment A8 (owner-approved 2026-09-02):** owner is optimizing to **win** the Grafana track, not only to bank the Stage-1 fallback. The observable, auditable evidence→proposal→approval→action→QC loop is the track differentiator; it is currently fake everywhere except Spend Control (`decide_approval` only flips a status field — nothing executes). Promoting **AL-1 + D-9 (Extend)** and a new **H-0 approval-action executor** ahead of E-2/E-3/G3. This crosses the "Stage 1a starts only after G3" rule from A5 for these two items **only** — Extend is chosen over the spec'd S2 background_swap/outpaint (frame-by-frame Gemini image edit) because G0 already proved Extend cleaner (flicker 0.69× vs 13.97×) and lower-risk for a live demo. Dub QC (E-2/E-3) and G3 move **after** this slice, not cancelled — still required to call Stage 1 complete. Logged: `docs/memory/decision-log.md` (2026-09-02).

| ID | Task | Mode | Refs | DoD |
|---|---|---|---|---|
| H-0 | Typed approval→action executor: `proposed→approved→acting→resolved\|failed`; deterministic command/job IDs; reconciler survives crash; `decide_approval` enqueues instead of just flipping status; every station's approvals (not only Spend Control) route through it | TDD | C-6.3, C-6.4, spec §7.2 | unit + integration: approve → real execution observed; crash mid-`acting` → reconciler resumes exactly once; SSE + Grafana annotation on every transition |
| AL-1 | Alternates model + API: every generated clip = alternate `{shot_id, op, artifact_ref, eval_scores, status}`; add/remove-from-continuity is an approval-tracked action (via H-0) | TDD | spec §5 Stage 1a | alternate lifecycle unit tests; routes through H-0, not a second action path |
| D-9 | Extend: Veo 3.1 single ≤7s segment first (G0-proven path); async execute, GCS store, meter cost, continuity/flicker QC, signed media, alternates lane in FE | EDD | AC (new, mirrors AC-S2.1 style) | eval on ≥3 fresh shots; draft/master are separate QC'd attempts; proposal→approval→render→QC→annotate observed end-to-end for a judge |

## SPRINT — Phase 3: hero depth + Dub QC (moved after H-0/AL-1/D-9 per A8)
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
| H-3 | Approvals inbox FE + autonomy toggle enforcement; Spend Control escalations land same inbox (executor now shared via H-0) | TDD | §7.2, C-4.3 | toggle honored in agent middleware tests; S5b + generic approvals render/resolve |
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

## PARKED — post-sprint backlog (owner-confirmed 2026-09-02)

| ID | Item | Order | Notes |
|---|---|---|---|
| F-4 | Hosted Grafana MCP OAuth login + saved token persistence | **LAST** (post-hackathon) | Owner ruling 2026-09-02: hackathon ships **OSS + SA token only** (`MCP_MODE=oss`, proven at B-2/B-2b). Decision point: before J-3 rehearsal, add an honest "OSS-only MCP auth" line to README limitations (J-4). Keep the SA-token-regeneration runbook handy for the demo window (token is a demo SPOF). See ADR-0001; log deferral decision in `docs/memory/decision-log.md`. |
| M8b | BigQuery billing-export reconcile — **audit report only** | Optional, after G3 when billable Dub/TTS volume exists | Cheap GCP toggle; closes the C-6.4 "did our integer micros match Google's invoice?" honesty loop. **Never the control loop** — Spend Control (S5b/ADR-0003) stays the only brain. Report lands in `docs/evidence/` + README limitations/honesty section. |

