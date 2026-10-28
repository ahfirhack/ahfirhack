# YouTube Shorts Automation — Setup Guide

Fully automated YouTube Shorts pipeline.  
**4 channels × 2 scheduled runs = up to 8 Shorts each day.**
Vertical video plus script, prompt, title, and clip deduplication are included.

---

## Channels

| # | Channel | Niche | Music Mood |
|---|---------|-------|------------|
| 1 | **Psychology & Human Behavior** | Psychology facts, social behavior, and cognitive biases | Suspenseful |
| 2 | **The History Mystery** | Forgotten history, ancient technology, and historical mysteries | Mysterious |
| 3 | **Epic History Kids** | Kid-safe stories about civilizations, people, inventions, and discoveries | Playful |
| 4 | **The Modern Stoic** | Ancient wisdom applied to modern stress and mental health | Epic cinematic |

---

## STEP 1 — YouTube API Setup (one-time per project)

1. Go to: https://console.cloud.google.com
2. Create a new project (e.g., `YT-Automation`)
3. **APIs & Services → Enable APIs** → enable **YouTube Data API v3**
4. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop app** → Download JSON
6. Rename the file to `client_secrets.json` → place in the `credentials/` folder

> **One `client_secrets.json` is shared by all 4 channels.**

---

## STEP 2 — Generate OAuth Tokens (one-time, run locally)

```bash
pip install -r requirements.txt
python auth_tokens.py
```

This opens your browser **4 times** — sign in with the correct Google account for each channel.  
Token files are saved in `credentials/`:
- `channel1_token.json` → Psychology & Human Behavior
- `channel2_token.json` → The History Mystery
- `channel3_token.json` → Epic History Kids
- `channel4_token.json` → The Modern Stoic

---

## STEP 3 — Encode Credentials for GitHub

```bash
python encode_secrets.py
```

This prints a base64 value for each file. Copy them — you'll need them in Step 4.

---

## STEP 4 — Add Secrets to GitHub

Go to: **Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|-------------|-------|
| `CLIENT_SECRETS_B64` | base64 of `credentials/client_secrets.json` |
| `CHANNEL1_TOKEN_B64` | base64 of `credentials/channel1_token.json` (Psychology & Human Behavior) |
| `CHANNEL2_TOKEN_B64` | base64 of `credentials/channel2_token.json` (The History Mystery) |
| `CHANNEL3_TOKEN_B64` | base64 of `credentials/channel3_token.json` (Epic History Kids) |
| `CHANNEL4_TOKEN_B64` | base64 of `credentials/channel4_token.json` (The Modern Stoic) |

---

## STEP 5 — Enable GitHub Actions

The workflow uses GitHub's hosted `ubuntu-latest` runner. Complete the one-time
Meta browser-session export described below, add it as a repository secret, and
then go to **Repo → Actions** and enable workflows.

The workflow runs automatically once every twelve hours (00:00 and 12:00 UTC).
You can also trigger it manually: **Actions → daily_upload → Run workflow**

---

## Daily Output

- 4 channels × 2 videos = **8 Shorts per day**
- ~240 Shorts per month — fully automated
- Dedup tracked in `used_scripts.json`, compact `used_prompts.json`, and
  `used_videos.json` (committed back after each run)

---

## How It Works

```
Script (Groq / Nova / Gemini / Claude / Bedrock)
    ↓
Channel 3: Meta AI Create in persistent Chrome → 3 × 10-second scenes
Other channels: stock clips until their individual optimization pass
    ↓
Channel 3: preserve Meta video voice/audio; no added music
Other channels: TTS voice + music
    ↓
Assembly (FFmpeg — 1440×2560 vertical)
    ↓
Upload to YouTube as #Shorts
```

Channels 1, 2, and 4 retain their caption overlays. Channel 3 adds no hook
text, captions, end screen, external voiceover, or background music.

### Epic History Kids — automated Meta AI Create workflow

Channel 3 uses Playwright to control `https://meta.ai/create` through a
dedicated persistent Chromium profile. It does not use Muse Automation or a
media-generation API key. Every video request includes the same permanent Milo
character, voice, style, and continuity prompt. Meta generates Milo's speech
inside each video. Scene 1 is generated directly; scenes 2 and 3 also use the
exact final frame of the preceding video. The assembler preserves the native
Meta audio, normalizes the three clips to ten seconds each, and joins their
audio and video timestamps without black, silent, or empty gap frames.

Channel 3 tries every configured script provider until one returns a valid,
unused story. Canned fallback stories are disabled. Compact hashes of the
title, script, and complete prompt are stored in `used_prompts.json`; an exact
title check against the authenticated YouTube channel runs before every upload.
If no provider produces a unique script, the run fails without generating or
uploading a duplicate.

GitHub-hosted machines are fresh for every job, so the Meta login is restored
from an encrypted GitHub Actions secret. Complete one local interactive login,
export Playwright storage state, and publish its compressed base64 value:

```bash
pip install -r requirements.txt
python -m playwright install chromium --with-deps
export META_AI_CHROME_PROFILE_DIR="$PWD/.meta-ai-profile"
export META_AI_STORAGE_STATE_FILE="$PWD/meta_ai_storage_state.json"
python main.py --meta-login
gzip -c "$META_AI_STORAGE_STATE_FILE" | base64 -w 0 | gh secret set META_AI_STORAGE_STATE_B64
```

The workflow restores that session into Chromium through Xvfb, generates all
three videos from the permanent prompt, assembles the Short, and uploads it. If
Meta expires or challenges the session, the workflow stops before upload;
repeat the login/export command to refresh the secret.

The signed-in Meta account must be eligible for Vibes video generation, be 18
or older, and be in a supported region. Check `https://meta.ai/vibes` before
exporting the session. If it shows an age/region restriction or Meta replies
that video generation is unavailable, the pipeline fails immediately and does
not substitute still images or GIFs.

Prepare a prompt job without rendering or uploading:

```bash
python main.py --prepare-meta
```

Run the complete automated Channel 3 pipeline only:

```bash
python main.py --once --channel 3
```

Run the same focused test on a GitHub-hosted runner:

```bash
gh workflow run daily_upload.yml -f channel=3 -f meta_timeout_seconds=300
```

Manual dispatches can select one channel; scheduled runs continue to process
all four. Failed Meta runs preserve unfinished scenes in the Actions cache and
upload a seven-day diagnostic artifact.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| **Token expired** | Re-run `python auth_tokens.py`, re-run `python encode_secrets.py`, update GitHub secret |
| **YouTube quota exceeded** | YouTube allows ~6 uploads/day per project. Apply for higher quota at console.cloud.google.com |
| **No video clips found** | Broaden the channel's `keywords` list in `config.py` |
| **Channel 3 script generation failed** | Every configured provider failed, returned the wrong length, or repeated an existing prompt. Check the provider secrets; Channel 3 intentionally has no canned fallback. |
| **Font missing on runner** | The GitHub Action installs `fonts-open-sans` and `fonts-dejavu-core` automatically |
