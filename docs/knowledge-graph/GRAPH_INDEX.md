# Project Knowledge Graph Index

Generated: 2026-09-07T06:03:46.692854+00:00
Mode: **application** | Nodes: 496 | Edges: 444

**Why this mode:** application label: 123 skills in .agents/skills plus source under (root), backend, docs, frontend, scripts, tests → indexing entire repository (skills + code + docs + memory).

**Scan layers:**
- skills (123 in .agents/skills)
- repo-wide source ((root), backend, docs, frontend, scripts, tests)
- docs (AGENTS.md, README.md, docs/**/*.md)
- memory (docs/memory, handoffs)
- packages (package.json workspaces)
- config (.agents/ROUTING.md, tsconfig, pyproject, etc.)
- top-level directories

EXTRACTED: 292 | INFERRED: 152

## Hub nodes
- __init__.py (module)
- venture-exploration
- memory
- models.py (module)
- memory-capture
- universal-skill-creator
- improve-skills
- app.py (module)

## Communities

**agent** (2): agent-launcher, agent-run-retro
**api** (2): api-and-interface-design, api-deprecation-and-migration
**app** (1): app-security-hardening
**browser** (1): browser-testing-with-devtools
**ci** (1): ci-cd-and-automation
**code** (2): code-review-crsp, code-simplification
**context** (1): context-engineering
**core** (4): inversion, ooda, quickstart, socratic
**create** (1): create-agent-prompt
**deep** (1): deep-thinking
**dependency** (5): debug-and-fix, dependency-mapping, dynamic-routing, safe-change, structured-planning
**deploy** (1): deploy-anywhere
**deprecate** (1): deprecate-skill
**design** (7): design-direction, design-review, design-system, frontend-design, gsap-animation, motion-animation, svg-creation
**eval** (3): eval-judge, eval-output, eval-rubric-design
**fault** (1): fault-localize
**first** (1): first-principles
**generate** (66): adversarial-hat, agent-builder, agent-loom-sync, apply-paper-to-project, architectural-decision-log, assumption-mapping, brainstorming, business-modeling, codebase-understanding, compress-skill
  … +56 more
**git** (1): git-workflow-and-versioning
**incremental** (1): incremental-implementation
**issue** (1): issue-sync
**knowledge** (1): knowledge-graph
**performance** (1): performance-optimization
**pr** (1): pr-authoring
**pre** (1): pre-mortem
**run** (1): run-trace
**runtime** (3): agent-observability, agent-system-architecture, runtime-learning-loop
**second** (1): second-order
**secure** (4): secure-skill, secure-skill-content-sanitization, secure-skill-repo-ingestion, secure-skill-runtime
**shipping** (1): shipping-and-launch
**source** (1): source-driven-development
**spec** (1): spec-crosscheck
**technical** (1): technical-debt-audit
**test** (1): test-driven-development
**tool** (1): tool-finder

## Node types

- **config**: 3
- **directory**: 10
- **doc**: 58
- **handoff**: 19
- **memory**: 9
- **module**: 273
- **package**: 1
- **skill**: 123

See `GRAPH_REPORT.md` for surprising connections and suggested questions.

Full graph: `docs/knowledge-graph/graph.json`
Authoritative call edges: `docs/knowledge-graph/call-graph.json`
