# Meta Create clip download diagnostics + paused-scene rescue

This patch fixes the missing *reason* when a browser-triggered Meta export is rejected. It does not re-submit prompts, change the scenes, remove the 10-second portrait/native-audio requirement, use external media, edit YouTube credentials, or alter the 3-worker scheduler.

## Why the old logs were ambiguous

The existing script silently discarded a downloaded clip if `ffprobe` found no native audio, a non-10-second duration, landscape footage, or an unreadable container. This patch logs privacy-safe failure categories and preserves the **first playable but rejected video** at `.../debug/scene_01_rejected_export.mp4`, instead of deleting the only evidence. The rejected clip is not given to the assembler.

## Install (PowerShell, non-administrator)

From `ahfirhack-main`:

```powershell
Copy-Item .\modules\meta_clip_download.py .\modules\meta_clip_download.py.before_diagnostic -Force
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\meta-download-diagnostic-recovery.zip" -DestinationPath . -Force
python -m unittest discover -s tests -p "test_meta_clip_diagnostic_recovery.py" -v
```

## First inspect the existing failure without spending credits

```powershell
Get-Content ".\meta_ai_jobs\channel_2\mara-s-call-from-tomorrow-night-train-e13800e357\debug\scene_01_download.json" -Raw
```

Interpretation: `download_events=0` means no Playwright download started; `download_events>0` means an export did start but the file may have failed validation. `ui_actions` reveals which Meta button was clicked; `source_scheme` shows only the URL type, not its confidential URL. `source_fetch_attempted=true` alone is not proof that a clip was retrieved.

## Rescue the already-generated Meta clip (no regeneration)

The failed browser session may have closed. If the same generated video is available in your Meta Create history, use its own **Download** button in regular Chrome. Locate the saved file (often Downloads). **Only import the exact video for that scene.**

```powershell
python recover_meta_scene.py --channel 2 --file "$env:USERPROFILE\Downloads\ACTUAL_META_VIDEO_FILENAME.mp4"
python test_pipeline.py 2 --workers 1
```

Replace the filename with the real download name. The rescue tool will reject silent, short, landscape or unreadable clips and will not overwrite a valid scene. The existing job marker is only removed by the main pipeline after it revalidates and extracts the last frame. This avoids spending more credits on scene 1.

## If Meta downloaded the wrong format

The rejection log now includes safe `duration_seconds`, `video_width`, `video_height` and whether it has an `audio_track`. A 5-second or silent result cannot meet this project's **five 10-second native-audio scenes** requirement without changing the generation method or requirements; the patch does not fabricate missing audio or extend the clip. A silent/short clip remains in the job's debug folder for inspection, not assembly.

## If NO download started

Your actual Meta page may expose a different button or menu. Open the private local screenshot `.../debug/scene_01.png` to see what Chrome displayed. Do not share screenshots without covering account details. The downloader cannot recover an earlier closed result automatically without a stable Meta-provided history/export path.

Do not upload `meta_ai_storage_state.json`, cookies, private links, or GitHub secrets.
