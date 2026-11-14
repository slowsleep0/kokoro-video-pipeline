# Writing your own text animations (the effects system)

Every animation in this pipeline is a **plugin**: a small Python file in this
folder. The pipeline knows nothing about specific effects — it only knows how
to read your script tags, call the right plugin, and chain whatever ffmpeg
filters the plugin returns. That means **you** can invent new animations
without ever touching `build_video.py`.

## 1. How a tag becomes an animation

In `script.txt`, end any paragraph with one or more tags:

```
Breaking news tonight [scroll: 0, 3, 80]
A quiet line [fade]
Big moment [bounce: 0.5][shake: 4, 2, 1.5, 3]      <- chained, applied in order
```

The paragraph is **still spoken** by the AI voice — the tag adds a visual.
While that paragraph is being read (its "window"), the effect runs.

The parser turns `[scroll: 0, 3, 80]` into:

```python
REGISTRY["scroll"]({"pos": ["0", "3", "80"], "kw": {}}, ctx)
```

- options before any `=` are **positional** (`opts["pos"]` — a list of strings)
- `key=value` options land in `opts["kw"]` (e.g. `[scroll: speed=80]`)
- `ctx` (context) tells the effect everything about the moment:

| ctx key | meaning |
|---|---|
| `ts`, `te` | effect window: start/end seconds in the final video |
| `W`, `H`, `fps` | video size and frame rate |
| `font`, `fs`, `lh` | font path, font size, line height |
| `lines` | the wrapped text: `[{"file": txt_path, "y0": base_y}, ...]` |
| `color` | text color from config.yaml |
| `text` | the full paragraph text |

Your effect returns a list of `drawtext=...` filter strings. The pipeline
chains them onto the video — that's the whole magic.

## 2. What you can actually animate

Everything in a `drawtext` filter is an **ffmpeg expression evaluated every
frame**. These are your animation primitives:

| expression slot | animates |
|---|---|
| `x='...'` | horizontal position → scroll, slide, shake, wobble |
| `y='...'` | vertical position → rise, drop, bounce, wave |
| `alpha='...'` | opacity → fades, blinks, pulses |
| `extra=":box=1:boxcolor=..."` | any other drawtext option you pass through |

Inside those expressions you can use:

```
t          current time in seconds      <- 95% of effects only need this
w  h       video width / height
text_w     rendered width of this line (use in x=)
min(a,b) max(a,b) if(cond,a,b) lt(a,b) gt(a,b) between(t,a,b)
sin(a) cos(a) abs(a) pow(a,b) sqrt(a) random(0) PI
```

Write the math, get the animation. `x='w-(t-2)*80'` = "start at the right
edge 2s in, move left 80 px per second" — that's a marquee in one line.

## 3. Helpers you get for free (`effects/base.py`)

```python
from .base import drawtext, get, getraw, getopt, gate
```

- `drawtext(ctx, line, x=None, y=None, alpha=None, extra="")` — builds one
  standard filter (centered, soft shadow, your font). `y` is an **offset**
  added to the line's base position, so `y="15*sin(t*4)"` wobbles around the
  resting point.
- `gate(ts, te, fin, fout)` — visibility alpha: 0 outside the window, smooth
  ramps inside. Combine with your own motion:
  `alpha=f"min({my_pulse},{gate(ctx['ts'], ctx['te'])})"`.
- `get(opts, 0, default)` — positional option as float; `getraw(...)` for
  strings like `"left"`; `getopt(opts, "speed", 60)` for `speed=60` style.

Rules of the road:
1. **Clamp to the window** — use `gate(...)` or clamp end times to `ctx["te"]`,
   or your text will linger over the next paragraph.
2. **No `:` inside expressions** (it separates filter options); commas are fine.
3. Return one `drawtext` per line in `ctx["lines"]` (long paragraphs wrap).

## 4. Build one together: `[wave]` (vertical wave)

**Step 1** — create `effects/wave.py`:

```python
"""[wave: height_px, wobbles_per_second] - lines float on a sine wave."""
from .base import drawtext, get, gate

NAME = "wave"

def build(opts, ctx):
    height = get(opts, 0, 15.0)                  # [wave: 25]  -> 25 px
    freq = get(opts, 1, 2.0)
    a = gate(ctx["ts"], ctx["te"])               # visible only in the window
    out = []
    for k, ln in enumerate(ctx["lines"]):        # each line slightly out of phase
        dy = f"{height:.0f}*sin((t-{ctx['ts']:.2f})*{freq * 6.283:.2f}+{k})"
        out.append(drawtext(ctx, ln, y=dy, alpha=a))
    return out
```

**Step 2** — register it, two lines at the bottom of `effects/__init__.py`:

```python
from . import wave
register("wave", wave.build)
```

**Step 3** — use it: `Some floating words [wave: 25, 3]` and run
`python build_video.py --preview`.

That's the entire system: **syntax → registry → your function → ffmpeg
expressions.** Copy `fade.py` (the shortest one) as a starting template.

## 5. Built-in effects (your teaching examples — read them!)

| Tag | Options (positional) | What happens |
|---|---|---|
| `[fade]` | `in_s, out_s` (0.6, 0.6) | gentle fade in/out |
| `[slide]` | `dir, seconds` (`up`, 0.7) | slides in from up/down/left/right |
| `[scroll]` | `start, end, speed, dir` (0, full, 60, `left`) | marquee across the screen |
| `[bounce]` | `start, drop_height` (0, 0.2) | drops in, lands with a soft bounce |
| `[shake]` | `amp, wobbles_s, start, end` (8, 8, 0, full) | nervous jitter |

Ideas to try next: a `[blink]` (alpha = `if(lt(mod(t,0.6),0.3),1,0)`), a
`[crawl]` star-wars style upward drift (`y = base + (te-t)*20`), a
`[pulse]` scale-feel via shadow (`shadowx` + alpha breathing), or a random
jitter with `random(0)`. Debug like this: run `--preview`, and if ffmpeg
complains, the failing filter string is printed — fix the expression and
re-run. Keep each effect in its own file so you can toggle them by tag.
