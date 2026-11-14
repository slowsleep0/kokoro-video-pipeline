"""STUB - swap-in slot for Resemble AI's Chatterbox (more expressive, can clone
a voice from ~10 seconds of audio).

It is NOT installed by default because it needs far more compute than Kokoro
(painful on a 2-core Codespace, happy on a GPU).

To activate it later on a GPU machine (or a beefier CPU):
  pip install chatterbox-tts
then fill in the two methods below and register 'chatterbox' in
tts_backends/__init__.py. Switch config.yaml:  tts.backend: chatterbox
"""
from .base import TTSEngine, Segment


class ChatterboxEngine(TTSEngine):
    name = "chatterbox"

    def __init__(self, voice_sample: str | None = None, exaggeration: float = 0.5):
        raise NotImplementedError(
            "Install chatterbox-tts and complete this backend first. "
            "The Kokoro backend works out of the box."
        )

    def synthesize(self, text: str, out_wav: str) -> list[Segment]:
        raise NotImplementedError
