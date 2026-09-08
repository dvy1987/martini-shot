# Martini Shot

> **Upload the footage, set the budget, and walk away. Martini Shot runs a small post-production operation, watches the work, explains what needs attention, and spends only what the production envelope allows.**

Martini Shot is an **observability-native post-production cockpit** for film and television teams. It turns a batch of uploaded clips into a governed chain of media jobs. The system checks the files, understands what is actually in the footage, fixes essential sound and picture problems, asks specialist agents what would improve each clip, then uses a Gemini-powered orchestrator to decide which work is worth doing within budget.

The product is built for the **Grafana Labs track** of the [Agentic Cinema hackathon][1]. The backend uses Google Cloud services, Google ADK, Gemini, Firestore, Cloud Storage, FFmpeg, OpenTelemetry, and a live Grafana MCP connection. The repository is public and licensed under the MIT License.

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

## What makes the system agentic

Martini Shot has two related agentic layers. They should not be confused.

### 1. The finishing orchestrator

The walk-away finishing path uses a Google ADK attendance team. Each later-phase station has its own specialist agent and its own inspection tool. The agents watch frames and audio through the billed Gemini inspection path and return validated notes. A separate ADK orchestrator reads the complete set of notes and produces the global order, dependencies, dropped work, and reason. The production path converts that plan into worklist rows and dispatches the selected station jobs.[3] [5]

The specialist agents do not conduct an open-ended debate. Their interaction is a bounded production cycle:

> **Specialist inspection → structured proposal → global ADK ranking → validated worklist → real station execution.**

### 2. The Post Supervisor

A separate signal-fired supervisor path investigates failed, quarantined, or human-review jobs. It uses real specialist investigators, a Verification Agent, a Gemini Post Supervisor synthesis call, the approval state machine, and Grafana MCP annotations or incidents. Its default autonomy mode is **rank, then spend the configured night envelope**, currently defaulting to a `$20` supervisor envelope. `propose_only` is the kill switch. A separate `retry_once` mode remains available for tighter bounded recovery.[6] [7]

This separation is deliberate. The finishing orchestrator governs creative and compliance work across clips. The Post Supervisor investigates operational failures and governs bounded interventions.

## How Grafana is used at runtime

Grafana is not a logo in the README. Martini Shot connects to Grafana through the MCP protocol and uses the connection in the running system.

The current connector supports two modes:

| Mode | Runtime use |
|---|---|
| `hosted` | Grafana Cloud MCP at `https://mcp.grafana.com/mcp` using user-scoped OAuth and the `X-Grafana-URL` header. |
| `oss` | The `mcp-grafana` server binary over stdio using a Grafana service-account token. This is the headless Cloud Run path. |

The supervisor has MCP tools for Prometheus queries, Loki queries, Tempo trace search, dashboard search, annotations, and incidents. Query tools are available in all modes. Write tools such as annotations and incidents check the current autonomy mode before dispatch. In `propose_only`, the system returns a structured proposal instead of writing to Grafana.[8] [9]

The Run Pulse surface calls Grafana MCP and Firestore to answer four practical questions:

| Run Pulse answer | Evidence behind it |
|---|---|
| **Factory or footage** | PromQL failure-rate and p50-duration queries plus Firestore job state. |
| **Burn you can change** | The highest-cost jobs from real `cost_micros` records. |
| **When wrap** | Remaining worklist items combined with observed station timing. |
| **Grabbed the wheel** | Grafana annotations, incidents, and fallback events. |

The repository includes dashboards and alert rules as code in `infra/grafana/` plus a provisioning helper in `scripts/provision_grafana.py`. The helper defaults to a dry run. Passing `--yes` performs writes through Grafana MCP.[10] [11]

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
| Final playback | The backend maintains `final_refs` correctly. The current frontend plays individual alternates and shows the worklist. A dedicated single-player assembled-final surface is not the primary documented UI path, so the demo should show the final references and one real artifact rather than claiming a polished final-cut player that is not present. |
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
| `frontend/` | React/Vite Timeline, upload, worklist, alternates, approvals, and Run Pulse surfaces. |
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

## License

Martini Shot is released under the [MIT License][25].

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
[25]: LICENSE "MIT license"
