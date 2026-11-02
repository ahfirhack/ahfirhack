# Hybrid YouTube Shorts Automation: Four Channels Every 6 Hours

This repository runs one Short per selected channel, with two deliberately separate media pipelines:

- **Channels 1, 2, and 4** use the restored pre-all-Meta workflow: licensed/public sourced visuals, a fixed Edge TTS voice per channel, background music, synchronized captions, three narrative visual beats, and the legacy FFmpeg assembler.
- **Channel 3 (Epic History Kids)** keeps the current Meta AI workflow: five consecutive 10-second portrait videos with native audio, final-frame handoffs, duplicate-scene checks, and gap-free 50-second assembly.

The GitHub Actions schedule is `13 */6 * * *` (UTC), up to four runs per day. Scheduled runs process all four channels; manual runs can select one channel.

All four YouTube channels authorize through **one shared Google Cloud OAuth project**, with one token per YouTube channel. The repository intentionally does not use separate Google projects as a combined quota pool.

See [META_ONLY_6_HOUR_SETUP.md](META_ONLY_6_HOUR_SETUP.md) for the complete hybrid setup and local preview instructions.

## Processing routes

Channels 1, 2, and 4:

`unique script` → `three topic-matched sourced visual beats` + `locked voice` + `music` → `narration-timed 1440×2560 assembly and validation` → `YouTube upload`

Channel 3:

`unique script` → `Meta AI 5 × 10-second portrait video/native-audio scenes` → `continuity, duplicate, duration, audio, and 720p-source validation` → `frame-matched 1440×2560 assembly` → `YouTube upload`

Meta failures affect channel 3 only. A manual run for channel 1, 2, or 4 does not require a Meta browser session. Channel 3 fails closed if Meta cannot provide a valid scene; it never substitutes stock footage or external voiceover.

## Quick commands

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium

# No-upload previews
python test_pipeline.py 1
python test_pipeline.py 3

# Upload one selected channel
python main.py --once --channel 1
python main.py --once --channel 3
```

Only channel 3 requires a signed-in Meta session. Up to five isolated Meta account sessions remain supported for its account failover; see [META_ACCOUNT_SWITCH.md](META_ACCOUNT_SWITCH.md).
