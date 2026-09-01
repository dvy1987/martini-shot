# Project Knowledge Graph Index

Generated: 2026-09-01T08:55:23.642781+00:00
Mode: **application** | Nodes: 771 | Edges: 242

**Why this mode:** application label: 123 skills in .agents/skills plus source under (root) → indexing entire repository (skills + code + docs + memory).

**Scan layers:**
- skills (123 in .agents/skills)
- repo-wide source ((root))
- docs (AGENTS.md, README.md, docs/**/*.md)
- memory (docs/memory, handoffs)
- packages (package.json workspaces)
- config (.agents/ROUTING.md, tsconfig, pyproject, etc.)
- top-level directories

EXTRACTED: 170 | INFERRED: 72

## Hub nodes
- config.py (module)
- venture-exploration
- memory
- memory-capture
- universal-skill-creator
- models.py (module)
- improve-skills
- feature-spec

## Communities

**agent** (2): agent-launcher, agent-run-retro
**api** (2): api-and-interface-design, api-deprecation-and-migration
**app** (1): app-security-hardening
**browser** (1): browser-testing-with-devtools
**ci** (1): ci-cd-and-automation
**code** (2): code-review-crsp, code-simplification
**context** (1): context-engineering
**core** (70): adversarial-hat, agent-builder, agent-loom-sync, apply-paper-to-project, architectural-decision-log, assumption-mapping, brainstorming, business-modeling, codebase-understanding, compress-skill
  … +60 more
**create** (1): create-agent-prompt
**deep** (1): deep-thinking
**dependency** (5): debug-and-fix, dependency-mapping, dynamic-routing, safe-change, structured-planning
**deploy** (1): deploy-anywhere
**deprecate** (1): deprecate-skill
**eval** (3): eval-judge, eval-output, eval-rubric-design
**fault** (1): fault-localize
**first** (1): first-principles
**git** (1): git-workflow-and-versioning
**gsap** (7): design-direction, design-review, design-system, frontend-design, gsap-animation, motion-animation, svg-creation
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

- **config**: 417
- **directory**: 11
- **doc**: 37
- **handoff**: 12
- **memory**: 9
- **module**: 161
- **package**: 1
- **skill**: 123

See `GRAPH_REPORT.md` for surprising connections and suggested questions.

Full graph: `docs/knowledge-graph/graph.json`
Authoritative call edges: `docs/knowledge-graph/call-graph.json`
