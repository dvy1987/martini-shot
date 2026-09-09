# Martini Shot

> **Upload the footage, set the budget, and walk away. Martini Shot runs a small post-production operation, watches the work, explains what needs attention, and spends only what the production envelope allows.**

Martini Shot is an **observability-native post-production supervisor** for film and television teams. It turns a batch of uploaded clips into a governed chain of media jobs: the system checks the files, understands what is actually in the footage, fixes essential sound and picture problems, asks specialist agents what work is justified, and uses a Gemini-powered orchestrator to decide which work is worth doing within budget.

The core value proposition is simple: a supervisor can delegate a messy, expensive post-production operation without delegating accountability. Martini Shot preserves the evidence behind each decision, keeps spending inside the production envelope, prevents unsafe media replacement, and explains the run through Grafana-backed health, cost, timing, traces, logs, and interventions.

The product is built for the **Grafana Labs track** of the [Agentic Cinema hackathon][1]. The backend uses Google Cloud services, Google ADK, Gemini, Firestore, Cloud Storage, FFmpeg, OpenTelemetry, and a live Grafana MCP connection. The repository is licensed under Apache 2.0.

## The problem

Post-production is a coordination problem disguised as a sequence of creative tasks. A supervisor must manage incoming media, integrity checks, sound levels, visual defects, dubs, captions, delivery requirements, optional finishing ideas, approvals, budgets, retries, and handoffs across many clips and stations.

That work is usually fragmented across media tools, job queues, spreadsheets, cloud logs, dashboards, and approval records. Bad inputs can travel too far, generative suggestions can consume budget without enough impact, automation can become difficult to audit, and a new render can damage continuity or overwrite an approved version before anyone has a safe review point.

Martini Shot addresses this operational gap. It is not a chatbot that merely recommends edits and not a generic video generator. It is a governed production system that makes creative automation accountable.

## The product in one minute

A post-production supervisor should not have to discover a broken file, a bad mix, a damaged shot, an unnecessary render, or a runaway retry loop by opening many tools and reading logs one job at a time. Martini Shot gives the supervisor one timeline and one governed worklist.

The user chooses the clips in order and sets a budget. Martini Shot then follows this house order:

1. It checks each uploaded file. A corrupt file is stopped before downstream work.
2. A Gemini ingest-understanding agent watches the original clip and records the words that are actually spoken plus a scene description. Silence is valid and produces an empty spoken-word field rather than invented dialogue.
3. A loudness agent and job always run. The system listens, classifies the audio context, mixes when needed, re-measures the result, and carries level context forward for continuing shots.
4. A pickups agent and job always run on the post-mix picture. It measures visual instability, asks a Gemini vision QC agent whether repair is needed, and uses the real media-generation path only when a repair is justified.
5. Martini Shot waits until every uploaded clip has completed the mandatory mix and pickups steps.
6. Seven later-phase specialists inspect the updated clips in upload order: delivery, dub, extend, corrections, relight, coverage, and camera language. Each returns a structured **must fix**, **nice improvement**, or **leave it alone** note.
7. A spend-pricing agent estimates the cost of every remaining proposal.
8. A Gemini orchestrator weighs impact, cost, dependencies, upload order, scene context, and handoff notes. It returns an ordered plan and drops work that does not fit.
9. The queue runs the selected real station jobs. Work that does not fit remains waiting or becomes paused when the envelope is exhausted.
10. The playable references always contain the originals plus only artifacts from jobs that actually passed. Failed, paused, incomplete, and human-review artifacts stay out of the cut.

This is not a chatbot that merely recommends edits. The specialist proposals become validated worklist items, the orchestrator selects and orders them, and the queue dispatches real station jobs. The important safety boundary is that generated media is attached as an alternate and never silently overwrites a locked cut.[2] [3] [4]

The user-facing product includes the Timeline, Suggestions, Approvals, Analytics/Run Pulse, Reports, Decisions, Changes, and Studio surfaces. Operator notes and decision history make the reasoning legible without turning the application into an unbounded chat interface. Real uploaded production clips are the primary input; the core ingest, cleanup, dubbing, delivery, governance, and observability paths do not require generated media. Studio supports approval-tracked, bounded Omni edits for corrections and other controlled finishing operations; the production path records the actual render model and fallback status so a Veo result is never mislabeled as an Omni pass.

