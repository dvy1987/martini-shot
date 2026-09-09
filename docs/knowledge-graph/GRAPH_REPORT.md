# Knowledge Graph Report

Generated: 2026-09-09T16:55:24.508965+00:00
Mode: application | Nodes: 1141 | Edges: 605

**Why this mode:** application label: 123 skills in .agents/skills plus source under (root) → indexing entire repository (skills + code + docs + memory).

## God nodes (skills + modules)
- __init__.py (module)
- venture-exploration
- test_supervisor_mcp.py (module)
- memory
- app.py (module)
- models.py (module)
- memory-capture
- universal-skill-creator
- improve-skills
- feature-spec

## Surprising cross-community connections
- agent-builder → harness-generation (invokes: agent ↔ harness)
- agent-builder → setup-evaluation (invokes: agent ↔ setup)
- agent-loom-sync → validate-skills (invokes: agent ↔ validate)
- apply-paper-to-project → learn-from-paper (invokes: apply ↔ learn)
- architectural-decision-log → memory-decision (invokes: architectural ↔ memory)
- brainstorming → feature-spec (invokes: core ↔ feature)
- brainstorming → venture-exploration (invokes: core ↔ venture)
- business-modeling → venture-exploration (invokes: business ↔ venture)

## Suggested questions
- How does agent-builder (agent) connect to harness-generation (harness)?
- How does agent-builder (agent) connect to setup-evaluation (setup)?
- How does agent-loom-sync (agent) connect to validate-skills (validate)?
- What depends on __init__.py (module), and what does __init__.py (module) invoke?
- What depends on venture-exploration, and what does venture-exploration invoke?
- What depends on test_supervisor_mcp.py (module), and what does test_supervisor_mcp.py (module) invoke?

## Provenance
- Authoritative invokes: 0
- EXTRACTED: 397 | INFERRED: 208

Query: `python3 .agents/skills/knowledge-graph/scripts/query_graph.py path <A> <B>`
