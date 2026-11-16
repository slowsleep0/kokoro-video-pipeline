# VFX GUIDE — level 2: understanding and inventing your own animations

Read `effects/README.md` first (the intro: contract, ctx, registration).
This guide goes deeper: the math patterns every animation is made of, how
to go beyond text, and how to debug when ffmpeg rejects your masterpiece.

The one idea everything here rests on:

> Your `build()` runs **once**, before rendering. It returns strings.
> ffmpeg then evaluates those expressions **on every frame**, with `t`
> (current time in seconds) as the moving part. You are not writing a
> program that animates — you are writing a **formula that describes
> position/opacity at any time t**.

---

## 1. The six patterns behind almost every effect

Every shipped effect in this folder is one of these six, plus glue:

| # | Pattern | Formula sketch | Used by |
|---|---|---|---|
| 1 | **Progress** | `r = min((t-ts)/dur, 1)` — 0→1 over `dur`, then stops | slide, bounce |
| 2 | **Easing** | multiply motion by `(1-r)*(1-r)` — fast start, soft landing | slide, bounce |
| 3 | **Wave** | `A*sin((t-ts)*2*PI*f)` — endless oscillation of size A, freq f | wave, shake |
| 4 | **Decay** | `max(0, 1-(t-ts)/T)` — dies out over T seconds | bounce wobble |
| 5 | **Visibility** | `gate(ts, te)` — smooth 0→1→0 window; combine: `min(mine, gate(...))` | every effect |
| 6 | **Step / boolean** | `if(lt(t,x), 0, 1)` or `enable='between(t,a,b)'` — on/off events | type, flash |

Compose them: bounce = progress (1) × easing (2) for the fall, + wave (3)
× decay (4) for the landing wobble, gated by (5).

**Copy-paste cookbook** (put `ts = ctx["ts"]` first):

```
r    = min((t-{ts:.2f})/0.7,1)              progress 0→1 over 0.7s
ease = (1-r)*(1-r)                          ease-out quadratic
bob  = 20*sin((t-{ts:.2f})*6.283*1.5)       20px bob, 1.5 Hz
ping = abs(sin((t-{ts:.2f})*3.14))          0→1→0 triangle, 0.5s period
dip  = max(0,1-(t-{ts:.2f})/1.2)            1→0 over 1.2s, then 0 forever
on   = if(lt(t,{te:.2f}),1,0)               hard on/off at a moment
```

## 2. Where the formula goes — the three animation slots

`drawtext(ctx, ln, x=..., y=..., alpha=...)` (from `effects/base.py`)
builds a full filter; your formulas land in:

- **x / y** — position. `y` is an OFFSET added to the line's resting spot
  (`ln["y0"]`), so a wobble never fights the layout. Use `text_w` in x for
  edge-aware motion: `x = "{W}-((t-{ts:.2f})*80)"` = enter from the right.
- **alpha** — opacity, 0..1. Anything >1 is treated as 1; negative shows
  nothing. `min(your_motion, gate(ts, te))` is the standard clamp.
- **extra** — raw append for any drawtext option you don't get from the
  helper: box, border (`:borderw=4:bordercolor=black`), per-effect
  fontcolor override, etc. See `box.py` for the cleanest example.

### Hard limits (know them before you fight them)

- **fontsize cannot animate.** drawtext takes fontsize once, no
  expressions. A "zoom" on text = fake it with shadow/alpha, or do it in
  the title-card layer, or pre-render frames — not worth it here.
- **No per-character animation.** drawtext renders a whole line; there is
  no per-glyph t. `[type]` therefore reveals per LINE (see type.py).
- **One filter in, one filter out per returned string.** The chain glue is
  `[cur]FRAG[fxN]` — a fragment cannot declare its own second input, so
  no `overlay`/`blend` with external images inside an effect.
- **No `:` inside x/y/alpha expressions** (option separator). Commas fine.
  ffmpeg's `min`/`max` take exactly TWO arguments — nest them.

## 3. Beyond text — fragments can be any 1-in/1-out filter

The pipeline doesn't check that your string starts with `drawtext`. It just
appends it to the chain. Any single-input/single-output filter works, which
opens real VFX on the whole frame:

