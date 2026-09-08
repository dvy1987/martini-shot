# Agentic Cinema Hackathon Requirements Reviewed

**Reviewed:** 2026-09-08

**Official overview:** https://agentic-cinema.devpost.com/

**Official rules:** https://agentic-cinema.devpost.com/rules

## Current requirements relevant to Martini Shot

The official overview says the project must be a functional agent powered by Gemini and Google Cloud Agent Builder that integrates a partner entity product or MCP to power a real media and entertainment workflow.

The submission must include a publicly hosted project URL, a public open-source repository containing source code, assets, and instructions, a complete open-source license file visible to judges, a public three-minute demo video uploaded to YouTube or Vimeo in English or with English subtitles, the selected partner track, and the completed Devpost form.

The repository must demonstrate actual runtime use of Google Cloud and the chosen partner service. Naming a service in the README is not sufficient. The relevant service must be imported and called in code.

The official judging criteria are technological implementation, design, potential impact, and quality of the idea. Technological implementation covers how effectively the project uses Google Cloud and partner services. Design asks whether the product experience is complete and coherent rather than only a technical proof of concept. Potential impact asks for a credible problem, a real audience, and evidence that the demonstrated solution addresses it. Quality of the idea asks whether the use of Google Cloud and partner services is creative and non-obvious and whether the team understands the problem space.

## Grafana-track implications

Martini Shot should explicitly show Grafana MCP as an active runtime control surface. The README and video should explain which Grafana MCP reads and writes are used, what the supervisor learns from them, and what evidence the judge can inspect in the repository or hosted project.

The demo should show the system running a real media workflow, not only a static dashboard. The strongest proof is a live or recorded sequence in which Martini Shot observes station telemetry through Grafana MCP, correlates a problem across logs, metrics, traces, annotations, or incidents, makes a governed decision, and records the result.

## Current deadline

The official Devpost page currently shows **September 9, 2026 at 9:00 PM UTC**, equivalent to **September 9, 2026 at 2:00 PM Pacific Time**.

## Technology and originality cautions

The official rules require a functional production-ready AI agent or multi-agent network powered by Gemini and Google Cloud Agent Builder, integrating a partner entity product or MCP server. The project documentation should avoid implying that an unverified or non-production path is live. It should distinguish code implementation from live-run evidence.

The repository should not claim that generated evidence or a planned integration is the same as a working runtime integration. The README should link directly to the relevant backend modules, Grafana configuration, setup instructions, and evidence files so judges can verify the claims.

## Documentation standard for this repository

The judge-facing README should lead with the user problem, the product behavior, the exact demo path, the Google Cloud and Grafana MCP architecture, a quick start, evidence links, limitations, and submission checklist. Internal handoffs, old plans, generated knowledge-graph files, and historical idea-lab notes should be labeled as internal or historical when they remain in the repository.

## References

[1]: https://agentic-cinema.devpost.com/ "Agentic Cinema official overview"
[2]: https://agentic-cinema.devpost.com/rules "Agentic Cinema official rules"
[3]: https://github.com/dvy1987/martini-shot "Martini Shot public repository"

The deadline, technology restrictions, and submission requirements in this file were checked against the official Devpost pages on 2026-09-08. The repository implementation claims must still be verified against the current code and evidence, as described in `README.md` and `docs/judge-guide.md`.
