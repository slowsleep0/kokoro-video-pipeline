"""The animation-effect contract - read this before writing your own effect.

An "effect" is a small Python file in this folder (next to fade.py, scroll.py,
...) that exposes two things:

    NAME = "myeffect"              # what the user types inside [ ] in script.txt

    def build(opts, ctx):          # called once per tagged paragraph
        return ["drawtext=..."]    # ffmpeg drawtext strings, chained in order

    opts = {"pos": ["0", "3", "80"], "kw": {"speed": "80"}}
        -> from script.txt:  [myeffect: 0, 3, speed=80]

    ctx = {"ts": start_seconds, "te": end_seconds,   # when the text is on screen
           "W", "H", "fps", "font", "fs", "lh",      # geometry & typography
           "lines": [{"file": txt_path, "y0": base_y}, ...],   # wrapped lines
           "color": "white", "text": "...", "work": Path, "idx": n}

Everything you animate is an ffmpeg *expression* evaluated on every frame.
Useful variables and functions inside x=, y=, alpha=:

    t          current time in seconds (the star of the show)
    w  h       video width / height          text_w  text_h  this line's size
    min(a,b) max(a,b) if(c,a,b) lt(a,b) gt(a,b) between(t,a,b)
    sin(a) cos(a) abs(a) pow(a,b) random(0) PI

Helpers in this file (import them - do not reinvent):

    drawtext(ctx, line, x=None, y=None, alpha=None, extra="")
        builds one standard drawtext filter; y is an OFFSET added to the
        line's base position; x defaults to centered.
    gate(ts, te, fin=0.35, fout=0.35)
        returns an alpha expression: invisible outside [ts,te], ramps in/out.
        Compose it: alpha=f"min({my_anim_alpha},{gate(ctx['ts'], ctx['te'])})"
    get(opts, i, default)     positional option i as a float
    getraw(opts, i, default)  positional option i as a string (e.g. "left")
    getopt(opts, name, default)  named option speed=80

Rules of the road:
  * keep expressions free of ':' (it separates filter options); commas are OK.
  * clamp your effect to the window: use gate(...) or clamp end times to
    ctx["te"], or your text will linger over the next paragraph.
  * return one drawtext per line in ctx["lines"] (wrapped long text).
"""
from __future__ import annotations


def parse_opts(raw: str | None) -> dict:
    """'0, 2, speed=40' -> {'pos': ['0', '2'], 'kw': {'speed': '40'}}"""
    pos, kw = [], {}
    if raw:
        for tok in raw.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if "=" in tok:
                k, v = tok.split("=", 1)
                kw[k.strip()] = v.strip()
            else:
                pos.append(tok)
    return {"pos": pos, "kw": kw}


def get(opts: dict, i: int, default):
    """Positional option i converted to float, else default."""
    try:
        return float(opts["pos"][i])
    except (IndexError, ValueError):
        return default


def getraw(opts: dict, i: int, default):
    """Positional option i as a raw string (directions like 'left')."""
    return opts["pos"][i] if len(opts["pos"]) > i else default


def getopt(opts: dict, name: str, default):
    """Named option: [fx: speed=80] -> 80."""
    return opts["kw"].get(name, default)


def gate(ts: float, te: float, fin: float = 0.35, fout: float = 0.35) -> str:
    """Visibility alpha: 0 outside [ts,te], smooth ramps inside. Triangle form:
    ramps meet at a peak of 1 even when the window is shorter than the ramps."""
    fin, fout = max(fin, 1e-3), max(fout, 1e-3)
    # NOTE: ffmpeg's min()/max() take exactly TWO arguments - nest them.
    return f"max(0,min(min((t-{ts:.2f})/{fin:.2f},({te:.2f}-t)/{fout:.2f}),1))"


def drawtext(ctx: dict, line: dict, x: str | None = None, y: str | None = None,
             alpha: str | None = None, extra: str = "") -> str:
    """One standard text filter. `y` is an OFFSET expression added to the
    line's base position; `x` defaults to horizontally centered."""
    x = x or "(w-text_w)/2"
    y = f"{line['y0']}+({y})" if y else f"{line['y0']}"
    alpha = alpha or "1"
    return (f"drawtext=fontfile={ctx['font']}:textfile={line['file']}:"
            f"fontsize={ctx['fs']}:fontcolor={ctx['color']}:"
            f"x='{x}':y='{y}':alpha='{alpha}'"
            f":shadowcolor=black@0.6:shadowx=3:shadowy=3{extra}")
