"""Focused probe: fr-03 mutated audio — is the cut audible?"""

import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import get_settings
from backend.core.generative import tts_synthesize
from backend.stations.dubbing.qc import (
    measure_timing,
    truncate_speech_wav,
)

row = {
    "script_target": "Prise trois, épisode un.",
    "lang": "fr-FR",
    "voice": "fr-FR-Chirp3-HD-Aoede",
    "original_ref": "fixtures/dubbing/seg-03-source.wav",
    "truncate_ms": 900,
}
ROOT = Path(__file__).resolve().parents[1]
s = get_settings()
original = (ROOT / row["original_ref"]).read_bytes()
render = tts_synthesize(
    s,
    ssml=f"<speak>{row['script_target']}</speak>",
    language_code=row["lang"],
    voice_name=row["voice"],
)
dub = bytes(render["audio_bytes"])
from backend.stations.dubbing.run import time_fit_dub

fit = time_fit_dub(
    s,
    ssml=f"<speak>{row['script_target']}</speak>",
    language=row["lang"],
    original_wav=original,
    first_wav=dub,
)
mutated = truncate_speech_wav(fit["wav"], row["truncate_ms"])
out = ROOT / "fixtures" / "_probe_fr03.wav"
out.write_bytes(mutated)
m = measure_timing(original, mutated, tolerance_ms=45)
print("delta:", m["duration_delta_ms"], "verdict:", m["verdict"])
w = wave.open(io.BytesIO(mutated))
print("mutated duration ms:", w.getnframes() / w.getframerate() * 1000)
# tail energy profile: last 10 x 50ms windows RMS
import struct as _struct

raw = w.readframes(w.getnframes())
step = int(w.getframerate() * 0.05) * 2
tail = []
for i in range(10):
    chunk = raw[max(0, len(raw) - (i + 1) * step) : len(raw) - i * step]
    n = len(chunk) // 2
    vals = _struct.unpack(f"<{n}h", chunk) if n else (0,)
    tail.append(int((sum(v * v for v in vals) / n) ** 0.5))
print("tail RMS (oldest first):", tail)
print("saved:", out)
