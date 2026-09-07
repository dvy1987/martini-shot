# Knowledge Graph Report

Generated: 2026-09-07T05:58:43.901320+00:00
Mode: application | Nodes: 489 | Edges: 442

**Why this mode:** application label: 123 skills in .agents/skills plus source under (root), backend, docs, frontend, scripts, tests → indexing entire repository (skills + code + docs + memory).

## God nodes (skills + modules)
- check_thresholds.py (module)
- venture-exploration
- memory
- models.py (module)
- memory-capture
- universal-skill-creator
- improve-skills
- test_extend_qc.py (module)
- feature-spec
- app.py (module)

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
- What depends on check_thresholds.py (module), and what does check_thresholds.py (module) invoke?
- What depends on venture-exploration, and what does venture-exploration invoke?
- What depends on memory, and what does memory invoke?

## Provenance
- Authoritative invokes: 0
- EXTRACTED: 289 | INFERRED: 153

Query: `python3 .agents/skills/knowledge-graph/scripts/query_graph.py path <A> <B>`
