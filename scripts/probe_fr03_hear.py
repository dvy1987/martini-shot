"""What does the model actually hear in the fr-03 mutated dub?"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import get_settings
from backend.core.generative import tts_synthesize
from backend.stations.dubbing.qc import truncate_speech_wav
from backend.stations.dubbing.run import time_fit_dub
from backend.supervisor.otel_ai import run_agent_call

s = get_settings()
original = (
    Path(__file__).resolve().parents[1] / "fixtures/dubbing/seg-03-source.wav"
).read_bytes()
render = tts_synthesize(
    s,
    ssml="<speak>Prise trois, épisode un.</speak>",
    language_code="fr-FR",
    voice_name="fr-FR-Chirp3-HD-Aoede",
)
fit = time_fit_dub(
    s,
    ssml="<speak>Prise trois, épisode un.</speak>",
    language="fr-FR",
    original_wav=original,
    first_wav=bytes(render["audio_bytes"]),
)
mutated = truncate_speech_wav(fit["wav"], 900)
resp = run_agent_call(
    s,
    "Transcribe EXACTLY what you hear in this audio, word for word. If a word "
    "is cut off mid-pronunciation, say so explicitly. Answer in plain text.",
    span_name="probe.audio_transcribe",
    persona="dub_qc_probe",
    audio=(mutated, "audio/wav"),
)
print("MODEL HEARD:", resp["text"][:600])
