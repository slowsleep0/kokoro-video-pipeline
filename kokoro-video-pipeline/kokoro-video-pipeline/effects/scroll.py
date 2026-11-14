"""[scroll: start, end, speed, direction] - marquee / scrolling text.

start     seconds after the paragraph starts when scrolling begins (default 0)
end       seconds after the paragraph start when scrolling stops
          (default: until the paragraph ends)
speed     pixels per second (default 60)
direction left | right (default left - text enters from the right edge)

Example:  Breaking news [scroll: 0, 3, 80]
"""
from .base import drawtext, get, getraw

NAME = "scroll"


def build(opts: dict, ctx: dict) -> list[str]:
    start = get(opts, 0, 0.0)
    end = get(opts, 1, ctx["te"] - ctx["ts"])       # default: whole paragraph
    speed = max(1.0, get(opts, 2, 60.0))
    d = str(getraw(opts, 3, "left")).lower()

    a = ctx["ts"] + start                            # absolute start of scrolling
    b = ctx["ts"] + min(max(end, start + 0.3), ctx["te"] - ctx["ts"])  # clamp to window
    vis = f"if(lt(t,{a:.2f}),0,if(lt(t,{b:.2f}),1,0))"

    if d == "right":
        x = f"(-text_w)+(t-{a:.2f})*{speed:.1f}"     # crawl in from the left
    else:
        x = f"{ctx['W']}-(t-{a:.2f})*{speed:.1f}"    # enter from the right edge
    return [drawtext(ctx, ln, x=x, alpha=vis) for ln in ctx["lines"]]
