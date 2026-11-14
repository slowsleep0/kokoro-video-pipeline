"""Effect registry - THE one place that connects script.txt tags to Python.

script.txt syntax (tags at the END of a paragraph, the text is still spoken):

    Breaking news [scroll: 0, 3, 80]
    A quiet line [fade]
    Big moment [bounce: 0.5][shake: 4, 2, 1.5, 3]     <- multiple tags chain

ADD YOUR OWN EFFECT - 3 steps:
  1. copy effects/fade.py to effects/mine.py, rename NAME="mine",
     change the math (it is just x / y / alpha expressions per frame)
  2. register it here - two lines at the bottom of this file:
         from . import mine
         register("mine", mine.build)
  3. use [mine: ...] in script.txt

Full guide + ffmpeg expression cheatsheet: effects/README.md
"""
from .base import parse_opts  # noqa: F401  (re-exported for build_video)

from . import fade, slide, scroll, bounce, shake

REGISTRY = {
    fade.NAME: fade.build,
    slide.NAME: slide.build,
    scroll.NAME: scroll.build,
    bounce.NAME: bounce.build,
    shake.NAME: shake.build,
}


def register(name: str, fn) -> None:
    """Add a custom effect to the registry (call from this file)."""
    REGISTRY[name] = fn
