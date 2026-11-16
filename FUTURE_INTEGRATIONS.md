# FUTURE INTEGRATIONS — roadmap: YouTube, socials, Colab/HF, full automation

This file is the plan for everything *after* "script.txt → final.mp4 works".
Each phase is independent — do them in any order, but Phase 1 unlocks
Phase 4, and Phase 3 is only worth it once you outgrow CPU TTS.

Effort estimates assume theCodespace workflow you already know
(edit → preview → commit). No phase requires touching the effects system.

---

## Phase 1 — Upload to YouTube automatically (≈ one focused weekend)

**What:** after a render, push `final.mp4` straight to YouTube as a draft
or public video, from the terminal.

**The pieces:**

1. Google Cloud console (console.cloud.google.com) → create a project →
   **Enable "YouTube Data API v3"** → OAuth consent screen (External,
   yourself as test user) → Credentials → **OAuth client ID → Desktop app**
   → download `client_secret.json` into the repo root (NOT into git).
2. `pip install google-api-python-client google-auth-oauthlib` (add to
   `requirements.txt` — comment it out if you want Codespace builds lean).
3. A new `youtube.py` (~80 lines) with one function:

```python
def upload(path, title, description, tags, privacy="private"):
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    # first run: opens a browser to sign in; Codespaces forwards the
    # localhost port so the sign-in URL appears in Ports > forwarded.
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json",
                                                     scopes)
    creds = flow.run_local_server(port=8080)          # caches nothing yet
    yt = build("youtube", "v3", credentials=creds)
    body = {"snippet": {"title": title, "description": description,
                        "tags": tags, "categoryId": "24"},
            "status": {"privacyStatus": privacy,       # private = safe default
                       "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    done = None
    while done is None:
        status, done = req.next_chunk()
        if status:
            print(f"  upload {int(status.progress() * 100)}%")
    return done["id"]
```

4. Wire it into `build_video.py`: add `--upload` and `--title` argparse
   flags, call `upload(...)` at the end of `main()` when `--upload` is set.
   First run saves `token.json` (pickle the creds with
   `google.auth.transport.requests` refresh flow) so later runs are silent.

**Quota math (important):** default daily quota = 10,000 units; a video
insert costs ~1,600 → **~6 uploads/day**. Fine for a human cadence.

**Safety rules — non-negotiable:**
- `client_secret.json` and `token.json` go into `.gitignore` BEFORE you
  create them. Pushed secrets = revoke immediately in the console.
- Prefer `privacy="private"` while testing; YouTube's "altered content"
  disclosure (AI voice) is ticked in Studio — check the current Data API
  docs for a programmatic field before automating public uploads.

---

## Phase 2 — Other platforms (honest status, ≈ 1 evening to set up the workaround)

| Platform | Programmatic upload | Reality |
|---|---|---|
| TikTok | Content Posting API exists | requires app review; unofficial libs violate ToS → ban risk |
| Instagram Reels | Graph API `instagram_content_publish` | needs Business account + Facebook Page + Meta app review |
| X / Twitter | API v2 media | upload endpoints are on paid tiers now |
| Pinterest | API exists | video pins, moderate setup |

**The pragmatic path:** render once, then post manually from your phone,
or automate the boring part with a scheduler service (Buffer / Metricool
free tiers, or Make.com) that watches a cloud folder. For vertical Shorts /
Reels you already have the lever: `config.yaml` → `width: 1080`,
`height: 1920` — render a second cut with `--out output/shorts.mp4`.

---

## Phase 3 — GPU offload to Google Colab or Hugging Face (≈ a weekend)

**Why:** your 2-core Codespace renders fine, but (a) TTS is the slow half,
(b) the interesting big engines — Chatterbox (voice cloning from ~10s
audio), larger Kokoro-style models — only run well on GPU. The stub already
waiting at `tts_backends/chatterbox_backend.py` is for exactly this.

**The design: split the pipeline in two, join with a file.**

Add two flags to `build_video.py` (the change is small — `main()` already
has the seams):

- `--tts-only` → run stages 1–3, write `output/narration.wav` AND a new
  `output/timeline.json` containing `titles`, `fx`, `srt segments`,
  `total`. Stop.
- `--from-timeline output/timeline.json` → skip TTS entirely, load the
  windows from JSON, run stages 4–5 (background + render) exactly as now.

`build_timeline()` already returns everything in `titles`/`fx`/`srt_segs`
— serializing it is ~15 lines of `json.dump`.

**Transport options (pick one):**
- *Google Drive:* Colab mounts your Drive; you drop `timeline.json` +
  wavs into one folder, the Codespace reads it. Zero extra accounts.
- *HF Hub:* a private dataset repo under your account; upload/download via
  `huggingface_hub.upload_file()` — works from Colab AND Codespaces, and
  gives you versioning for free.

**Colab sketch (GPU runtime, cells):**

```python
# 1. clone + install
!git clone https://github.com/slowsleep0/kokoro-video-pipeline
%cd kokoro-video-pipeline
!pip install -q -r requirements.txt "chatterbox-tts"

# 2. TTS on GPU -> Drive
from google.colab import drive
drive.mount("/content/drive")            # your folder as the file bus

# 3. run the split stage (after implementing --tts-only)
!python build_video.py --tts-only --script topics/ocean.txt --out /content/drive/MyDrive/videos/ocean/
```

Then back in the Codespace: `python build_video.py --from-timeline ...`
renders the 1080p video from the GPU-made audio.

**HF Spaces variant:** deploy a tiny Gradio Space (free GPU quota) whose
`api()` endpoint takes text + voice and returns a wav — then your
`tts_backends/` grows a `RemoteEngine` that calls it with
`gradio_client.Client("you/tts-space")`. Same `TTSEngine` contract, so
`config.yaml: tts.backend: remote` is the only switch.

---

## Phase 4 — Full automation with GitHub Actions (≈ one evening, after Phase 1)

**Why:** Actions runners are free for public repos, ubuntu-latest is a
2-core machine — the exact size this pipeline was built for. A scheduled
workflow can render AND upload with zero Codespace open.

`.github/workflows/nightly.yml` sketch:

```yaml
name: nightly-video
on:
  schedule: [{cron: "0 6 * * *"}]     # 06:00 UTC daily
  workflow_dispatch: {}               # manual run button
concurrency: nightly-video            # never two renders at once
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg espeak-ng
      - run: pip install torch --index-url https://download.pytorch.org/whl/cpu
      - run: pip install -r requirements.txt
      - run: python -m spacy download en_core_web_sm
      - run: python build_video.py --script topics/$(date +%F).txt
      - run: python youtube.py --upload output/final.mp4  # Phase 1 code
        env:
          YT_TOKEN: ${{ secrets.YT_TOKEN }}           # secret, never in git
```

Feeder pattern: keep a `topics/` folder of ready scripts; the workflow
picks the day's file (or a small `--next-topic` flag that pops a queue).
No Codespace hours burned, runs even when you sleep.

**Guardrails:** `concurrency:` prevents double uploads; keep uploads
`private` until you trust the loop; quota math from Phase 1 caps you at
~6/day; a failed run emails you — check Actions tab before scaling up.

---

## Order recommendation

1. Phase 1 (upload) — highest value per hour, unlocks Phase 4.
2. Phase 4 (Actions) — automation dopamine, no GPU needed.
3. Phase 3 (GPU) — only when you actually want voice cloning or speed.
4. Phase 2 (socials) — manual/scheduler first; APIs later, if ever.

At every phase: `git commit` before you start, one feature per commit,
and secrets never leave the Secrets vault.
