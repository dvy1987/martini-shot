# Knowledge Graph Report

Generated: 2026-09-07T06:03:46.692854+00:00
Mode: application | Nodes: 496 | Edges: 444

**Why this mode:** application label: 123 skills in .agents/skills plus source under (root), backend, docs, frontend, scripts, tests → indexing entire repository (skills + code + docs + memory).

## God nodes (skills + modules)
- __init__.py (module)
- venture-exploration
- memory
- models.py (module)
- memory-capture
- universal-skill-creator
- improve-skills
- app.py (module)
- feature-spec
- test_smoke.py (module)

## Surprising cross-community connections
- skill-finder → universal-skill-creator (invokes: skill ↔ universal)
- library-skill → generate-changelog (invokes: library ↔ generate)
- library-skill → codebase-understanding (invokes: library ↔ codebase)
- library-skill → prd-writing (invokes: library ↔ prd)
- improve-skills → validate-skills (invokes: improve ↔ validate)
- improve-skills → prune-skill (invokes: improve ↔ prune)
- improve-skills → research-skill (invokes: improve ↔ research)
- improve-skills → skill-deconflict (invokes: improve ↔ skill)

## Suggested questions
- How does skill-finder (skill) connect to universal-skill-creator (universal)?
- How does library-skill (library) connect to generate-changelog (generate)?
- How does library-skill (library) connect to codebase-understanding (codebase)?
- What depends on __init__.py (module), and what does __init__.py (module) invoke?
- What depends on venture-exploration, and what does venture-exploration invoke?
- What depends on memory, and what does memory invoke?

## Provenance
- Authoritative invokes: 0
- EXTRACTED: 292 | INFERRED: 152

Query: `python3 .agents/skills/knowledge-graph/scripts/query_graph.py path <A> <B>`