| filter | what it gives you | shipped example |
|---|---|---|
| `eq=brightness=V:enable='between(t,a,b)'` | whole-frame flash / glow / darken (V is static per filter, so decay = several steps) | `flash.py` |
| `drawbox=x:y:w:h:color=C@A:t=fill:enable=...` | bars, wipes, letterbox, lower-third background (x/y/w/h accept expressions!) | — try one |
| `vignette=enable='...'` | cinematic dark edges during a moment | — |
| `hue=s=0:enable='...'` | desaturate a section for mood | — |
| `noise=alls=N:allf=t+u:enable='...'` | grainy flashback texture | — |
| `gblur=sigma=N:enable='...'` | defocus a moment (heavy — preview first) | — |

Idea sketch — "letterbox bar wipes in then out":

```python
h_in = f"{ctx['H']*0.12:.0f}*min((t-{ts:.2f})/0.5,1)"
return [f"drawbox=x=0:y=0:w=iw:h=({h_in}):color=black:t=fill"]
```

Bars grow from the top for 0.5s and stay — pair with the paragraph ending
and a title card next, and you have a scene transition.

## 4. Debugging — the loop that never lies

1. **Test fast:** `python build_video.py --preview` (~1-2 min). Errors come
   in two kinds:
   - Python `Traceback` at parse time → your `build()` crashed; read the
     last line, it names your file and line number.
   - ffmpeg error mid-render → an expression is invalid; the log prints the
     failing filter string. 90% of the time: a `:` inside an expression, or
     a 3-argument `min/max`, or an unbalanced quote/paren.
2. **"Unknown effect '[name]'"** → you forgot the two registration lines in
   `effects/__init__.py` (or the file has a syntax error so the import
   failed — run `python -c "from effects import <name>"` to see it).
3. **Text lingers over the next paragraph** → you didn't clamp. Wrap your
   alpha in `min(your_alpha, gate(ctx["ts"], ctx["te"]))` or clamp every
   end-time to `ctx["te"]`.
4. **Nothing moves** → your expression has no `t` in it (constant), or your
   window times are off — print `ctx["ts"]`, `ctx["te"]` from `build()` with
   a temporary `print()` to see where the paragraph really sits.
5. **Frame forensics without a full render** (run anywhere ffmpeg exists):

```bash
ffmpeg -y -f lavfi -i color=c=0x11151c:s=640x360:r=30:d=6 \
  -vf "<paste your fragments, comma-joined>" \
  -ss 1.5 -frames:v 1 frame.png
```

Renders one frame of your effect over a fake dark background in ~2 seconds.
Change `-ss` to sample different moments. This is how flash.py was verified
before shipping.

## 5. Read the source — each file teaches exactly one trick

| file | the trick to steal |
|---|---|
| `fade.py` | the shortest possible effect: gate() and nothing else |
| `slide.py` | progress + easing; direction dispatch (up/down vs left/right) |
| `scroll.py` | linear motion from off-screen; clamping the active sub-window |
| `bounce.py` | two motions summed: easing fall + decaying sine wobble |
| `shake.py` | x AND y animated together with different frequencies |
| `wave.py` | per-line phase offset (`+k` inside the sine) — rigid vs alive |
| `type.py` | per-line start times via `enumerate(ctx["lines"])` |
| `flicker.py` | multiplying two frequencies for organic randomness |
| `box.py` | the `extra=` escape hatch (no math at all!) |
| `flash.py` | stepping OUTSIDE drawtext: eq on the whole frame |

## 6. Exercises (increasing difficulty)

1. **[blink]** — alpha = `if(lt(mod((t-ts),0.8),0.4),1,0.15)` inside gate.
   (Yes, `mod` exists in ffmpeg expressions.)
2. **[crawl]** — Star-Wars crawl: y offset = `(ctx["te"]-t)*30` (rises as t
   grows). Gate the alpha; clamp so lines don't fly off mid-word.
3. **[letterbox]** — the drawbox wipe from §3, but bars close AND reopen:
   in 0.5s, hold, out 0.5s before `te`.
4. **[pulse]** — fake zoom via `extra=":shadowcolor=white@0.5:shadowx=…"`,
   breathing shadow distance with a slow sine. Weird and beautiful.
5. **[glitch]** — shake + flicker combined: x jumps with
   `if(lt(mod((t-ts),0.25),0.05), 20*random(0), 0)` — random needs a seed
   argument in ffmpeg; `random(0)` is fine and re-rolls each frame.

When one of yours works, commit it (`git add effects/ && git commit -m
"my effect" && git push`) — your effects folder becomes your personal VFX
library that survives any Codespace rebuild.
