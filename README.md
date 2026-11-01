# Meta AI-Only YouTube Shorts: Four Channels × Every 6 Hours

This project produces **one 50-second YouTube Short per channel per run**, using **exactly five 10-second Meta AI-generated videos** and FFmpeg to assemble them. No footage from Pexels, Pixabay, other stock sites, no third-party images/videos, no separate TTS narration and no outside music. Every scene carries its own native Meta audio and the previous scene's actual final frame is sent to Meta as its next visual reference.

**Schedule:** GitHub Actions `13 */6 * * *` (UTC), up to four runs/day. Every scheduled run processes all four channels.

**Channels:** Silicon Crime Files (`@SiliconCrimeFiles`), StoryFuse (`@StoryFuseTV`), Epic History Kids (`@EpicHistoryKids`), Stoic Reset (`@StoicResetShorts`).

Read **[META_ONLY_6_HOUR_SETUP.md](META_ONLY_6_HOUR_SETUP.md)** for full instructions, account import, GitHub secret setup, local previews and limitations.

### Processing stages

`Unique script from saved queue or text-only generator` → `Meta AI 5 × 10 sec portrait videos + native audio (previous last frame attached)` → `continuity / audio / duration / true 1080p-source validation` → `FFmpeg frame-matched 1440×2560, 50-second assembly` → `YouTube Short upload to that channel`.

If Meta AI is unavailable or produces a silent, short, discontinuous, or sub-1080p scene, its channel fails closed with resumable artifacts; there is **no media, voiceover, or resolution-upscale fallback**.

### Quick commands (PowerShell, non-administrator)

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python switch_meta_account.py --from-open-chrome
python test_pipeline.py 2
python main.py --once --channel 2
```

Up to four isolated Meta sessions are supported. The current account is slot 1
and remains primary; see `META_ACCOUNT_SWITCH.md` to add fallback slots 2–4.

The last command **uploads** to StoryFuse if all five Meta scenes pass. The preview command does not upload.
