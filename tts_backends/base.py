"""Common interface every TTS engine implements.

To add a future engine (Chatterbox, F5-TTS, whatever wins next year):
  1. create      tts_backends/<name>_backend.py
  2. implement   synthesize()  -> returns a list of timed Segments
  3. register it in tts_backends/__init__.py  (3 lines)
  4. switch      tts.backend  in config.yaml

Nothing else in the pipeline ever changes.
"""
from dataclasses import dataclass


@dataclass
class Segment:
    text: str
    start: float  # seconds from the beginning of the audio
    end: float    # seconds


class TTSEngine:
    name = "base"

    def synthesize(self, text: str, out_wav: str) -> list[Segment]:
        """Render `text` to `out_wav` (any sample rate) and return timed segments."""
        raise NotImplementedError
