# Grafana Track — Distilled Notes

Everything below is distilled from `agentic-cinema.md`. Treat that file as source of truth.

## 1. Hard requirements (Stage One pass/fail)

- **Grafana at runtime, via MCP.** The agent must call tools on `https://mcp.grafana.com/mcp` (hosted) or the OSS `grafana/mcp-grafana` server. AI Observability alone does NOT satisfy this.
- **Gemini + Google Cloud only for AI/agent work** (ADK, Agent Engine / Vertex AI Agent Platform, Gemini models). No OpenAI/Anthropic/AWS/Microsoft models, no third-party agent frameworks' model calls. Non-AI services (hosting, DBs, web frameworks) are fine.
- **Theme lock:** solve a bottleneck across the *entertainment & media value chain* for filmmakers, screenwriters, studio crews, or fans. A pure DevOps/SRE tool with no media angle will fail Stage One screening ("reasonably addresses the challenge").
- **Platform:** web, Android, or iOS. Web is easiest to host + demo.
- **New project only**, created during the contest window (Jul 27 – Sep 9, 2026).
- Public repo (GitHub/GitLab/Bitbucket) + OSI license visible at repo top; Google Cloud and Grafana usage must be **imported/called in code**, not just README-named. Accepted Google packages: `google-adk`, `google-genai`, `google-generativeai`, `google-cloud-aiplatform`.
- Hosted project URL + ≤3-min English demo video on YouTube/Vimeo showing it actually running.
- Team size ≤ 4.

## 2. Grafana Cloud MCP — what the agent can actually do

Endpoint: `https://mcp.grafana.com/mcp` (Streamable HTTP; SSE unsupported).
Auth: OAuth 2.1 browser flow, one-time; token refreshes ~30 days. Header `X-Grafana-URL: https://<stack>.grafana.net`.
Unattended/serverless caveat: hosted MCP is interactive-auth only → run the agent where the browser auth can happen once (dev machine is fine for demo), OR use OSS mcp-grafana with a service-account token for headless runs. ADK has first-class Grafana Cloud MCP support.

Tool families (~60+):

| Family | Tools | Idea fuel |
|---|---|---|
| Prometheus/Mimir | range/instant queries, metric names, labels | live "health" of any instrumented system |
| Loki | LogQL queries, label discovery | event streams, error narratives |
| Tempo | trace search, trace detail, service graphs | multi-hop request journeys |
| Dashboards | search, get panel info, generate links, annotations | human-review artifacts, visual evidence |
| Alerts/IRM (OnCall) | list/get alerts & incidents, manage schedules/shifts | escalation logic, duty rosters |
| Pyroscope | profiling data | resource hotspots |
| Admin | datasources, teams, users | provisioning workflows |
| OnCall UI links | deep-link back into Grafana | every agent action leaves a reviewable artifact |

## 3. Judging criteria (equal weights — design for all four)

1. **Technological Implementation** — depth of Google Cloud + Grafana usage. Multi-tool MCP chains (alert → LogQL → PromQL → Tempo → annotation) score better than single-query wrappers.
2. **Design** — complete product feel, not PoC: real UI, real workflow, polished demo.
3. **Potential Impact** — credible, specific problem + audience, demonstrated end-to-end.
4. **Quality of the Idea** — creative, non-obvious fusion of observability × media domain.

## 4. Free-tier demo-data recipes (no production infra needed)

- **k6 load tests → Prometheus**: script synthetic traffic spikes against any API; ship metrics via Prometheus remote-write to Grafana Cloud.
- **OpenTelemetry SDK → traces/logs**: wrap any Python/Node service (or the agent itself); OTLP endpoints are free-tier friendly.
- **Synthetic log generator → Loki**: cron/Cloud Scheduler job emitting realistic log lines (e.g., render-farm job logs, stream CDN logs).
- **Grafana Alloy**: single-agent collector for metrics+logs+traces from local Docker compose stacks.
- **Alert rules as code**: define firing alerts via provisioning/API so the demo has real incidents to investigate.
- **AI Observability (recommended bonus)**: OTel-instrument the Gemini agent itself → live token cost/latency/tool-call dashboards *inside your own demo*. Judges see the meta-story.

## 5. Timeline sketch (15 days, solo)

- D1–2: Grafana Cloud free stack, accept Assistant T&Cs, browse MCP tools from an MCP client, pick idea, write plan.
- D3–5: Data plumbing (synthetic incidents + dashboards), agent skeleton on ADK with Grafana MCP toolbox.
- D6–9: Core agentic loop (multi-step investigation), web UI, persistence.
- D10–11: Polish UX; wire AI Observability instrumentation.
- D12–13: Deploy (web app + wherever MCP auth can complete), record 3-min video, write README.
- D14–15: Buffer; submit early — never submit on deadline day.

## 6. Differentiation tactics for this track

Most entries will be "SRE copilot for movie-streaming infra" (generic). Stand out by:
- Making the **domain persona** native (director, showrunner, post supervisor), not a skin on a chatbot.
- Using **IRM/alerts + annotations + dashboard links** (write-path tools), not just read-only queries.
- Showing **agent-observes-itself** in the demo (AI Observability dashboards of the agent doing the observing).
- A crisp "before: 45-min war room / after: 90-second briefing" narrative with numbers.
