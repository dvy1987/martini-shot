# Rubric: leftover-stack ranking + spend pricing (walk-away)

## Task
After mix and pickups, leftover station agents suggest work. Spend names a
micro cost for each leftover job. The orchestrator ranks the priced bag:
impact, dependencies (what must wait on what), envelope, and spine notes
from ingest/handoff. Do not invent a line when ingest never happened.

## Who scores
Live `gemini-3.7-flash` on the product path (`run_rank_agent`,
`decide_spend_pricing`). Labels in JSONL. No second judge model.

## Dimensions
- Task completion: order / drop / prices match the labeled case
- Dependencies: same-shot Omni edits serialize; independent clips do not
- Spine: restored bag is truth; unrepairable shot does not get invented dialogue
- Format: JSON plan / prices only (hard gate)

## Fail
Invented station; ignore orchestrator_spine; Python sort counted as a pass.
