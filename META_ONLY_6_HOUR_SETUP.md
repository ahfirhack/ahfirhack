# Hybrid four-channel setup (every 6 hours)

The filename is retained so existing links continue to work. The production pipeline is now hybrid:

| Channel | Media pipeline | Audio | Output |
|---|---|---|---|
| 1 — Silicon Crime Files | Licensed/public sourced visuals | Locked Edge voice + music | Narration-timed Short |
| 2 — StoryFuse | Licensed/public sourced visuals | Locked Edge voice + music | Narration-timed Short |
| 3 — Epic History Kids | Meta AI Create, five connected scenes | Meta native scene audio | 50-second Short |
| 4 — Stoic Reset | Licensed/public sourced visuals | Locked Edge voice + music | Narration-timed Short |

## Install locally

Open PowerShell in the repository:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
ffmpeg -version
```

The sourced-media channels can run with key-free public sources. These optional GitHub secrets improve media availability and matching:

- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`
- `COVERR_API_KEY`
- `VIDEEZY_CLIENT_ID` and `VIDEEZY_CLIENT_SECRET`
- `YOUTUBE_API_KEY`
- `JAMENDO_CLIENT_ID`
- `FREESOUND_API_KEY`

The configured channel voices use `edge-tts`, which is installed from `requirements.txt`.

## Configure Meta for channel 3

Keep Chrome signed in on `https://meta.ai/create`, temporarily enable Chrome remote debugging for the import, then run:

```powershell
python switch_meta_account.py --from-open-chrome
python switch_meta_account.py --publish-only --repo YOUR_OWNER/YOUR_REPO
```

This publishes slot 1 as `META_AI_STORAGE_STATE_B64`. Optional fallback accounts can be imported and published as slots 2–5 using the steps in [META_ACCOUNT_SWITCH.md](META_ACCOUNT_SWITCH.md). Never commit session JSON, cookies, browser profiles, OAuth secrets, or tokens.

Meta is used only by channel 3. Manual GitHub runs for channels 1, 2, or 4 skip the Meta-session requirement.

## Configure YouTube OAuth

Use one Google Cloud project and one Desktop OAuth client for all four YouTube channels:

1. Enable YouTube Data API v3.
2. Save the client JSON as `credentials/youtube_shared_secrets.json`.
3. Run `python auth_tokens.py` and authorize each YouTube channel, producing `channel1_token.json` through `channel4_token.json`.
4. Publish `YOUTUBE_SHARED_SECRETS_B64` and `CHANNEL1_TOKEN_B64` through `CHANNEL4_TOKEN_B64` using `python setup.py` or `python encode_secrets.py`.

The workflow rejects tokens belonging to a different OAuth client before generation begins.

## Preview without uploading

```powershell
# Restored sourced-media route
python test_pipeline.py 1

# Meta route; this may consume five Meta generations
python test_pipeline.py 3

# Preview all channels sequentially
python test_pipeline.py all
```

Outputs are written to `output_videos/PREVIEW_channel_N.mp4`. Preview media history is isolated from production deduplication state.

## Run or upload

```powershell
python main.py --once --channel 1
python main.py --once --channel 3
python main.py --once
```

The first two commands upload only the selected channel; the last processes all four sequentially. Sequential execution is intentional because the restored media modules share temporary working filenames.

## GitHub Actions schedule

The workflow runs at `00:13`, `06:13`, `12:13`, and `18:13` UTC. Manual dispatch can select `all` or one channel. It validates that:

- channel 3 alone is configured for Meta native video/audio;
- channels 1, 2, and 4 use sourced media, locked narration, and music;
- all selected YouTube tokens belong to the shared OAuth client.

If channel 3 cannot render or download a valid 720×1280-or-better source clip with native audio, its unfinished job is retained for resumption. Other selected channels continue and are reported independently.
