#!/usr/bin/env python3
"""
kokoro-video-pipeline v3
========================
script.txt ──► parse ──► Kokoro TTS ──► narration.wav ──► ffmpeg ──► output/final.mp4
                │                                       ▲
     ## Title lines → title cards            clips/*.mp4 (auto-looped)
     [fx: opts] tags  → animations from effects/ (plugin registry)

Script format
-------------
  ## The Hidden Ocean           -> animated title card on a BLURRED background
  ## Life in Darkness [dark]    -> title card on a PLAIN BLACK background
  Normal paragraph              -> spoken narration
  Paragraph [fade]              -> spoken AND shown as an animated overlay
  Paragraph [scroll: 0, 3, 80]  -> effect name + options, comma separated
  Paragraph [fade][slide: left] -> multiple effects chain

Effects are PLUGINS: one small Python file per effect in effects/, registered
in effects/__init__.py. Write your own - guide with cheatsheet: effects/README.md

Usage:
    python build_video.py                    # full-quality build from config.yaml
    python build_video.py --preview          # fast 720p draft (test the flow first!)
    python build_video.py --script other.txt # different input file
    python build_video.py --out output/v2.mp4
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from tts_backends import load_engine
from effects import REGISTRY, parse_opts

ROOT = Path(__file__).resolve().parent
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}

TITLE_RE = re.compile(r"^##\s*(.*?)\s*$")
STYLE_RE = re.compile(r"\s*\[(blur|dark)\]\s*$", re.IGNORECASE)
# trailing tag at the end of a paragraph:  [name]  or  [name: opt, opt, ...]
TAG_RE = re.compile(r"\s*\[([A-Za-z_][A-Za-z0-9_]*)(?::([^\[\]]*))?\]\s*$")

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

TC_DEFAULTS = {
    "enabled": True,
    "default_style": "blur",   # blur = blurred background | dark = plain black
    "duration": 3.0,           # seconds each card stays on screen
    "font_size": 72,           # at 1080p; scaled with the video size
    "wrap_chars": 28,          # wrap long titles after N characters
    "font": "auto",            # path to a .ttf file, or "auto"
}

FX_DEFAULTS = {
    "enabled": True,
    "font_size": 48,           # at 1080p; scaled with the video size
    "wrap_chars": 36,          # tagged paragraphs wrap after N characters
    "color": "white",          # text color (name or 0xRRGGBB)
}


# ----------------------------------------------------------------- helpers --
def run(cmd: list) -> None:
    print("  $ " + " ".join(str(c) for c in cmd[:12]) + (" ..." if len(cmd) > 12 else ""))
    subprocess.run([str(c) for c in cmd], check=True)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def find_font(cfg_font: str) -> str:
    if cfg_font and cfg_font != "auto":
        p = Path(cfg_font)
        if not p.is_absolute() and (ROOT / p).exists():
            p = ROOT / p
        if not Path(p).exists():
            sys.exit(f"Font not found: {cfg_font} (fix title_cards.font in config.yaml)")
        return str(p)
    for c in FONT_CANDIDATES:
        if Path(c).exists():
            return c
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "sans:weight=bold"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    sys.exit("No .ttf font found - install fonts-dejavu-core or set title_cards.font")


def wrap_title(text: str, max_chars: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if not cur or len(cur) + 1 + len(w) <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:4]  # hard cap: 4 lines on screen


def srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list[tuple], path: Path) -> None:
    lines, i = [], 0
    for start, end, text in segments:
        text = " ".join(str(text).split())
        if not text:
            continue
        i += 1
        lines += [str(i), f"{srt_time(start)} --> {srt_time(end)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  subtitles -> {path.name}")


# ------------------------------------------------------------ script parsing --
def parse_script(text: str, titles_enabled: bool,
                 fx_enabled: bool = True) -> list[dict]:
    """Split the script into 'title' cards and 'voice' narration paragraphs.
    Voice paragraphs carry their trailing [effect: options] tags (peeled off)."""
    parts: list[dict] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        m = TITLE_RE.match(block)
        if m:
            title, inline = m.group(1), None
            sm = STYLE_RE.search(title)
            if sm:
                inline, title = sm.group(1).lower(), title[: sm.start()].strip()
            if title:
                if titles_enabled:
                    parts.append({"kind": "title", "text": title, "style": inline})
                else:
                    parts.append({"kind": "voice", "text": " ".join(title.split()),
                                  "effects": []})
            continue
        # voice paragraph - peel trailing [effect: options] tags off the end
        effects: list[tuple[str, str | None]] = []
        body = block
        while True:
            tm = TAG_RE.search(body)
            if not tm:
                break
            if fx_enabled:
                raw = tm.group(2).strip() if tm.group(2) is not None else None
                effects.append((tm.group(1).lower(), raw))
            body = body[: tm.start()].rstrip()
        effects.reverse()  # restore written left-to-right order
        parts.append({"kind": "voice", "text": " ".join(body.split()),
                      "effects": effects})
    return parts


# ------------------------------------------------------------ audio timeline --
def _resample(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or len(audio) == 0:
        return audio
    n_out = int(round(len(audio) / sr_in * sr_out))
    idx = np.linspace(0, len(audio) - 1, n_out)
    return np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)


def build_timeline(parts: list[dict], engine, tc: dict, work: Path,
                   out_dir: Path) -> tuple[Path, list, list, list, float]:
    """Synthesize every narration paragraph, lay everything on one timeline
    (silence for title cards) and write output/narration.wav.

    Returns (wav_path, srt_segments, title_windows, fx_windows, total_duration).
    """
    wavs, segs_local, sr = {}, {}, None
    for i, p in enumerate(parts):
        if p["kind"] != "voice":
            continue
        wav = work / f"part_{i:03d}.wav"
        segs_local[i] = engine.synthesize(p["text"], str(wav))
        audio, asr = sf.read(str(wav), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr is None:
            sr = asr
        wavs[i] = _resample(audio, asr, sr)
        print(f"    part {i:02d}: {len(wavs[i]) / sr:5.2f}s  {p['text'][:50]}")
    sr = int(sr or getattr(engine, "SAMPLE_RATE", 24000) or 24000)

    pieces: list[np.ndarray] = []
    srt: list[tuple] = []
    titles: list[dict] = []
    fx: list[dict] = []
    t = 0.0
    for i, p in enumerate(parts):
        if p["kind"] == "voice":
            t0 = t
            audio = wavs[i]
            for s in segs_local[i]:
                srt.append((s.start + t, s.end + t, s.text))
            pieces.append(audio)
            t += len(audio) / sr
            if p.get("effects"):
                fx.append({"ts": t0, "te": t, "text": p["text"],
                           "effects": [(n, parse_opts(raw)) for n, raw in p["effects"]]})
        else:
            d = float(tc["duration"])
            titles.append({"ts": t, "te": t + d, "text": p["text"],
                           "style": (p["style"] or tc["default_style"]).lower()})
            pieces.append(np.zeros(int(round(sr * d)), dtype=np.float32))
            t += d

    narration = out_dir / "narration.wav"
    data = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
    sf.write(str(narration), data, sr, subtype="PCM_16")
    return narration, srt, titles, fx, t


# ---------------------------------------------------------------- background --
def make_background(clips: list[Path], total: float, W: int, H: int, fps: int,
                    vq: tuple[str, int], out_dir: Path) -> Path:
    """Build .bg.mp4: the clips looped/trimmed to exactly the narration length."""
    bg = out_dir / ".bg.mp4"
    vq_p, vq_c = vq
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps},setsar=1")

    if not clips:
        print("  (no clips in clips/ - using a plain dark background)")
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", f"color=c=0x11151c:s={W}x{H}:r={fps}:d={total + 0.5:.2f}",
             "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", vq_p,
             "-crf", str(vq_c), "-pix_fmt", "yuv420p", bg])
    elif len(clips) == 1:
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1",
             "-i", clips[0], "-t", f"{total:.3f}", "-vf", vf,
             "-c:v", "libx264", "-preset", vq_p, "-crf", str(vq_c),
             "-pix_fmt", "yuv420p", "-an", bg])
    else:
        print(f"  joining {len(clips)} clips into one loopable background...")
        cycle = out_dir / ".cycle.mp4"
        inputs, parts = [], []
        for i, c in enumerate(clips):
            inputs += ["-i", str(c)]
            parts.append(f"[{i}:v]{vf},format=yuv420p[c{i}]")
        fc = (";".join(parts) + ";" +
              "".join(f"[c{i}]" for i in range(len(clips))) +
              f"concat=n={len(clips)}:v=1:a=0[cat]")
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
             "-filter_complex", fc, "-map", "[cat]",
             "-c:v", "libx264", "-preset", vq_p, "-crf", str(vq_c), "-an", cycle])
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1",
             "-i", cycle, "-t", f"{total:.3f}",
             "-c:v", "libx264", "-preset", vq_p, "-crf", str(vq_c),
             "-pix_fmt", "yuv420p", "-an", bg])
        cycle.unlink(missing_ok=True)
    return bg


# ---------------------------------------------------------------- title cards --
def build_title_inputs(titles: list[dict], W: int, H: int, fps: int, tc: dict,
                       work: Path, font: str) -> tuple[list[str], list[str], str]:
    """Build the ffmpeg inputs + filtergraph for all title cards.

    blur style: background branch blurred + darkened, faded in/out, text on top
    dark style: black overlay faded in/out, text on top
    text:       fade-in + slide-up animation, white with a soft shadow

    Returns (extra_input_args, filtergraph_lines, current_label).
    """
    extra: list[list[str]] = []
    fc: list[str] = []
    fs = max(18, round(int(tc["font_size"]) * H / 1080))
    lh = int(fs * 1.35)
    drift = int(H * 0.06)
    n_blur = sum(1 for t in titles if t["style"] == "blur")

    cur = None
    if n_blur:
        outs = "".join(f"[bs{k}]" for k in range(n_blur))
        fc.append(f"[0:v]split={n_blur + 1}[base]{outs}")
        cur = "base"
    else:
        cur = "0:v"

    bi = di = 0
    for tinfo in titles:
        ts, te, style = tinfo["ts"], tinfo["te"], tinfo["style"]
        if style == "blur":
            # blur a downscaled copy (cheap + smooth), dim it slightly, alpha-fade it
            fc.append(
                f"[bs{bi}]scale=iw/8:ih/8,boxblur=4:2,scale={W}:{H},"
                f"eq=brightness=-0.06,format=yuva420p,"
                f"fade=t=in:st={max(0.0, ts - 0.4):.2f}:d=0.45:alpha=1,"
                f"fade=t=out:st={max(0.0, te - 0.45):.2f}:d=0.45:alpha=1[bl{bi}]")
            fc.append(f"[{cur}][bl{bi}]overlay="
                      f"enable='between(t,{max(0.0, ts - 0.45):.2f},{te + 0.1:.2f})'[ov{bi}]")
            cur = f"ov{bi}"
            bi += 1
        else:
            k = 2 + di  # input index: 0=bg, 1=narration, 2..=black sources
            extra.append(["-f", "lavfi", "-i",
                          f"color=c=black:s={W}x{H}:r={fps}:d={te + 1:.2f}"])
            fc.append(
                f"[{k}:v]format=yuva420p,"
                f"fade=t=in:st={max(0.0, ts - 0.4):.2f}:d=0.45:alpha=1,"
                f"fade=t=out:st={max(0.0, te - 0.45):.2f}:d=0.45:alpha=1[dk{di}]")
            fc.append(f"[{cur}][dk{di}]overlay="
                      f"enable='between(t,{max(0.0, ts - 0.45):.2f},{te + 0.1:.2f})'[od{di}]")
            cur = f"od{di}"
            di += 1

    # animated text (one drawtext per wrapped line)
    for j, tinfo in enumerate(titles):
        ts, te = tinfo["ts"], tinfo["te"]
        lines = wrap_title(tinfo["text"], int(tc["wrap_chars"]))
        y0 = (H - len(lines) * lh) // 2
        if te - ts >= 1.5:
            a_expr = (f"max(0,if(lt(t,{ts + 0.8:.2f}),(t-{ts:.2f})/0.8,"
                      f"if(lt(t,{te - 0.5:.2f}),1,({te:.2f}-t)/0.5)))")
        else:
            a_expr = "1"
        for li, line in enumerate(lines):
            tf = work / f"title{j:02d}_l{li}.txt"
            tf.write_text(line, encoding="utf-8")
            y_expr = f"{y0 + li * lh}+{drift}*(1-min((t-{ts:.2f})/0.8,1))"
            fc.append(
                f"[{cur}]drawtext=fontfile={font}:textfile={tf}:fontsize={fs}:"
                f"fontcolor=white:x=(w-text_w)/2:y='{y_expr}':alpha='{a_expr}':"
                f"shadowcolor=black@0.6:shadowx=3:shadowy=3[tx{j}_{li}]")
            cur = f"tx{j}_{li}"
    return [a for e in extra for a in e], fc, cur


# ------------------------------------------------------------------ fx chain --
def build_fx_chain(fx: list[dict], W: int, H: int, fps: int, txc: dict,
                   work: Path, font: str, fc: list[str], cur: str) -> tuple[list[str], str]:
    """Call every effect plugin for every tagged paragraph and chain the
    returned drawtext filters onto the current video label.

    This is the whole "system": a paragraph tagged  [name: a, b, c]  becomes
    REGISTRY[name]({"pos": [a, b, c], "kw": {...}}, ctx)  and whatever
    drawtext filters the effect returns are appended to the video chain.
    """
    fs = max(16, round(int(txc["font_size"]) * H / 1080))
    lh = int(fs * 1.3)
    fxi = 100
    for wi, w in enumerate(fx):
        lines = wrap_title(w["text"], int(txc["wrap_chars"]))
        y0 = (H - len(lines) * lh) // 2
        files = []
        for k, line in enumerate(lines):
            tf = work / f"fx{wi:02d}_l{k}.txt"
            tf.write_text(line, encoding="utf-8")
            files.append({"file": tf, "y0": y0 + k * lh})
        ctx = {"ts": w["ts"], "te": w["te"], "W": W, "H": H, "fps": fps,
               "font": font, "fs": fs, "lh": lh, "lines": files,
               "color": txc.get("color", "white"), "text": w["text"],
               "work": work, "idx": wi}
        for name, opts in w["effects"]:
            if name not in REGISTRY:
                sys.exit(f"Unknown effect '[{name}]'. Available: "
                         f"{', '.join(sorted(REGISTRY))}\n"
                         "Write your own: copy effects/fade.py, see effects/README.md")
            for frag in REGISTRY[name](opts, ctx):
                fc.append(f"[{cur}]{frag}[fx{fxi}]")
                cur = f"fx{fxi}"
                fxi += 1
    return fc, cur


# ------------------------------------------------------------------- render --
def render(bg: Path, wav: Path, titles: list[dict], fx: list[dict], total: float,
           W: int, H: int, fps: int, vq: tuple[str, int], tc: dict, txc: dict,
           burn_srt: Path | None, work: Path, out: Path,
           wave: dict | None = None) -> None:
    wave = wave or {}
    wave_mode = str(wave.get("mode", "off")).lower()
    wave_color = str(wave.get("color", "0x4FC3F7"))
    wave_h = max(60, round(int(wave.get("height", 180)) * H / 1080))
    wave_h = min(wave_h - wave_h % 2, H // 3)      # even px, max 1/3 of screen
    if wave_mode != "off":
        af = ("[1:a]asplit=2[al][aw];"             # tap narration twice:
              "[al]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    else:
        af = "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
    vq_p, vq_c = vq
    extra: list[str] = []
    fc: list[str] = []
    cur = "0:v"

    if titles:
        e, t_fc, cur = build_title_inputs(titles, W, H, fps, tc, work,
                                          find_font(tc["font"]))
        extra += e
        fc += t_fc

    if fx:
        fc, cur = build_fx_chain(fx, W, H, fps, txc, work,
                                 find_font(tc["font"]), fc, cur)

    if burn_srt is not None:
        fc.append(f"[{cur}]subtitles={burn_srt}[sb]")
        cur = "sb"

    if wave_mode != "off":  # audio-reactive strip along the bottom edge
        if wave_mode == "bars":
            wspec = (f"[aw]showfreqs=r={fps}:s={W}x{wave_h}:mode=bar"
                     f":ascale=cbrt:colors={wave_color}[wv]")
        else:
            # draw at 1/8 width first: ~7 samples per column makes the
            # min/max envelope actually fill; stretched back up it reads
            # as a fat music-video waveform instead of a 1-px hairline.
            # scale=sqrt boosts quiet parts of the curve (thicker line)
            # while keeping word/pause contrast at ~4:1.
            wspec = (f"[aw]showwaves=r={fps}:s={W // 8}x{wave_h}"
                     f":mode=cline:scale=sqrt:colors={wave_color}"
                     f",scale={W}:{wave_h}[wv]")
        strip_y = H - wave_h - 8                   # dim backdrop so it reads
        fc.append(f"[{cur}]drawbox=x=0:y={strip_y}:w=iw:h={wave_h + 8}"
                  f":color=black@0.55:t=fill[wbs]")
        fc.append(wspec)                           # audio -> video stream
        fc.append(f"[wbs][wv]overlay=x=0:y={strip_y}[vwx]")
        cur = "vwx"

    if not fc and wave_mode == "off":  # nothing drawn -> stream-copy bg (fast)
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
             "-i", bg, "-i", wav, "-filter_complex", af,
             "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}",
             "-movflags", "+faststart", out])
        return

    fc.append(f"[{cur}]format=yuv420p[vout]")
    fc.append(af)  # audio: loudnorm to YouTube's -14 LUFS

    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
         "-i", bg, "-i", wav, *extra,
         "-filter_complex", ";".join(fc),
         "-map", "[vout]", "-map", "[aout]",
         "-c:v", "libx264", "-preset", vq_p, "-crf", str(vq_c),
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}",
         "-movflags", "+faststart", out])


# -------------------------------------------------------------------- main --
def main() -> None:
    ap = argparse.ArgumentParser(description="script.txt -> TTS + title cards + effects -> final.mp4")
    ap.add_argument("--script", help="input text file (default: paths.script in config.yaml)")
    ap.add_argument("--out", help="output mp4 path (default: output/final.mp4)")
    ap.add_argument("--preview", action="store_true",
                    help="fast low-res draft (use this to test the flow)")
    args = ap.parse_args()

    t_start = time.time()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    tc = {**TC_DEFAULTS, **(cfg.get("title_cards") or {})}
    txc = {**FX_DEFAULTS, **(cfg.get("text_fx") or {})}

    v = dict(cfg["video"])
    if args.preview:
        f = 720.0 / min(int(v["width"]), int(v["height"]))
        v["width"], v["height"] = max(2, int(v["width"] * f) // 2 * 2), max(2, int(v["height"] * f) // 2 * 2)
        v["preset"], v["crf"] = "ultrafast", max(int(v.get("crf", 23)), 28)
        print(f"PREVIEW draft {v['width']}x{v['height']} (ultrafast, crf {v['crf']})")
    W, H, fps = int(v["width"]), int(v["height"]), int(v["fps"])
    vq = (v.get("preset", "veryfast"), int(v.get("crf", 23)))

    script_path = ROOT / (args.script or cfg["paths"]["script"])
    text = script_path.read_text(encoding="utf-8").strip()
    if not text:
        sys.exit(f"Script is empty: {script_path}")
    parts = parse_script(text, bool(tc["enabled"]), bool(txc["enabled"]))
    n_title = sum(1 for p in parts if p["kind"] == "title")
    if not any(p["kind"] == "voice" for p in parts):
        sys.exit("script.txt has no narration paragraphs (only title cards)")
    print(f"script: {len(parts) - n_title} narration paragraph(s) + {n_title} title card(s)")

    out_dir = ROOT / cfg["paths"]["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / ".work"
    work.mkdir(exist_ok=True)

    clips_dir = ROOT / cfg["paths"]["clips_dir"]
    clips = (sorted(p for p in clips_dir.iterdir()
                    if p.suffix.lower() in VIDEO_EXTS and not p.name.startswith("_"))
             if clips_dir.exists() else [])

    print(f"[1/4] TTS engine: {cfg['tts']['backend']} - synthesizing narration...")
    t1 = time.time()
    engine = load_engine(cfg["tts"])
    wav, srt_segs, titles, fx, total = build_timeline(parts, engine, tc, work, out_dir)
    t_tts = time.time() - t1
    print(f"  narration.wav: {total:.1f}s  (TTS {t_tts:.1f}s)")
    write_srt(srt_segs, out_dir / "narration.srt")
    for tinfo in titles:
        print(f"  title card [{tinfo['style']}] {tinfo['ts']:6.1f}-{tinfo['te']:6.1f}s  "
              f"'{tinfo['text']}'")
    for w in fx:
        print(f"  fx overlay   {w['ts']:6.1f}-{w['te']:6.1f}s  "
              f"[{' + '.join(n for n, _ in w['effects'])}]  '{w['text'][:40]}'")

    print("[2/4] preparing background...")
    t2 = time.time()
    bg = make_background(clips, total, W, H, fps, vq, out_dir)
    print(f"  background ready ({time.time() - t2:.1f}s)")

    print("[3/4] rendering title cards + effects + final video...")
    t3 = time.time()
    out = ROOT / (args.out or out_dir / "final.mp4")
    burn = out_dir / "narration.srt" if v.get("burn_subtitles") else None
    render(bg, wav, titles, fx, total, W, H, fps, vq, tc, txc, burn, work, out,
           wave=cfg.get("wave"))
    t_render = time.time() - t3

    (out_dir / ".bg.mp4").unlink(missing_ok=True)

    print(f"[4/4] Done -> {out}")
    print(f"      {ffprobe_duration(out):.1f}s, {out.stat().st_size / 1e6:.1f} MB")
    print(f"      TTS {t_tts:.1f}s + render {t_render:.1f}s = {time.time() - t_start:.1f}s total")


if __name__ == "__main__":
    main()
