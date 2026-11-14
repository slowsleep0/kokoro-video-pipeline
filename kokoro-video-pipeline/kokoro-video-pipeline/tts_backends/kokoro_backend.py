"""Kokoro-82M engine: tiny (~350 MB), CPU-friendly, Apache-2.0 licensed.

Runs faster than real time on most CPUs, which makes it the best free choice
for a 2-core GitHub Codespace today.
"""
import numpy as np
import soundfile as sf

from .base import TTSEngine, Segment


class KokoroEngine(TTSEngine):
    name = "kokoro"
    SAMPLE_RATE = 24000

    def __init__(self, lang_code: str = "a", voice: str = "af_heart", speed: float = 1.0):
        from kokoro import KPipeline  # imported here so the rest of the app stays light

        self.voice, self.speed = voice, speed
        self.pipeline = KPipeline(lang_code=lang_code)

    def synthesize(self, text: str, out_wav: str) -> list[Segment]:
        # Kokoro splits on blank lines / newlines, so every paragraph of
        # script.txt becomes one timed segment (handy for subtitles).
        chunks, segments, t0 = [], [], 0.0
        for gs, _ps, audio in self.pipeline(text, voice=self.voice, speed=self.speed):
            audio = np.asarray(audio, dtype=np.float32)
            chunks.append(audio)
            dur = len(audio) / self.SAMPLE_RATE
            segments.append(Segment(text=str(gs), start=t0, end=t0 + dur))
            t0 += dur
        if not chunks:
            raise RuntimeError("TTS produced no audio - is the script empty?")
        sf.write(out_wav, np.concatenate(chunks), self.SAMPLE_RATE)
        return segments
