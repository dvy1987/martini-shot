"""Central model ID registry (ADR 0002, G0-verified 2026-08-28/29).

The ONLY place model IDs may appear in backend code. Station modules import
from here; changes require an ADR + eval re-run (C-3.3).
"""

TEXT_MODEL = "gemini-3.7-flash"
THINKING_LEVEL = "HIGH"
THROUGH_THOUGHTS = True

# Conversational editing / extension ops (Interactions API; Omni research is
# parked until after Stage 1 per owner ruling 2026-08-30).
OMNI_MODEL = "gemini-omni-1.1-flash-preview"

# Video generation — GA `-001` ID proven callable on Vertex at the G0 sweep
# (bg-swap + scene-extend renders, docs/evidence/G0/).
VEO_MODEL = "veo-3.1-fast-generate-001"
