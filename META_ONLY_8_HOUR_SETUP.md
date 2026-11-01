# Meta AI ONLY: four YouTube channels, every 8 hours

**Scope**: video and native audio generation occur **only at Meta AI**. Script/story ideas may still come from the existing text-only script generators or saved SQLite prompt reserves. Video assembly is local FFmpeg. No stock footage, downloaded external pictures, external TTS, music, AI Horde images, captions or forced end screens.

## What happens per GitHub Actions run

1. Select one unique story from each of the four channel-specific prompt queues/text generators.
2. Meta AI Create (the only production surface) generates **five portrait 10-second clips** with native speech/audio, in sequence. Each new request attaches the **actual final PNG frame** extracted from the preceding generated Meta video. It repeats that channel's character, voice and camera/style locks. When the clip is already complete, reuse it on resumption. Vibes Studio is not an automatic fallback because its current exports fail the duration, native-audio and 1080p requirements.
3. Validate each generated clip: video+embedded audio, at least 1080x1920 source resolution, portrait orientation, 9.9–10.6 sec container duration, native audio at least 9.8 sec, and approximate first-frame similarity to the supplied last frame. Reject/ retry a clip if it does not match. If Meta quota, UI, quality options or account access prevents generation, stop this channel and keep its incomplete job; **never replace with stock, separate voiceover, resolution upscaling or other generators**.
4. FFmpeg extracts a matching handoff frame from each clip and **replaces**, rather than prepends, the next clip's first frame. It joins 5 × 300 normalized 30-fps frames with 5 native audio tracks, creating a **50-second** 1440x2560 Short with no transitions, external audio, overlays or added intro/outro. Pixel-perfect identity cannot be guaranteed after lossy H.264 encode; this method prevents intentional empty frames and minimizes visible discontinuity. Meta's subsequent motion may still jump; the handoff similarity check rejects conspicuous resets but cannot guarantee perfect actor/voice continuity.
5. Upload once to each channel's configured YouTube account; retain all unuploaded jobs for resume. One successful video **per channel per run**. At three scheduled runs a day, that is up to 12 Shorts/day, **subject to Meta limits**, authentication, render success and GitHub Actions runtime.

## Installation / update on Windows 11

1. Clone or pull the repository, then open PowerShell (non-administrator) in the project folder:

   ```powershell
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   ffmpeg -version
   ```

2. To use the Meta login already active in your existing Chrome window, keep Chrome on `https://meta.ai/create`, enable `chrome://inspect/#remote-debugging` **only while importing**, and run:

   ```powershell
   python switch_meta_account.py --from-open-chrome
   Test-Path .\meta_ai_storage_state.json
   ```

   This imports Meta-related state into `meta_ai_storage_state.json`; it does **not** make remote GitHub Actions use your running Chrome window. Turn remote debugging **off** afterward. Chrome might still require fresh authentication when the saved session runs on GitHub.

3. Preview *one* channel locally without uploading:

   ```powershell
   python test_pipeline.py 2
   ```

   **It can generate up to five real Meta clips**, consuming Meta quota. Verify output at `output_videos/PREVIEW_channel_2.mp4`. To preview all, omit `2`.

4. Publish the Meta AI session to your actual GitHub repo:

   ```powershell
   gh auth login
   python switch_meta_account.py --publish-only --repo YOUR_OWNER/YOUR_REPO
   ```

   This updates the GitHub Actions secret `META_AI_STORAGE_STATE_B64`. **Do not commit session JSON, cookies, tokens or browser profile files.**

5. Push the updated project code and workflows to the repository's default branch:

   ```powershell
   git add -A
   git commit -m "Use Meta Create only for native-audio Shorts"
   git push
   ```

   Check `git status` before committing to ensure credentials, browser profiles and saved Meta sessions are never staged.

6. Trigger a manual test at **GitHub → Actions → YouTube Upload (Meta AI Only Every 8 Hours) → Run workflow → channel 2**. Review its logs and artifact diagnostics. If successful, use `all` (four channels). Cron runs **00:13, 08:13, 16:13 UTC** (approximately 8:13 PM, 4:13 AM, 12:13 PM Eastern during daylight saving time; 7:13 PM, 3:13 AM, 11:13 AM during standard time).

## Limits and safety

- Meta does not guarantee five 10-second native-audio videos or a specific number of generations per account. One complete daily batch needs **20 accepted scene videos** (or up to 60/day if every run succeeds). Rate limits, UI changes and login challenges can prevent a run; an unsuccessful channel is reported as failed rather than silently substituted.
- A Meta account whose Studio quality menu tops out at 720p cannot satisfy the strict 1080p-source rule. The run stops before generation rather than representing a 720p upscale as genuine 1080p quality. Likewise, a video-only export without a native audio stream is never padded or given separate TTS.
- Current Chrome **cannot be directly controlled by GitHub-hosted runners**. GitHub Actions uses the imported session secret to open its own browser. An authenticated Chrome tab on your PC is not a persistent remote runner.
- FFmpeg reuses the last frame as the next frame; video/image matching and audio lip sync are not guaranteed by Meta. Verify preview before enabling unattended uploads.
- The video content is AI-generated; YouTube altered/synthetic disclosures may be required depending on depictions. For factual channels, verify scripts against the linked public sources.
- Only the upload workflow runs every eight hours. Script-generator health and YouTube cleanup are separate maintenance workflows with their own schedules.
