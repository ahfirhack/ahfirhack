# Fresh Meta AI Video Test — GitHub Actions

This is a **manually triggered**, standalone smoke test for your existing Meta-only `ahfirhack` project. It does **not** change the 6-hour production schedule or upload any videos to YouTube.

## Modes

- **1 scene (default)**: Launch Playwright on a GitHub-hosted Ubuntu runner, restore the ordered Meta sessions (slot 1 from `META_AI_STORAGE_STATE_B64`, plus any configured slots 2–4), open **Meta Create only**, submit a new original StoryFuse scene prompt, wait for completion, **download the actual video**, and verify its 10-second duration, 9:16-ish portrait orientation, video track, native audio track, and true 1080p-or-higher source resolution. Includes the downloaded MP4 in Actions artifacts on success. Does not assemble an incomplete Short and never falls back to Vibes Studio.
- **5 scenes**: Do the above five times, attaching the actual last frame from the preceding Meta clip, validate continuity, and assemble one 50-second Short using the existing FFmpeg assembler. Adds `META_GITHUB_SMOKE_50S.mp4` to the workflow artifact. This costs up to five Meta generations and is intended **only after mode 1 passes**.

Both modes use an isolated fresh job and do not consume your prompt-reserve queues. Neither mode reads YouTube credentials or sends a YouTube upload. No third-party stock media, separate voice-over, or image generation is used.

## Installation (PowerShell — non-administrator)

1. Copy/extract the patch contents **into your existing project checkout**, not a new sibling folder. Keep the `.github` folder and its subfolder structure intact.

```powershell
Set-Location "C:\Users\Abdal\Downloads\Videos\ahfirhack-meta-account-switch\ahfirhack-main"
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\meta-ai-github-actions-smoke-test.zip" -DestinationPath . -Force
python -m unittest discover -s tests -p test_meta_github_smoke.py -v
```

2. Confirm your GitHub repository already has the primary **repository Actions secret** `META_AI_STORAGE_STATE_B64`, created by the separate Chrome account-import workflow:

```powershell
python switch_meta_account.py --publish-only --repo YOUR_OWNER/YOUR_REPO
```

Optional failover accounts are published separately with `--slot 2`, `--slot 3`
and `--slot 4`. The smoke test and production workflow always try slot 1 first.

`YOUR_OWNER/YOUR_REPO` means the **actual repository that runs this automation**. If your browser session has expired or your Meta account requires verification on a cloud runner, you must re-authenticate and re-export the session. Cloud Actions cannot attach to Chrome running on your local Windows machine.

3. Commit the four new files and push them to your GitHub repository's **default branch**. If the existing directory is a Git clone:

```powershell
git add .github/workflows/meta_ai_smoke_test.yml scripts/meta_github_smoke.py tests/test_meta_github_smoke.py META_GITHUB_ACTIONS_SMOKE_TEST.md
git commit -m "Add safe Meta AI generation and download smoke test"
git push
```

Do not commit `meta_ai_storage_state.json`, credentials, session cookies, Chrome browser profiles, or video job directories. If this unpacked folder is not a Git checkout, copy these four files into your cloned GitHub repository and run the commands there.

4. In GitHub, open **Actions → Meta AI Fresh Generation and Download Test → Run workflow**. Choose `scenes = 1` first. Once it passes, choose `scenes = 5` to test full assembly.

5. Open the workflow run → **Artifacts** → download `meta-smoke-RUN_ID`. On success: find the video under `clips/scene_01.mp4`. Five-scene success also adds `short/META_GITHUB_SMOKE_50S.mp4`. `result.json`, `summary.md`, and `diagnostics/*.json` explain failures.

## Important limits and safeguards

- This is a real live test; it can use Meta generation credits or quota. A rendered clip that fails to download is **not automatically regenerated** by the smoke test. `diagnostics/scene_01_download.json` records failure reasons.
- Passing unit tests does **not** mean video downloads work on the live Meta site; only a completed GitHub run with a valid MP4 artifact proves that.
- Only safe JSON metadata and generated clips are uploaded. **Screenshots, cookies, storage state, media URLs, authentication traces and YouTube credentials are never part of the test artifact.** Generated video clips may still be visible to people who can access the repository's workflow artifacts; keep the repository private if necessary.
- GitHub-hosted runners use a separate browser and often run from a different IP/location; Meta might require a new login or reject the copied session. That cannot be solved by extra selector retries.
- Five 10-second clips with visual continuity and synchronized audio are requested, but Meta's current UI, generation length, output audio, and quota can vary by account. The test **fails clearly** if the requirement is not met rather than substituting another provider.
- The production schedule at 00:13, 06:13, 12:13 and 18:13 UTC remains unaffected by this test. A shared concurrency group prevents the smoke test from running simultaneously with production.