Generative finishing is optional rather than a prerequisite for the product to be useful. Omni’s refusal to process some public-domain or public-commons source media is a limitation of that optional edit request, not of Martini Shot’s ability to ingest, measure, clean up, dub, deliver, or supervise real clips. The original remains valid input, and the configured fallback or no-change path remains explicit in job state.

## The solution in one workflow

Martini Shot follows a controlled production order:

1. **Ingest:** validate the uploaded media, inspect the container, check decodability and audio presence, and quarantine files that fail.
2. **Understand:** use Gemini to establish what is actually spoken and what is visible in the scene. Silence is represented honestly rather than filled with invented dialogue.
3. **Mandatory cleanup:** run loudness and pickup checks for every uploaded clip. Loudness uses measured audio and re-measures the result; pickups use the post-mix picture when available.
4. **Specialist attendance:** have delivery, dubbing, extending, corrections, relighting, coverage, and camera-language specialists inspect the updated clips. Each can propose a necessary fix, a useful improvement, or no action.
5. **Price and rank:** estimate the cost of each candidate and have a Google ADK orchestrator rank the complete proposal set using impact, cost, dependencies, upload order, scene context, and handoff notes.
6. **Governed dispatch:** queue only work that clears its dependencies, obeys per-shot constraints, and fits the remaining budget. Work that does not fit waits or pauses instead of being silently dropped.
7. **Safe finishing:** treat generated media as an alternate. Apply draft-first and visual-quality gates where required, preserve the approved cut, and refresh final references only with original media and artifacts that actually passed. If no transformation passes, the original remains the playable reference.
8. **Operational explanation:** use Run Pulse and Grafana MCP to show whether a problem is in the footage or the factory, which work is consuming budget, when the run is likely to wrap, and what automation already changed.

The separate Post Supervisor path investigates failed, quarantined, and human-review jobs. It queries the evidence, verifies proposed interventions, applies bounded autonomy and budget controls, and records the resulting action through Grafana annotations or incidents when the configured mode permits writes.

## What makes the system agentic

Martini Shot has two related agentic layers. They should not be confused.

### 1. The finishing orchestrator

The walk-away finishing path uses a Google ADK attendance team. Each later-phase station has its own specialist agent and its own inspection tool. The agents watch frames and audio through the billed Gemini inspection path and return validated notes. A separate ADK orchestrator reads the complete set of notes and produces the global order, dependencies, dropped work, and reason. The production path converts that plan into worklist rows and dispatches the selected station jobs.[3] [5]

The specialist agents do not conduct an open-ended debate. Their interaction is a bounded production cycle:

> **Specialist inspection → structured proposal → global ADK ranking → validated worklist → real station execution.**

### 2. The Post Supervisor

A separate signal-fired supervisor path investigates failed, quarantined, or human-review jobs. It uses real specialist investigators, a Verification Agent, a Gemini Post Supervisor synthesis call, the approval state machine, and Grafana MCP annotations or incidents. Its default autonomy mode is **rank, then spend the configured night envelope**, currently defaulting to a `$20` supervisor envelope. `propose_only` is the kill switch. A separate `retry_once` mode remains available for tighter bounded recovery.[6] [7]

This separation is deliberate. The finishing orchestrator governs creative and compliance work across clips. The Post Supervisor investigates operational failures and governs bounded interventions.

Martini Shot is agentic because its agents participate in a real decision-and-execution loop rather than producing an isolated answer. Gemini and ADK provide perception, judgment, prioritization, and synthesis. Deterministic code remains authoritative for file integrity, measurement, schema validation, dependencies, budgets, leases, draft-first rules, approval transitions, and final-reference safety. This hybrid boundary turns model judgment into controlled production work.

## How Grafana is used at runtime

Grafana is not a logo in the README. Martini Shot connects to Grafana through the MCP protocol and uses the connection in the running system.

The current connector supports two modes:

| Mode | Runtime use |
|---|---|
| `hosted` | Grafana Cloud MCP at `https://mcp.grafana.com/mcp` using user-scoped OAuth and the `X-Grafana-URL` header. |
| `oss` | The `mcp-grafana` server binary over stdio using a Grafana service-account token. This is the headless Cloud Run path. |

