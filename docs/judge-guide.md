# Judge Guide

This guide is the shortest route through the repository after [`README.md`](../README.md). It is written for a judge who wants to verify that Martini Shot is a working media workflow rather than a dashboard mockup.

## The claim to test

> **Martini Shot lets a post-production supervisor upload clips, set a budget, walk away, and return to a governed list of completed work, paused work, evidence, and Grafana-backed explanations.**

The current product has two cooperating but distinct agentic paths:

| Path | What it decides | Primary implementation |
|---|---|---|
| Walk-away finishing | Which optional media and delivery jobs should run after required cleanup | `backend/supervisor/adk_finishing.py`, `backend/supervisor/finishing_loop.py`, `backend/api/finish.py` |
| Post Supervisor | How to investigate and respond to failed, quarantined, or human-review work | `backend/supervisor/team.py`, `backend/supervisor/agents/verification.py`, `backend/supervisor/agents/post_supervisor.py`, `backend/supervisor/budget_loop.py` |

The finishing path is the main demo spine. The Post Supervisor is the Grafana-centered operational proof.

## Five-minute repository tour

| Read this | What it proves |
|---|---|
| [`frontend/src/components/FinishBar.tsx`](../frontend/src/components/FinishBar.tsx) | The user uploads multiple clips, sets a dollar budget, and starts the asynchronous finishing run. |
| [`backend/api/finish.py`](../backend/api/finish.py) | The production API creates the worklist, runs ingest understanding, invokes cleanup, gathers specialist looks, prices proposals, invokes the ADK ranker, and persists the plan. |
| [`backend/supervisor/finishing_loop.py`](../backend/supervisor/finishing_loop.py) | Upload-order preservation, mandatory loudness and pickups, dependencies, budget dispatch, draft QC, handoff spine, and final reference assembly. |
| [`backend/supervisor/adk_finishing.py`](../backend/supervisor/adk_finishing.py) | One Google ADK specialist per proposal station plus the global finishing orchestrator. |
| [`backend/stations/run.py`](../backend/stations/run.py) | Explicit worker branches for the eleven current station names. |
| [`backend/jobs/worker.py`](../backend/jobs/worker.py) | Handoff validation and repair before downstream execution, authoritative terminal hooks, worker execution, and Grafana annotations. |
| [`backend/supervisor/mcp.py`](../backend/supervisor/mcp.py) | Hosted Grafana Cloud MCP and headless OSS `mcp-grafana` modes. |
| [`backend/supervisor/tools.py`](../backend/supervisor/tools.py) | Grafana MCP PromQL, Loki, Tempo, dashboard, annotation, and incident tool wrappers with autonomy checks on writes. |
| [`backend/supervisor/run_pulse.py`](../backend/supervisor/run_pulse.py) | Grafana-backed factory health, cost burn, ETA, and intervention summary. |

## Verify the walk-away path

The primary route is `POST /api/v1/projects/{project_id}/finish`. The browser reaches it through `FinishBar`. The request returns quickly because the long work runs in the background and the worker uses Firestore lease jobs.

The production order is:

| Phase | Runtime behavior | Code evidence |
|---|---|---|
| Upload | Files are uploaded one at a time from the browser. Passed ingest jobs are sorted by creation time, which becomes the upload order. | `FinishBar.tsx`, `collect_original_refs()` |
| Ingest | The ingest worker checks file integrity. It does not perform creative editing. | `backend/stations/ingest/run.py` |
| Understand | The ingest-understand Gemini agent watches extracted audio and frames, then stamps spoken words, speech presence, and scene description onto the shot. | `backend/supervisor/station_agents/ingest_understand.py`, `clip_context_after_ingest()` |
| Cleanup | Loudness and pickups worklists are created for every shot. Loudness runs first. Pickups uses the post-mix picture when one exists. | `mandatory_cleanup_items()`, `proposal_clip_uri()` |
| Gate | Optional proposal looks do not start until every cleanup item is terminal. | `cleanup_finished()` and `backend/api/app.py` terminal hook |
| Attendance | Delivery, dub, extend, corrections, relight, coverage, and camera language agents inspect each updated clip in upload order. | `PROPOSE_STATIONS`, `build_finishing_team()` |
| Price | The spend-pricing agent assigns a cost to each candidate proposal. Missing prices fall back to station defaults, and the failure is logged. | `backend/supervisor/station_agents/spend_pricing.py` |
| Rank | The ADK orchestrator reads all notes, scene context, handoff spine messages, upload order, dependencies, and remaining budget. | `run_orchestrator_rank_sync()` |
| Dispatch | The validated plan becomes waiting worklist rows. `dispatch_next()` queues only work that fits, has cleared dependencies, and does not violate one-generative-edit-per-shot rules. | `items_from_rank()`, `dispatch_next()` |
| Finish | Terminal jobs reconcile real spend, run draft-first QC where needed, append handoff notes, and refresh final references. | `on_finishing_terminal()`, `apply_draft_qc()`, `refresh_final_refs()` |

