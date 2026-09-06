"""One-off probe: does Chirp 3 HD honor SSML prosody vs audioConfig
.speakingRate? Deletes itself conceptually after the ADR note."""

import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import get_settings
from backend.core.generative import tts_synthesize


def dur(b: bytes) -> float:
    w = wave.open(io.BytesIO(b))
    return w.getnframes() / w.getframerate()


s = get_settings()
line = "Bienvenido a Martini Shot, la cabina de postproduccion."
base = tts_synthesize(
    s,
    ssml=f"<speak>{line}</speak>",
    language_code="es-ES",
    voice_name="es-ES-Chirp3-HD-Aoede",
)
pros = tts_synthesize(
    s,
    ssml=f'<speak><prosody rate="80%">{line}</prosody></speak>',
    language_code="es-ES",
    voice_name="es-ES-Chirp3-HD-Aoede",
)
rate = tts_synthesize(
    s,
    ssml=f"<speak>{line}</speak>",
    language_code="es-ES",
    voice_name="es-ES-Chirp3-HD-Aoede",
    speaking_rate=0.8,
)
print("base:", round(dur(base["audio_bytes"]), 3))
print("prosody 80%:", round(dur(pros["audio_bytes"]), 3))
print("speakingRate 0.8:", round(dur(rate["audio_bytes"]), 3))