The supervisor has MCP tools for Prometheus queries, Loki queries, Tempo trace search, dashboard search, annotations, and incidents. Query tools are available in all modes. Write tools such as annotations and incidents check the current autonomy mode before dispatch. In `propose_only`, the system returns a structured proposal instead of writing to Grafana.[8] [9]

The Run Pulse surface calls Grafana MCP and Firestore to answer four practical questions. Firestore remains the source of truth for job and worklist state; Grafana contributes factory health, duration, annotations, and trace evidence.

The Run Pulse surface answers:

| Run Pulse answer | Evidence behind it |
|---|---|
| **Factory or footage** | PromQL failure-rate and p50-duration queries plus Firestore job state. |
| **Burn you can change** | The highest-cost jobs from real `cost_micros` records. |
| **When wrap** | Remaining worklist items combined with observed station timing. |
| **Grabbed the wheel** | Grafana annotations, incidents, and fallback events. |

The repository includes dashboards and alert rules as code in `infra/grafana/` plus a provisioning helper in `scripts/provision_grafana.py`. The helper defaults to a dry run. Passing `--yes` performs writes through Grafana MCP.[10] [11]

This is the Grafana-track differentiator: Grafana is not a logo in the README or a screenshot at the end of the demo. It is the evidence layer and intervention surface for an agentic creative operation. The supervisor uses telemetry to investigate a failed job, compare cost and duration, enforce bounded responses, and leave an auditable record of what automation changed. In `propose_only` mode, the same write path returns a structured proposal instead of mutating Grafana.

## What a judge can verify quickly

| Claim | Where to verify it |
|---|---|
| FinishBar uploads clips, accepts a budget, and starts the walk-away run | [`frontend/src/components/FinishBar.tsx`][12] and [`backend/api/finish.py`][2] |
| The production application installs the finish routes and worker | [`backend/api/app.py`][13] and [`backend/api/spine.py`][14] |
| Ingest order, mandatory cleanup, proposal stations, budget dispatch, and final references | [`backend/supervisor/finishing_loop.py`][3] |
| Each specialist is an ADK agent and the orchestrator consumes the complete proposal bag | [`backend/supervisor/adk_finishing.py`][5] |
| All worker-recognized stations have explicit dispatcher branches | [`backend/stations/run.py`][15] |
| Handoff repair runs before downstream execution and reports to the orchestrator spine | [`backend/jobs/worker.py`][16] and [`backend/jobs/handoff.py`][17] |
| Grafana MCP is imported, configured, and called at runtime | [`backend/supervisor/mcp.py`][8] and [`backend/supervisor/tools.py`][9] |
| Run Pulse joins Grafana MCP reads with job and worklist state | [`backend/supervisor/run_pulse.py`][18] and [`frontend/src/components/RunPulse.tsx`][19] |
| Real-model evaluations and outcomes | [`docs/evidence/`][20] and the current readiness record [`docs/pending-work.md`][21] |

## The three-minute demo story

The demo should be a product walkthrough, not a cinematic trailer. The official hackathon requires a public video of no more than three minutes in English or with English subtitles.[1]

| Time | What the judge sees | Why it matters |
|---:|---|---|
| 0:00–0:20 | The Timeline screen, the Upload clips control, and a deliberately small budget | Establishes the user, the problem, and the walk-away promise. |
| 0:20–0:45 | Two or three clips uploaded in visible order and the Finish action | Shows a real web product, not a static architecture diagram. |
| 0:45–1:15 | Ingest understanding followed by loudness and pickups rows | Shows that essential work is sequenced and that the original clip receives context before later decisions. |
| 1:15–1:45 | Attendance rows from the seven later-phase specialists | Shows that different agents look for different kinds of problems and can return a leave-it result instead of inventing work. |
| 1:45–2:15 | Spend estimates, the ADK rank reason, dependencies, and the worklist | Shows the orchestrator making a global decision rather than executing every suggestion. |
| 2:15–2:40 | One real station artifact, one waiting or paused item, and the original-plus-passed final references | Shows governed spend and the final-cut safety rule. |
| 2:40–3:00 | Run Pulse and one Grafana trace, annotation, query, or incident | Proves that Grafana MCP is part of the runtime control loop. |

