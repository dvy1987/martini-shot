# Knowledge Graph Report

Generated: 2026-09-07T15:14:23.030498+00:00
Mode: application | Nodes: 1030 | Edges: 507

**Why this mode:** application label: 123 skills in .agents/skills plus source under (root) → indexing entire repository (skills + code + docs + memory).

## God nodes (skills + modules)
- finish.py (module)
- venture-exploration
- memory
- models.py (module)
- memory-capture
- universal-skill-creator
- improve-skills
- test_gcs_keys.py (module)
- feature-spec
- app.py (module)

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
- What depends on finish.py (module), and what does finish.py (module) invoke?
- What depends on venture-exploration, and what does venture-exploration invoke?
- What depends on memory, and what does memory invoke?

## Provenance
- Authoritative invokes: 0
- EXTRACTED: 346 | INFERRED: 161

Query: `python3 .agents/skills/knowledge-graph/scripts/query_graph.py path <A> <B>`
