# Knowledge Graph Report

Generated: 2026-09-01T08:55:23.642781+00:00
Mode: application | Nodes: 771 | Edges: 242

**Why this mode:** application label: 123 skills in .agents/skills plus source under (root) → indexing entire repository (skills + code + docs + memory).

## God nodes (skills + modules)
- config.py (module)
- venture-exploration
- memory
- memory-capture
- universal-skill-creator
- models.py (module)
- improve-skills
- feature-spec
- problem-to-plan
- memory-startup

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
- What depends on config.py (module), and what does config.py (module) invoke?
- What depends on venture-exploration, and what does venture-exploration invoke?
- What depends on memory, and what does memory invoke?

## Provenance
- Authoritative invokes: 0
- EXTRACTED: 170 | INFERRED: 72

Query: `python3 .agents/skills/knowledge-graph/scripts/query_graph.py path <A> <B>`