Use a two-clip or three-clip rehearsal first. A small budget should fund one meaningful optional job and leave at least one other proposal waiting. The exact result is content-dependent because stations are allowed to return leave-it or empty notes. That variability is a feature of the product, not a canned script.

## Current implementation status

The repository is beyond a scaffold and the latest branch contains the production paths described above. The following limitations should remain visible rather than being hidden behind marketing language.

| Area | Current truth |
|---|---|
| Walk-away finishing | Implemented from the main Timeline UX through FastAPI, Firestore lease jobs, the worker, the seven specialist lookers, spend pricing, ADK ranking, and budgeted dispatch. |
| Mandatory cleanup | Loudness and pickups rows are created for every uploaded shot. A clean or unmeterable clip may not create a new media artifact, but the QC or mix job still runs. |
| All eleven worker stations | The dispatcher recognizes `ingest`, `loudness`, `delivery`, `spend`, `pickups`, `dub`, `extend`, `corrections`, `relight`, `coverage`, and `camera_language`. The walk-away path uses ingest understanding, loudness, pickups, seven later-phase lookers, and a separate spend-pricing agent. The older `spend` worker branch remains part of the broader supervisor path. |
| Budget and autonomy | Finishing uses the user-selected project budget. The Post Supervisor uses the separate night envelope and daily cap. App boot writes the current ranking-quality receipt and defaults the supervisor to `act`; `propose_only` remains the kill switch. |
| Evaluations | Live evidence exists for spend pricing, finishing rank, supervisor retry-once, ingest understanding, Stage 1a lookers, and Omni quality suites. The finishing rank suite clears the mean threshold but includes a known failing `fr-05` case where Extend was ordered before Loudness. |
| Test gate | `make check` coverage is still below the project’s 90% target. Run the repository checks before treating the branch as a final release artifact. |
| Final playback | The backend maintains `final_refs` correctly. The current frontend’s Final cut strip selects the latest successful After for each original clip in upload order and can play the resulting playlist. If no successful After exists, the original remains the playable reference. |
| Failure signals | The Post Supervisor’s production trigger currently fires for failed, quarantined, and needs-human terminal states. Other signal taxonomy entries remain intentionally deferred. |
| Media generation | Product behavior is Omni first with Veo fallback when needed. Evaluation evidence must not label a Veo-finished row as an Omni pass. |

## Quick start for a judge or developer

### Prerequisites

You need Python 3.12, Node.js with npm, FFmpeg and FFprobe, a Google Cloud project with Firestore and Cloud Storage, Gemini or Vertex access, and a Grafana Cloud stack or a Grafana OSS MCP server. The full environment variable surface is in [`.env.example`][22].

### Backend

```bash
git clone https://github.com/dvy1987/martini-shot.git
cd martini-shot
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m pip install -r requirements-dev.txt
cp .env.example .env
uvicorn backend.api.main:app --host 0.0.0.0 --port 8080
```

The backend reads process environment first, then `.env`, then safe dataclass defaults. It fails closed when the Grafana MCP configuration is incomplete or when the API key is missing. `/api/v1/health` is public. Other API routes require `X-API-Key`. The long finishing run is asynchronous, so the `POST /api/v1/projects/{id}/finish` response is only the start signal.

### Frontend

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0 --port 5000
```

Set `VITE_API_BASE_URL` to the backend origin and `VITE_API_KEY` to the backend read key before building the frontend. The current Replit workflow serves the Vite app on port 5000 and the repository deployment target is Cloud Run.[23]

### Checks

```bash
make lint
make typecheck
make test
make eval-check
make integrity
make check

