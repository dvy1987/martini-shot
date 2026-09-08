# Grafana Track Notes

This document is the current Grafana Labs track reference for Martini Shot. The official requirements are at the [Agentic Cinema Devpost page](https://agentic-cinema.devpost.com/) and its [official rules](https://agentic-cinema.devpost.com/rules). The repository’s current implementation is the authority for what Martini Shot claims to do.

## The track story

Martini Shot applies Grafana’s observability and MCP action surface to a media workflow that is normally coordinated through spreadsheets, file shares, render queues, and delayed status reports.

The media operation is real: clips arrive, jobs run, artifacts are produced, failures and costs are recorded, and a supervisor must decide what to investigate or run next. Grafana is the evidence and control plane. OpenTelemetry emits metrics, traces, and logs. The supervisor reads Grafana through MCP, follows job evidence across Prometheus, Loki, and Tempo, and records accountable annotations or incidents when autonomy allows.

The creative finishing orchestrator is a separate but cooperating ADK path. It reads specialist media proposals and ranks budgeted work. Do not describe the finishing rank call as if it were a Grafana query. Describe the two connections accurately:

> **Gemini and Google ADK reason about media proposals. Grafana MCP gives the supervisor an observable, auditable view of the operation and lets bounded interventions leave a durable trail.**

## What judges should see

A convincing demo should show a real uploaded clip batch moving through the product, then use Grafana MCP to answer at least one operational question that the browser alone cannot answer cleanly:

- Which station is failing or slowing down?
- Which job consumed the most budget?
- What trace connects the failed job to its downstream handoff?
- What annotation or incident did the supervisor record?
- Did an Omni-to-Veo fallback occur and where is it recorded?

The strongest three-minute sequence is the walk-away house order in the README and [`docs/judge-guide.md`](judge-guide.md), followed by Run Pulse and one direct Grafana evidence link.

## Actual runtime connector

The implementation is in `backend/supervisor/mcp.py`.

| Mode | How it works | Best use |
|---|---|---|
| `hosted` | Connects to `https://mcp.grafana.com/mcp` using Streamable HTTP and the `X-Grafana-URL` stack header. OAuth is user-scoped and requires one-time browser consent. | Local development or a demo environment where OAuth can be completed. |
| `oss` | Launches the `mcp-grafana` binary over stdio with `GRAFANA_URL` and `GRAFANA_SERVICE_ACCOUNT_TOKEN`. | Headless Cloud Run operation. |

The connector fails closed when `MCP_MODE`, `GRAFANA_STACK_URL`, or the mode-specific credentials are missing. It does not silently replace MCP with raw Grafana HTTP calls.

## MCP capabilities used by the product

The wrappers are registered in `backend/supervisor/tools.py` and the connector resolves the actual server tool names at runtime.

| Capability | Martini Shot use | Runtime surface |
|---|---|---|
| PromQL | Failure rate, p50 duration, station health, and cost-related metrics. | `query_promql()` |
| Loki / LogQL | Error and event narratives for failed jobs and supervisor cases. | `query_loki()` |
| Tempo / TraceQL | Cross-service job traces and trace enrichment. | `search_traces()` |
| Dashboards | Evidence discovery and judge-friendly deep links. | `search_dashboards()` and generated links |
| Annotations | Job outcomes and supervisor interventions with job or project context. | `add_annotation()` |
| Incidents | Quarantine and spend-enforcement cases. | `create_incident()` |

Annotations and incidents are **act-class tools**. The autonomy guard checks the current mode before a write. In `propose_only`, the tool returns a proposal without mutating Grafana. This preserves the product’s fail-closed behavior while still showing the judge what the agent wanted to do.

## Run Pulse

`GET /api/v1/projects/{project_id}/run-pulse` assembles a current run snapshot from Firestore and Grafana MCP. The frontend displays four answers:

| Panel | What it explains |
|---|---|
| Factory or footage | Whether the run looks healthy from failure metrics and current work. |
| Burn you can change | The highest-cost jobs and their actual recorded spend. |
| When wrap | Estimated time remaining using the worklist and observed station timing. |
| Grabbed the wheel | Recent annotations, incidents, and fallback events. |

The backend implementation is `backend/supervisor/run_pulse.py` and the frontend is `frontend/src/components/RunPulse.tsx`.

## Dashboards and provisioning

The dashboards and alert rules are versioned in `infra/grafana/`:

- `station-health.json`
- `finishing-cost.json`
- `interventions.json`
- `alerts/run-pulse.yaml`

`scripts/provision_grafana.py` validates the files and performs a dry run by default. Passing `--yes` writes through Grafana MCP and should be treated as an owner-approved operational action.

## Track compliance map

| Official concern | Martini Shot evidence |
|---|---|
| Functional agent or multi-agent network | Google ADK station team, finishing orchestrator, Post Supervisor specialists, Verification Agent, and Gemini synthesis. |
| Google Cloud | Firestore lease queue, Cloud Storage media, Cloud Run deployment, Google authentication and Gemini or Vertex runtime calls. |
| Partner integration | Runtime Grafana MCP connector, registered MCP tools, Grafana-backed Run Pulse, annotations, incidents, and dashboards. |
| Real media workflow | Upload, ingest, scene understanding, loudness, pickups, specialist proposals, budgeted execution, alternates, and worklist. |
| Public proof | README, Judge Guide, evidence directory, hosted product URL, and three-minute running-product video. |

## Honest limitations

The current Post Supervisor trigger vocabulary is deliberately narrower than the full signal taxonomy. Production triggers currently cover failed, quarantined, and needs-human terminal states. Stuck leases, crash recovery, QC breach, spend breach, runaway, daily budget, and dub breach signals remain explicitly deferred in `docs/pending-work.md`.

The current finishing rank evidence clears the mean quality threshold but includes a known `fr-05` ordering miss where Extend was placed before Loudness. The repository also reports coverage below the 90% target for the full `make check` gate. These limitations should be disclosed rather than omitted from the submission narrative.
