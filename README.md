# YouTube Shorts Automation — Setup Guide

Fully automated YouTube Shorts pipeline.  
**4 channels × 2 scheduled runs = up to 8 Shorts each day.**
Vertical video plus script, prompt, title, and clip deduplication are included.

---

## Channels

| # | Channel | Handle | Niche | Music Mood |
|---|---------|--------|-------|------------|
| 1 | **Silicon Crime Files** | `@SiliconCrimeFiles` | High-stakes tech and corporate true crime from documented public cases | Suspenseful |
| 2 | **StoryFuse** | `@StoryFuseTV` | Cinematic deep storytelling, escalating stakes, and twist endings | Mysterious |
| 3 | **Epic History Kids** | `@EpicHistoryKids` | Kid-safe stories about civilizations, people, inventions, and discoveries | Playful |
| 4 | **Stoic Reset** | `@StoicResetShorts` | Ancient wisdom applied to modern stress and mental health | Cinematic |

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
- `channel1_token.json` → Silicon Crime Files
- `channel2_token.json` → StoryFuse
- `channel3_token.json` → Epic History Kids
- `channel4_token.json` → Stoic Reset

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
| `CHANNEL1_TOKEN_B64` | base64 of `credentials/channel1_token.json` (Silicon Crime Files) |
| `CHANNEL2_TOKEN_B64` | base64 of `credentials/channel2_token.json` (StoryFuse) |
| `CHANNEL3_TOKEN_B64` | base64 of `credentials/channel3_token.json` (Epic History Kids) |
| `CHANNEL4_TOKEN_B64` | base64 of `credentials/channel4_token.json` (Stoic Reset) |
| `OPENROUTER_API_KEY` | optional free-tier prompt-provider key |
| `CEREBRAS_API_KEY` | optional free-tier prompt-provider key |
| `HF_TOKEN` | optional Hugging Face Inference Providers token |
| `MISTRAL_API_KEY` | optional Mistral free/experimental-tier key |
| `COHERE_API_KEY` | optional Cohere trial-tier key |
| `NVIDIA_API_KEY` | optional NVIDIA NIM developer key |
| `CLOUDFLARE_API_TOKEN` | optional Workers AI token |
| `CLOUDFLARE_ACCOUNT_ID` | required with the Workers AI token |

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
- Dedup is tracked in `used_scripts.json`, compact `used_prompts.json`, and
  `used_videos.json`. Every channel has its own transactional SQLite reserve:
  `prompt_reserve_channel_1.sqlite3`, `prompt_reserve_channel_2.sqlite3`,
  `prompt_reserve.sqlite3` (Channel 3), and `prompt_reserve_channel_4.sqlite3`.
  All state is committed after each run.
- Ready-prompt counts are **Channel 1: 2,048 official public-record cases**,
  **Channel 2: 2,048**, **Channel 3: 2,560**, and **Channel 4: 2,048**.
  A used reserve row is deleted only after YouTube confirms the upload.

---

## How It Works

```
Script (12-provider active-model failover, then the channel's SQLite reserve)
    ↓
Channel 3: Meta AI Create in persistent Chrome → 3 × 10-second scenes
Other channels: ranked topic-matched clips for hook → escalation → payoff
    ↓
Channel 3: preserve Meta video voice/audio; no added music
Other channels: TTS voice + music
    ↓
Assembly (FFmpeg — 1440×2560 vertical)
    ↓
Upload to YouTube as #Shorts
```

Channels 1, 2, and 4 use locked, channel-specific Edge voices, large two-line
captions driven by the narrator's real word boundaries, and episode-specific
hook cards. Their three narrative beats are matched against Pexels, Pixabay,
Coverr, Wikimedia Commons, Internet Archive, NASA, Openverse, and the Art
Institute of Chicago. Channel 1 can also capture its official government record
as the evidence-first visual. Wikimedia's maintained HD video derivatives are
preferred before a licensed photograph or public-domain artwork is converted
locally into a vertical cinematic motion clip.

