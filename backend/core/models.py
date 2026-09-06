"""Central model ID registry (ADR 0002, G0-verified 2026-08-28/29).

The ONLY place model IDs may appear in backend code. Station modules import
from here; changes require an ADR + eval re-run (C-3.3).
"""

TEXT_MODEL = "gemini-3.7-flash"
THINKING_LEVEL = "HIGH"
THROUGH_THOUGHTS = True

# Video generation + conversational editing (Interactions API on the Vertex
# Agent Platform endpoint — gs:// media input, generation_config.video_config.task,
# no response_format for extend/edit; evidence docs/evidence/G0/omni_probe_2026-09-04.json,
# decision log 2026-09-04). Primary video path as of 2026-09-04.
OMNI_MODEL = "gemini-omni-1.1-flash-preview"

# Video generation — GA `-001` ID proven callable on Vertex at the G0 sweep
# (bg-swap + scene-extend renders, docs/evidence/G0/). FALLBACK video path
# since Omni on Vertex matched/beat it on the flicker gate (2026-09-04).
VEO_MODEL = "veo-3.1-fast-generate-001"

# Speech synthesis — Google Cloud Text-to-Speech, Chirp 3 HD voice family
# (per-language voice name: "<lang>-Chirp3-HD-Aoede"). E-2 dub station (A10).
TTS_VOICE_FAMILY = "Chirp3-HD-Aoede"
TTS_API_BASE = "https://texttospeech.googleapis.com/v1"
