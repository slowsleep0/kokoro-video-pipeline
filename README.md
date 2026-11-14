# kokoro-video-pipeline

Write a script → get a finished video with AI voice-over, animated title cards
and your copyright-free clips behind it. Runs inside a free GitHub Codespace.
No server, no GPU, no paid API.

```
script.txt ──► parse ──► Kokoro TTS ──► narration.wav ──► ffmpeg ──► output/final.mp4
                │                          (silence for         ▲
        ## Title lines                     title cards)   clips/*.mp4 (auto-looped)
        become animated title cards
```

## Files you will touch

| File | What it is |
|---|---|
| `script.txt` | Your narration + `##` title cards (see below). |
| `clips/` | Drop your copyright-free videos here (mp4/mov/webm). |
| `config.yaml` | Voice, video size, title-card style. Edit later. |
| `output/final.mp4` | The finished video. Download it. |

Everything else (`build_video.py`, `tts_backends/`, `.devcontainer/`) is the
machinery — you don't need to open it.

## Title cards (new!)

Any paragraph starting with `##` becomes an **animated text card** — it is
*not* spoken. The text fades in and slides up; the card fades back out.

```
## The Hidden Ocean          <- card on a blurred version of your clips
## Life in Darkness [dark]   <- card on a plain black background
Normal paragraph...          <- spoken by the AI voice
```

- Each card stays on screen for `title_cards.duration` seconds (default 3.0),
  with silence in the narration while it shows.
- `[blur]` / `[dark]` after the title picks the style for that one card;
  without a tag the `default_style` from `config.yaml` is used.
- Long titles wrap automatically; font size, wrap width and even the `.ttf`
  font file are set in `config.yaml` under `title_cards:`.

## Text effects — a custom animation on any line (new!)

End any paragraph with a tag in square brackets. The text is **still spoken**,
and while the voice reads it, the animation plays on screen:

```
Breaking news tonight [scroll: 0, 3, 80]        <- scrolls across the screen
A quiet line [fade]
Big moment [bounce: 0.5][shake: 4, 2, 1.5, 3]   <- effects can chain
```

Options are comma-separated and mean whatever the effect defines (e.g.
`start, end, speed`). **This is a plugin system you can extend yourself:**
every animation is a ~15-line Python file in `effects/` — a function that
turns simple `x` / `y` / `alpha` math into movement. The full guide, with a
worked example and an ffmpeg expression cheatsheet, is in
**`effects/README.md`**.

Built-ins: `fade`, `slide`, `scroll`, `bounce`, `shake`. Global look (size,
wrap width, color) lives in `config.yaml` under `text_fx:`.

## First time: put it on GitHub (once ever)

1. Unzip this folder on your computer.
2. github.com → **+** (top right) → **New repository** → name it
   `kokoro-video-pipeline` → Private or Public → **leave all boxes unticked** →
   **Create repository**.
3. Click **"uploading an existing file"** → open the unzipped folder →
   select EVERYTHING inside it (Mac: first press **Cmd+Shift+.** to show
   hidden files) → drag it all into the upload box → **Commit changes**.

## First Codespace (installs itself, ~10 min — happens only once)

1. Repo page → green **Code** button → **Codespaces** tab →
   **Create codespace on main**.
2. A VS Code window opens and starts installing (you'll see text scrolling in
   the terminal). **Wait until it stops** (~10 min). This result is cached by
   GitHub — the next Codespace you ever create starts in ~2 minutes.

## Make one video (the part you'll repeat)

1. Drag 1–5 clips from your computer **into the `clips/` folder** (left panel).
2. Click `script.txt` → replace the text with your narration + `##` title
   cards → Ctrl+S.
3. In the terminal at the bottom, run:
   ```
   python build_video.py --preview    # quick low-res test
   python build_video.py              # full 1080p render
   ```
4. When it says `Done`, right-click `output/final.mp4` → **Download**.

## When you finish working

Just **close the tab**. That's it. Your Codespace keeps everything and the
free quota is enough for one all month.

Delete the Codespace only if GitHub shows you're close to the 15 GB storage
limit (billing page → Codespaces storage). Even then you lose nothing
important: recreate it in ~2 minutes and re-drop your clips.

## Handy knobs (config.yaml)

- Voice: `af_heart`, `af_bella`, `am_michael`, `bf_emma`... full list at
  huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
- YouTube Shorts: `width: 1080`, `height: 1920`
- Title cards: `default_style`, `duration`, `font_size`, `font`
  (any `.ttf` path — useful for non-Latin scripts)
- Burned subtitles into the video: `burn_subtitles: true` (a subtitle file
  `narration.srt` is always created anyway)
- Turn title cards off: `title_cards: {enabled: false}` — `##` lines are then
  just spoken as normal text.

## How long does a 30–45 min video take?

Free 2-core machine, rough numbers: TTS 15–50 min + render 25–75 min ≈
**45 min to 2 hours** total (title cards add ~3 s each). A 45-min video needs
a ~4,500–6,800 word script. The script prints exact times for every stage.

## Swapping the TTS engine later

Every engine only has to implement `synthesize(text, out_wav) -> segments`
(see `tts_backends/base.py`). Add a file, register 3 lines in
`tts_backends/__init__.py`, change one line in `config.yaml`. Done.

## Troubleshooting

| Problem | Fix |
|---|---|
| Setup/terminal stuck | Wait 5 more min, then reload the page |
| Weird pronunciations | Spell them phonetically in script.txt |
| Title text shows squares | Non-Latin font missing — set `title_cards.font` to a .ttf of your language |
| Render slow | Use `--preview`, or set `preset: ultrafast` |
| Storage full | Delete Codespace → recreate (~2 min) → re-drop clips |

`setup.sh` in this folder is only needed if you ever run the pipeline on your
own computer instead of a Codespace — inside Codespaces everything is already
installed by the Dockerfile.