The non-Meta channels fail closed: black frames, flat-color clips, broadcast
test patterns, missing narrative beats, and missing caption timing metadata all
stop the run before upload. There is no synthetic color-card or black-video
fallback. Results are ranked by topic overlap and joined as equal, gapless
hook/escalation/payoff segments. Media credits are added to the YouTube
description automatically. Channel 3 adds no hook text, captions, end screen,
external voiceover, or background music; its Meta workflow is unchanged.

### Local no-upload preview

Run `python test_pipeline.py` to exercise all four channels without importing
or calling the YouTube uploader. Pass `1`, `2`, `3`, or `4` to test selected
channels. Preview prompts are read without reserving or consuming SQLite rows,
and preview media history is isolated from production deduplication state. The
command continues through every selected channel, writes local MP4s under
`output_videos/PREVIEW_channel_N.mp4`, and returns a nonzero exit status if any
channel fails. Each rerun replaces that channel's previous preview and removes
legacy timestamped test previews, so validation never accumulates duplicates.

The script generator has twelve integrations and discovers currently active
models at runtime where catalogs are available. Its failover chain is Groq,
Hugging Face Router, Mistral, NVIDIA NIM, Cloudflare Workers AI, OpenRouter
Free, Cerebras, Cohere, Gemini, Nova, Claude, and Amazon Bedrock. Missing keys
are skipped automatically. A daily `AI Script Generator Health` workflow
rotates through Channels 1, 2, and 4 (one per day to respect free-tier limits)
and validates a fresh script and its packaging. Manual runs can target a
specific channel or all three.

### Epic History Kids — automated Meta AI Create workflow

Channel 3 uses Playwright to control `https://meta.ai/create` through a
dedicated persistent Chromium profile. It does not use Muse Automation or a
media-generation API key. Every video request includes the same permanent Milo
character, voice, style, and continuity prompt. Meta generates Milo's speech
inside each video. Scene 1 is generated directly; scenes 2 and 3 also use the
exact final frame of the preceding video. The assembler preserves the native
Meta audio, normalizes the three clips to ten seconds each, and joins their
audio and video timestamps without black, silent, or empty gap frames.

Channel 3 queries provider model catalogs at runtime and tries active models
across every configured provider until one returns a valid, unused story.
OpenRouter uses its maintained `openrouter/free` router instead of a fixed
model ID. If all configured AI services fail, Channel 3 reserves one of 2,560
ready, unique historical stories from `prompt_reserve.sqlite3`. That row stays
reserved during Meta rendering and assembly and is permanently deleted only
after YouTube returns a successful upload ID. Failed runs keep their unfinished
job and reservation for automatic resumption. The database is never silently
reseeded after prompts are consumed.

Small hard-coded fallback lists remain disabled for Channel 3. Compact hashes
of the title, script, and complete prompt are stored in `used_prompts.json`;
an exact title check against the authenticated YouTube channel runs before
every upload. If both the providers and the reserve are exhausted, the run
fails without generating or uploading a duplicate.

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
three videos from the permanent prompt, assembles the Short, and uploads it.
Temporary Meta service errors are retried four times with increasing delays.
If Meta expires or challenges the session, the workflow stops before upload;
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
| **Channel 3 script generation failed** | Every configured provider failed or repeated a prompt, and the SQLite reserve is exhausted. Check provider secrets and the available row count in `prompt_reserve.sqlite3`. |
| **Channel 1, 2, or 4 script generation failed** | Check the daily `AI Script Generator Health` run and that channel's `prompt_reserve_channel_N.sqlite3` available-row count. The pipeline fails closed instead of recycling a used episode. |
| **Meta safety service temporarily unavailable** | No account change is needed. The runner automatically retries four times and preserves the unfinished job for the next run. |
| **Font missing on runner** | The GitHub Action installs `fonts-open-sans` and `fonts-dejavu-core` automatically |
