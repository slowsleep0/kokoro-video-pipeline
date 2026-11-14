"""Factory that builds the TTS engine chosen in config.yaml.

Add new engines here - this is the ONLY registration point.
"""
from .base import TTSEngine, Segment


def load_engine(cfg: dict) -> TTSEngine:
    name = cfg["backend"]
    if name == "kokoro":
        from .kokoro_backend import KokoroEngine

        return KokoroEngine(
            lang_code=cfg.get("lang_code", "a"),
            voice=cfg.get("voice", "af_heart"),
            speed=float(cfg.get("speed", 1.0)),
        )
    raise ValueError(
        f"Unknown TTS backend '{name}'. Available: kokoro. "
        "See tts_backends/base.py for how to plug in another engine."
    )