## Verify the eleven stations

The current worker vocabulary has eleven explicit dispatcher branches:

```text
ingest, loudness, delivery, spend, pickups, dub,
extend, corrections, relight, coverage, camera_language
```

They are not all used in the same phase. The walk-away flow uses ingest understanding, mandatory loudness and pickups, seven later-phase proposal lookers, and a separate spend-pricing agent. The older `spend` worker remains part of the broader Spend Control and Post Supervisor path. This is why a judge may see eleven worker branches but seven later-phase attendance rows.

## Verify the Grafana track

Martini Shot uses Grafana through MCP at runtime. The connector supports:

- Prometheus or Mimir queries for failure rate and p50 job duration.
- Loki queries for error and event narratives.
- Tempo trace search for a job’s cross-service path.
- Dashboard search and evidence deep links.
- Annotation writes for job outcomes and supervisor interventions.
- Incident writes for quarantine and spend-enforcement cases.

The write tools are autonomy-aware. In `propose_only`, the system returns a proposal instead of mutating Grafana. In the current default supervisor mode, the app boot writes the ranking-quality receipt and `act` spends the bounded night envelope. The production trigger currently fires on failed, quarantined, and needs-human terminal states. Additional signal types remain deferred and are disclosed in [`docs/pending-work.md`](pending-work.md).

The frontend Run Pulse presents the four judge-friendly answers:

1. **Factory or footage:** Is the run healthy according to Grafana metrics and Firestore state?
2. **Burn you can change:** Which jobs are costing the most?
3. **When wrap:** What is the estimated remaining time?
4. **Grabbed the wheel:** What annotations, incidents, or fallback actions did an agent record?

## Evidence map

The evidence directory contains real evaluation outputs and summaries. The current handoff records the following high-signal results:

| Evidence area | Current result |
|---|---|
| Spend pricing | Three live runs at 1.0. |
| Finishing rank | Three live runs at 0.9, 0.9, and 0.8. The suite mean clears the 0.8 threshold, although `fr-05` remains a known ordering miss. |
| Supervisor retry-once | Three live runs at 1.0. |
| Stage 1a lookers | Live evidence for relight, coverage, camera language, corrections, extend, visual QC, continuity, creative finishing, and related station judgments. |
| Omni media quality | Passing suites are archived with model and fallback fields. Veo-finished rows are not counted as Omni passes. |
| Repository checks | The repository still reports coverage below the 90% target for the full `make check` gate. |

The authoritative current status is in [`docs/memory/current-state.md`](memory/current-state.md), [`docs/memory/agent-handoffs.md`](memory/agent-handoffs.md), and [`docs/pending-work.md`](pending-work.md). Historical evidence should be read with its timestamp and should not override a newer handoff.

## Recommended live verification

Use two or three short clips. Upload them in a visibly meaningful order and choose a budget that can pay for one optional proposal but not every proposal. Then capture:

1. The upload and Finish interaction.
2. The worklist changing from `inspecting` to cleanup.
3. Ingest scene and spoken-word metadata.
4. Loudness and pickups rows for every clip.
5. The cleanup gate before proposal rows appear.
6. Specialist attendance notes, including at least one leave-it or empty outcome if the footage produces one honestly.
7. Spend prices and the ADK rank reason.
8. One queued and completed station job.
9. One waiting or paused item that did not fit.
10. Run Pulse plus one Grafana query, trace, annotation, or incident.

Do not fake a clean outcome or force every station to propose work. The product’s integrity rule is that an unwired or unavailable look is empty, not “all good.”

## Official submission checklist

The official Devpost page currently requires a hosted project URL, a public source repository with all code, assets, instructions, and a detectable open-source license, a public three-minute demo video in English or with English subtitles, and a selected partner track. The project must demonstrate actual runtime use of Google Cloud and the selected partner service.[1]

Before submission, verify:

- The hosted URL loads the actual Timeline product.
- The backend health endpoint returns successfully.
- The deployed worker is enabled and can process a real ingest job.
- The Grafana MCP connector is authorized in the chosen deployment mode.
- The demo video is no longer than three minutes and shows the running product.
- The repository points judges to this guide, the README, the code paths, and the evidence directory.
- The About section visibly detects the MIT License.
- The Devpost submission selects the Grafana Labs track and includes the hosted URL, repository URL, and video URL.

[1]: https://agentic-cinema.devpost.com/ "Agentic Cinema official overview and submission requirements"
