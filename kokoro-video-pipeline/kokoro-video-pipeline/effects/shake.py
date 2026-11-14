"""[shake: amplitude, wobbles_per_second, start, end] - nervous jitter.

amplitude  pixels of jitter (default 8)
speed      wobbles per second (default 8)
start,end  when the shaking happens, seconds into the paragraph
           (default: the whole paragraph)

Example:  ALARM!! [shake: 14, 12]
"""
from .base import drawtext, get, gate

NAME = "shake"


def build(opts: dict, ctx: dict) -> list[str]:
    amp = get(opts, 0, 8.0)
    freq = get(opts, 1, 8.0)
    s = get(opts, 2, 0.0)
    e = get(opts, 3, ctx["te"] - ctx["ts"])

    a = ctx["ts"] + s
    b = ctx["ts"] + min(max(e, s + 0.3), ctx["te"] - ctx["ts"])  # clamp to window
    vis = f"max(0,if(lt(t,{a:.2f}),0,if(lt(t,{b:.2f}),1,({b:.2f}-t)/0.25)))"

    dx = f"{amp:.1f}*sin((t-{a:.2f})*{freq * 6.283:.2f})"
    dy = f"{amp * 0.6:.1f}*cos((t-{a:.2f})*{freq * 6.283 * 1.3:.2f})"
    out = []
    for ln in ctx["lines"]:
        out.append(drawtext(ctx, ln, x=f"(w-text_w)/2+({dx})", y=dy, alpha=vis))
    return out