cd frontend
npm run typecheck
npm run lint
npm run test
npm run build
```

The full gate can require cloud credentials and real external services. If a check is not run, report that fact rather than replacing it with a simulated result.

## Backend deployment

The repository includes [`deploy.sh`][24] for Cloud Run. It builds from the repository, sets the service to listen on port 8080, allows unauthenticated Cloud Run ingress, and relies on the application’s own `X-API-Key` gate for API protection. It installs the Linux `mcp-grafana` binary in the container and supports `MCP_MODE=oss` for headless Grafana MCP operation.

```bash
export GCP_PROJECT_ID="your-project"
./deploy.sh
```

The script prints the Cloud Run URL and verifies `/api/v1/health`. Do not commit `.env`, tokens, service-account JSON files, or generated deployment secrets.

## Repository map

| Path | Purpose |
|---|---|
| `backend/api/` | FastAPI application, upload, finish, worklist, SSE, approvals, reports, and health routes. |
| `backend/jobs/` | Firestore lease queue, worker, handoff validation, and terminal hooks. |
| `backend/stations/` | Explicit worker implementations for the production station vocabulary. |
| `backend/supervisor/adk_finishing.py` | Specialist looker team and ADK finishing orchestrator. |
| `backend/supervisor/finishing_loop.py` | House order, worklist, budget dispatch, QC, handoffs, and final references. |
| `backend/supervisor/` | Post Supervisor, Grafana MCP tools, run pulse, autonomy, and budgeted interventions. |
| `frontend/` | React/Vite Timeline, upload, worklist, alternates, approvals, Suggestions, Decisions, Changes, Studio, Reports, and Run Pulse surfaces. |
| `infra/grafana/` | Dashboards and alert rules as code. |
| `scripts/` | Evaluations, Grafana provisioning, deployment and evidence helpers. |
| `docs/evidence/` | Real evaluation and integration evidence. |
| `docs/judge-guide.md` | Judge-facing verification map and submission checklist. |

## Hackathon alignment

Martini Shot addresses the challenge with a real media workflow for post-production supervisors and studio crews. It uses Gemini and Google ADK for specialist inspection, scene understanding, pricing, orchestration, media judgment, and bounded supervisor synthesis. It uses Google Cloud Firestore, Cloud Storage, Cloud Run, and Vertex or Gemini runtime services. It uses Grafana MCP as a runtime integration, not merely as a dashboard export.

The project is designed against the four official judging criteria:

| Criterion | Martini Shot proof |
|---|---|
| Technological implementation | Google ADK agents, Gemini media and text calls, Firestore lease jobs, Cloud Storage artifacts, OpenTelemetry, Grafana MCP queries and writes, and real EDD evidence. |
| Design | A clear upload → cleanup → specialist attendance → pricing → orchestration → governed execution flow in one Timeline experience. |
| Potential impact | A specific operational problem for post-production teams: coordinating expensive, failure-prone work across many clips and stations. |
| Quality of idea | Grafana’s observability and MCP action surface are used as the accountable control plane for a creative media operation, not as a generic SRE chatbot. |

The official submission also requires a hosted project URL, a public repository with a detectable open-source license, and a public three-minute demo video. The final Devpost entry must provide those URLs and select the Grafana Labs track.[1]

## Submission description

### What we built

We built Martini Shot, an observability-native post-production supervisor for film and television teams. A supervisor uploads clips in order, sets a budget, and starts a walk-away finishing run. Martini Shot validates and understands the footage, performs mandatory loudness and visual cleanup, gathers specialist finishing proposals, prices and ranks them, dispatches the work that fits the envelope, and preserves a clear distinction between original media, approved alternates, waiting work, failed work, and human-review work.

The product combines a Timeline, governed worklist, Suggestions, Approvals, Decisions, Changes, Studio, Reports, playable clip references, and Analytics/Run Pulse. It supports controlled generative finishing through an Omni-first path with Veo fallback where configured, multilingual dubbing through Chirp 3 HD voices, deterministic media QC, and approval-safe alternates.

### How it works

The browser starts an asynchronous backend run rather than waiting for a long model call inside an HTTP request. A Firestore-backed lease queue processes the footage through the house order. Ingest checks integrity and quarantines invalid files. Gemini establishes scene and spoken-word context. Loudness and pickups run for every clip before optional finishing proposals are considered.

Seven specialist agents inspect the updated clips for delivery, dubbing, extending, corrections, relighting, coverage, and camera language. Their structured notes are priced and passed to a Google ADK finishing orchestrator. The orchestrator returns a ranked plan with dependencies and reasons. The dispatcher queues only work that fits the remaining budget and clears the required gates.

Station workers execute real media jobs using Cloud Storage artifacts and FFmpeg-based processing. Generative outputs are recorded as alternates. Draft-first and visual QC gates prevent an unverified render from becoming the approved result. Passed artifacts are added to final references; incomplete, failed, paused, and human-review artifacts remain out of the cut.

OpenTelemetry sends metrics, logs, and traces to Grafana. The Post Supervisor and Run Pulse use Grafana MCP to query Prometheus/Mimir, Loki, and Tempo, explain failures and spend, estimate remaining time, and record interventions through annotations or incidents when permitted by the autonomy mode.

### Technologies used

The backend uses Python, FastAPI, Uvicorn, Google Gen AI, Google Agent Development Kit, Vertex AI, Gemini, Gemini Omni, Veo, Google Cloud Text-to-Speech with Chirp 3 HD voices, Cloud Firestore, Cloud Storage, Cloud Run, Cloud IAM/IAM Credentials, FFmpeg, and FFprobe. The frontend uses React, TypeScript, Vite, React Router, Tailwind CSS, TanStack React Query, Framer Motion, and Lucide React. Testing and quality checks use Pytest, Mypy, Ruff, Vitest, Testing Library, and ESLint. The Grafana-track integration uses Grafana Cloud, Grafana MCP, Prometheus/Mimir, Loki, Tempo, OpenTelemetry, and the Grafana MCP Server. Docker packages the backend; GitHub provides source control; Replit supports the frontend workflow.

### What we learned

Reliable agentic media software is not created by placing a language model in front of a render endpoint. It requires a complete operational loop in which agents have clear roles, return validated contracts, and hand decisions to deterministic enforcement paths. Observability must be designed in from the beginning because a dashboard added after the fact cannot reconstruct the evidence, cost, dependency, and approval context needed to govern an autonomous decision.

We also learned that bounded autonomy is more useful than unrestricted autonomy. Budgets, lease ownership, retry limits, draft-first rendering, continuity locks, approval transitions, and final-reference rules turn creative agents into controlled production participants. Abstention is a quality behavior: a specialist that returns leave-it-alone is more trustworthy than one that invents work for every clip. Finally, model capabilities and service behavior must be measured separately, so the system records whether a render used Omni or Veo fallback and never reports a fallback result as an Omni pass.

The strongest product story is not “AI can make video.” It is that **a post-production supervisor can delegate a messy, expensive operation without delegating accountability**.

## License

Martini Shot is released under the [Apache License 2.0][25].

## References

[1]: https://agentic-cinema.devpost.com/ "Agentic Cinema official overview and submission requirements"
[2]: backend/api/finish.py "Production finishing API"
[3]: backend/supervisor/finishing_loop.py "Walk-away order, worklist, dispatch, budget, QC, and final references"
[4]: backend/supervisor/rank.py "Validated rank plan and proposal conversion"
[5]: backend/supervisor/adk_finishing.py "Google ADK specialist team and finishing orchestrator"
[6]: backend/supervisor/team.py "Production Post Supervisor wiring and trigger path"
[7]: backend/supervisor/budget_loop.py "Autonomy mode, night envelope, daily cap, and ACT gate"
[8]: backend/supervisor/mcp.py "Grafana MCP hosted and OSS connector"
[9]: backend/supervisor/tools.py "Grafana MCP query and write tools"
[10]: backend/supervisor/run_pulse.py "Grafana-backed Run Pulse assembly"
[11]: scripts/provision_grafana.py "Grafana MCP dashboard provisioning"
[12]: frontend/src/components/FinishBar.tsx "Upload and Finish user experience"
[13]: backend/api/app.py "Application boot, worker, and act-gate setup"
[14]: backend/api/spine.py "Core API route installation"
[15]: backend/stations/run.py "Worker station roster and dispatcher"
[16]: backend/jobs/worker.py "Production worker and handoff gate"
[17]: backend/jobs/handoff.py "Handoff repair and blocking rules"
[18]: backend/supervisor/run_pulse.py "Run Pulse backend"
[19]: frontend/src/components/RunPulse.tsx "Run Pulse frontend"
[20]: docs/evidence/ "Real evaluation and integration evidence"
[21]: docs/pending-work.md "Current readiness and limitations"
[22]: .env.example "Environment template"
[23]: .replit "Current Replit development and deployment configuration"
[24]: deploy.sh "Cloud Run deployment script"
[25]: LICENSE "Apache License 2.0"
