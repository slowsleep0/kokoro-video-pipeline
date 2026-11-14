"""[bounce: start, drop_height] - text drops in and lands with a soft bounce.

start        seconds after the paragraph starts (default 0)
drop_height  fraction of the screen height it falls from (default 0.2)

Example:  Big reveal! [bounce: 0.5, 0.3]
"""
from .base import drawtext, get, gate

NAME = "bounce"


def build(opts: dict, ctx: dict) -> list[str]:
    start = get(opts, 0, 0.0)
    drop = get(opts, 1, 0.2)
    ts = ctx["ts"] + start                            # moment the drop begins

    r = f"min((t-{ts:.2f})/0.7,1)"                    # fall progress 0 -> 1
    fall = f"(1-{r})*(1-{r})"                          # fast fall, soft landing
    wobble = (f"abs(sin((t-{ts:.2f})*12.5))*0.06*"
              f"max(0,1-(t-{ts:.2f})/1.2)")           # small decaying bounce
    dy = f"{ctx['H'] * drop:.0f}*{fall}+{ctx['H']:.0f}*{wobble}"

    a = gate(ts, ctx["te"], 0.15, 0.35)               # invisible until the drop
    return [drawtext(ctx, ln, y=dy, alpha=a) for ln in ctx["lines"]]
