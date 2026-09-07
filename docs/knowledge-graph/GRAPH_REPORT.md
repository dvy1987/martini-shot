# Knowledge Graph Report

Generated: 2026-09-07T06:02:36.213158+00:00
Mode: application | Nodes: 492 | Edges: 443

**Why this mode:** application label: 123 skills in .agents/skills plus source under (root), backend, docs, frontend, scripts, tests → indexing entire repository (skills + code + docs + memory).

## God nodes (skills + modules)
- firestore.py (module)
- venture-exploration
- memory
- models.py (module)
- memory-capture
- universal-skill-creator
- test_shot_locking.py (module)
- improve-skills
- app.py (module)
- feature-spec

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
- What depends on firestore.py (module), and what does firestore.py (module) invoke?
- What depends on venture-exploration, and what does venture-exploration invoke?
- What depends on memory, and what does memory invoke?

## Provenance
- Authoritative invokes: 0
- EXTRACTED: 291 | INFERRED: 152

Query: `python3 .agents/skills/knowledge-graph/scripts/query_graph.py path <A> <B>`
