"""El Jefesito — Neural Colombian & US English Voice TTS Engine (`server/tts_colombia.py`).

Provides natural, fast, human-sounding Colombian Spanish (`es-CO-SalomeNeural` /
`es-CO-GonzaloNeural`) and US English (`en-US-AriaNeural`) audio synthesis via
Microsoft Edge Neural TTS (`edge-tts`) with local disk caching for instant playback.

Default speed: `+22%` (fast, crisp executive pace).
"""
import asyncio
import hashlib
import os
import re
import tempfile

import edge_tts

CACHE_DIR = os.path.join(tempfile.gettempdir(), "jefesito_tts_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

VOICES = {
    "es": "es-CO-SalomeNeural",
    "es_male": "es-CO-GonzaloNeural",
    "en": "en-US-AriaNeural",
}

DEFAULT_RATE = "+22%"


def _clean_for_speech(text: str) -> str:
    """Strip markdown, brackets, and symbols so the neural voice reads smoothly."""
    t = re.sub(r"\[[A-Z]-\w+\]", "", text or "")
    t = re.sub(r"[*_`#~|•▸🧠🔔🔕✓✕🖨🔊⏹]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:900]


async def _gen(text: str, voice: str, rate: str, out_path: str):
    comm = edge_tts.Communicate(text, voice=voice, rate=rate)
    await comm.save(out_path)


def synthesize(text: str, lang: str = "es", voice: str | None = None, rate: str = DEFAULT_RATE) -> bytes:
    """Return MP3 bytes for `text` using Colombian Spanish (`es-CO-SalomeNeural`) or US English (`en-US-AriaNeural`)."""
    cleaned = _clean_for_speech(text)
    if not cleaned:
        return b""
    is_en = str(lang or "").strip().lower().startswith("en")
    v = voice or (VOICES["en"] if is_en else VOICES["es"])
    key = hashlib.sha256(f"{v}|{rate}|{cleaned}".encode("utf-8")).hexdigest()[:24]
    path = os.path.join(CACHE_DIR, f"{key}.mp3")
    if not os.path.isfile(path) or os.path.getsize(path) < 100:
        asyncio.run(_gen(cleaned, v, rate, path))
    with open(path, "rb") as f:
        return f.read()


if __name__ == "__main__":
    mp3 = synthesize("Hola Jasmel, soy El Jefesito con voz neural colombiana, rápida y natural.", lang="es")
    print(f"Synthesized {len(mp3)} bytes MP3 (es-CO-SalomeNeural @ {DEFAULT_RATE})")
