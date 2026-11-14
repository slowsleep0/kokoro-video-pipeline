"""[fade: in_seconds, out_seconds] - text gently fades in and out.

Defaults: 0.6s in, 0.6s out.   Example:  Some line [fade: 0.3, 0.8]
"""
from .base import drawtext, get, gate

NAME = "fade"


def build(opts: dict, ctx: dict) -> list[str]:
    fin = get(opts, 0, 0.6)
    fout = get(opts, 1, 0.6)
    a = gate(ctx["ts"], ctx["te"], fin, fout)
    return [drawtext(ctx, ln, alpha=a) for ln in ctx["lines"]]
