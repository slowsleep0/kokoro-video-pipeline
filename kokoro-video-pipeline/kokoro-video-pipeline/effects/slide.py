"""[slide: direction, seconds] - text slides in and settles.

direction: up | down | left | right   (default up)
seconds:   how long the slide takes   (default 0.7)

Example:  A quiet thought [slide: left, 1.0]
"""
from .base import drawtext, get, getraw, getopt, gate

NAME = "slide"


def build(opts: dict, ctx: dict) -> list[str]:
    d = str(getopt(opts, "dir", getraw(opts, 0, "up"))).lower()
    dur = max(0.1, get(opts, 1, 0.7))
    ts = ctx["ts"]
    r = f"min((t-{ts:.2f})/{dur:.2f},1)"           # progress 0 -> 1
    ease = f"(1-{r})*(1-{r})"                       # fast start, soft landing
    a = gate(ts, ctx["te"], min(dur, 0.4), 0.35)

    if d in ("up", "down"):
        dy = f"{ctx['H'] * 0.12:.0f}*{ease}" if d == "up" else f"-{ctx['H'] * 0.12:.0f}*{ease}"
        return [drawtext(ctx, ln, y=dy, alpha=a) for ln in ctx["lines"]]
    dx = f"{ctx['W'] * 0.35:.0f}*{ease}" if d == "left" else f"-{ctx['W'] * 0.35:.0f}*{ease}"
    return [drawtext(ctx, ln, x=f"(w-text_w)/2+({dx})", alpha=a) for ln in ctx["lines"]]
