# YouTube Shorts Automation — Setup Guide

Fully automated YouTube Shorts pipeline.  
**4 channels × 3 videos = 12 Shorts uploaded every day at 3 AM UTC.**  
Music-only. No voiceover. Full HD 1080×1920. No repeated scripts or clips.

---

## Channels

| # | Channel | Niche | Music Mood |
|---|---------|-------|------------|
| 1 | **Motivational Quotes** | Inspiring quotes, mindset wisdom, life-changing advice | Wisdom |
| 2 | **Weird Facts** | Mind-blowing facts, strange science, bizarre history | Mysterious |
| 3 | **People Stories** | True mystery stories, unexplained events, paranormal | Suspense |
| 4 | **Life Hacks** | Genius tips, DIY tricks, money-saving hacks | Upbeat |

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
- `channel1_token.json` → Motivational Quotes
- `channel2_token.json` → Weird Facts
- `channel3_token.json` → People Stories
- `channel4_token.json` → Life Hacks

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
| `CHANNEL1_TOKEN_B64` | base64 of `credentials/channel1_token.json` (Motivational Quotes) |
| `CHANNEL2_TOKEN_B64` | base64 of `credentials/channel2_token.json` (Weird Facts) |
| `CHANNEL3_TOKEN_B64` | base64 of `credentials/channel3_token.json` (People Stories) |
| `CHANNEL4_TOKEN_B64` | base64 of `credentials/channel4_token.json` (Life Hacks) |

---

## STEP 5 — Enable GitHub Actions

Go to: **Repo → Actions tab → Enable workflows**

The pipeline runs automatically every day at **3 AM UTC**.  
You can also trigger it manually: **Actions → daily_upload → Run workflow**

---

## Daily Output

- 4 channels × 3 videos = **12 Shorts per day**
- ~360 Shorts per month — fully automated
- Dedup tracked in `used_scripts.json` + `used_videos.json` (committed back after each run)

---

## How It Works

```
Script (Groq / Gemini / Claude)
    ↓
Video clips (Pexels / Pixabay / Coverr)
    ↓
Music (Jamendo API)
    ↓
Assembly (FFmpeg — 1080×1920, CRF 18, 8 Mbps)
    ↓
Upload to YouTube as #Shorts
```

Captions: 4 words per line, 2–3 lines on screen at a time.  
Short scripts (≤24 words) stay on screen for the full video duration.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| **Token expired** | Re-run `python auth_tokens.py`, re-run `python encode_secrets.py`, update GitHub secret |
| **YouTube quota exceeded** | YouTube allows ~6 uploads/day per project. Apply for higher quota at console.cloud.google.com |
| **No video clips found** | Broaden the channel's `keywords` list in `config.py` |
| **Script too short** | Expected — Groq returns short scripts sometimes. The fallback (72-word) script is used automatically |
| **Font missing on runner** | The GitHub Action installs `fonts-open-sans` and `fonts-dejavu-core` automatically |
