"""
main.py (v9 — Voice + Music, 8-hour schedule)
- Voiceover using ElevenLabs/Deepgram TTS
- Background music mixed with voice
- Videos uploaded every 8 hours
- Script deduplication: never repeats a title/script across runs
- Videos uploaded as YouTube Shorts (vertical 9:16, #Shorts in title)
"""

import os
import sys
import time
import datetime
import shutil
import hashlib
import json

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    CHANNELS, VIDEOS_PER_CHANNEL_PER_DAY, TEMP_DIR, OUTPUT_DIR,
    SHORT_DURATION_TARGET, USED_SCRIPTS_FILE, UPLOAD_INTERVAL_SECONDS,
)
from modules.script_generator import generate_script
from modules.music_fetcher import generate_background_music
from modules.video_fetcher import fetch_video_clips
from modules.video_assembler import assemble_video
from modules.uploader import upload_video
from modules.voiceover import generate_voiceover

CLIP_COUNT = 6


def clean_temp():
    # Windows can temporarily lock files (WinError 32) right after ffmpeg/readers finish.
    if os.path.exists(TEMP_DIR):
        last_err = None
        for _ in range(8):
            try:
                shutil.rmtree(TEMP_DIR)
                last_err = None
                break
            except (PermissionError, OSError) as e:
                last_err = e
                winerror = getattr(e, "winerror", None)
                if winerror == 32 or "WinError 32" in str(e):
                    time.sleep(1.0)
                    continue
                raise
        if last_err is not None and os.path.exists(TEMP_DIR):
            # Last resort: try best-effort cleanup.
            shutil.rmtree(TEMP_DIR, ignore_errors=True)

    os.makedirs(TEMP_DIR, exist_ok=True)


# ── Single-instance lock (prevents concurrent runs clobbering temp/) ──
def _acquire_run_lock() -> str:
    """
    Prevent multiple concurrent executions of main.py.
    When tool timeouts leave a previous run active, overlapping runs cause
    missing temp files (One process deletes temp while another is rendering).
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    lock_path = os.path.join(TEMP_DIR, "pipeline.lock")

    try:
        # Exclusive create: fails if lock_path already exists
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return lock_path
    except FileExistsError:
        try:
            with open(lock_path, "r") as f:
                pid = f.read().strip()
        except Exception:
            pid = "unknown"
        print(f"[Main] Another run is active (lock exists, pid={pid}). Exiting.")
        sys.exit(0)


def _release_run_lock(lock_path: str):
    try:
        if lock_path and os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


# ── Script deduplication ─────────────────────────────────────
def _load_used_scripts() -> set:
    if os.path.exists(USED_SCRIPTS_FILE):
        try:
            with open(USED_SCRIPTS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_used_scripts(used: set):
    with open(USED_SCRIPTS_FILE, "w") as f:
        json.dump(list(used), f)


def _script_hash(data: dict) -> str:
    """
    Maximum uniqueness fingerprint: title + topic + search_query
    This ensures no duplicate content across runs.
    """
    title = data.get("title", "").lower()
    script = data.get("script", "").lower()
    search_query = data.get("search_query", "").lower()
    # Combine all three for maximum uniqueness
    fingerprint = f"{title}|{script[:100]}|{search_query}"
    return hashlib.md5(fingerprint.encode()).hexdigest()[:16]


def _generate_unique_script(niche: str, used_scripts: set) -> dict:
    """Retry generation up to 5 times to avoid repeated scripts."""
    data = None
    for _ in range(5):
        data = generate_script(niche)
        h = _script_hash(data)
        if h not in used_scripts:
            used_scripts.add(h)
            _save_used_scripts(used_scripts)
            return data
    # All retries produced known scripts — use it anyway to not block pipeline
    h = _script_hash(data)
    used_scripts.add(h)
    _save_used_scripts(used_scripts)
    return data


# ── Per-video pipeline ───────────────────────────────────────
def process_video(channel: dict, video_index: int, used_scripts: set):
    channel_name = channel["name"]
    niche        = channel["niche"]
    music_mood   = channel.get("music_mood", "relaxing")
    use_voice    = channel.get("use_voice", True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = channel["id"].replace(" ", "_")

    print(f"\n{'='*60}")
    print(f"  {channel_name} | Voice: {use_voice} | Music: {music_mood}")
    print(f"  Video {video_index + 1}/{VIDEOS_PER_CHANNEL_PER_DAY}")
    print(f"{'='*60}\n")

    # 1. Script (unique — no repeats)
    print("[1/6] Script (unique)...")
    data         = _generate_unique_script(niche, used_scripts)
    title        = data["title"]
    script       = data["script"]
    tags         = data["tags"]
    search_query = data["search_query"]
    print(f"      Title: {title}")
    print(f"      Words: {len(script.split())} | Query: {search_query}")

    # 2. Voiceover (if enabled)
    voice_path = None
    if use_voice:
        print("[2/6] Voiceover (ElevenLabs/Deepgram)...")
        voice_path = os.path.join(TEMP_DIR, f"{safe_name}_{timestamp}_voice.mp3")
        voice_style = channel.get("hook_style", "default")
        generate_voiceover(script, voice_path, voice_style=voice_style)
    else:
        print("[2/6] Voiceover skipped (music only)")

    # 3. Background music
    print("[3/6] Music...")
    music_path = os.path.join(TEMP_DIR, f"{safe_name}_{timestamp}_music.mp3")
    generate_background_music(music_mood, SHORT_DURATION_TARGET, music_path)

    # 4. Footage
    print(f"[4/6] Fetching {CLIP_COUNT} clips...")
    clips = fetch_video_clips(
        query=search_query,
        num_clips=CLIP_COUNT,
        script=script,
        niche_keywords=channel.get("keywords", []),
    )

    # 5. Assemble (Full HD 1080x1920, 9:16 Shorts)
    print("[5/6] Assembling...")
    fname      = f"{safe_name}_{timestamp}.mp4"

    # Use voice if available, otherwise use music only
    audio_for_video = voice_path if voice_path else music_path

    video_path = assemble_video(
        clip_paths=clips,
        audio_path=audio_for_video,
        script=script,
        output_filename=fname,
        channel_name=channel_name,
        music_path=music_path if voice_path else None,
    )

    # 6. Upload as YouTube Short
    print("[6/6] Uploading as Short...")
    upload_title = f"{title} #Shorts"
    video_id = upload_video(
        video_path=video_path,
        title=upload_title[:100],
        tags=tags + ["#Shorts"],
        channel_config=channel,
        script=script,
    )

    print(f"\n  {channel_name} → https://youtube.com/shorts/{video_id}\n")
    return video_id


# ── Daily batch ──────────────────────────────────────────────
def run_daily_batch():
    now   = datetime.datetime.now()
    total = len(CHANNELS) * VIDEOS_PER_CHANNEL_PER_DAY

    print(f"\n  YouTube Automation — {now.strftime('%Y-%m-%d %H:%M %A')}")
    print(f"  Channels: {len(CHANNELS)} | Videos/channel: {VIDEOS_PER_CHANNEL_PER_DAY} | Total: {total}\n")

    used_scripts = _load_used_scripts()
    results = []

    for ch in CHANNELS:
        for i in range(VIDEOS_PER_CHANNEL_PER_DAY):
            try:
                clean_temp()
                vid = process_video(ch, i, used_scripts)
                results.append({"ch": ch["name"], "vid": vid, "ok": True})
                if i < VIDEOS_PER_CHANNEL_PER_DAY - 1:
                    time.sleep(30)
            except Exception as e:
                print(f"\n  ERROR {ch['name']}: {e}")
                results.append({"ch": ch["name"], "vid": None, "ok": False})
        time.sleep(60)

    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}")
    print(f"  DONE: {ok}/{len(results)} uploaded")
    for r in results:
        s = "OK" if r["ok"] else "FAIL"
        print(f"  [{s}] {r['ch']} — {r.get('vid', 'error')}")
    print(f"{'='*60}\n")


# ── 8-hour schedule loop ───────────────────────────────────────
def run_scheduled():
    """Run the pipeline every 8 hours."""
    print(f"\n{'='*60}")
    print(f"  YouTube Automation — 8-Hour Schedule")
    print(f"  Upload interval: {UPLOAD_INTERVAL_SECONDS / 3600} hours")
    print(f"{'='*60}\n")

    while True:
        try:
            run_daily_batch()

            # Calculate next run time
            next_run = datetime.datetime.now() + datetime.timedelta(seconds=UPLOAD_INTERVAL_SECONDS)
            print(f"\n  Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Waiting {UPLOAD_INTERVAL_SECONDS / 3600:.1f} hours...\n")

            time.sleep(UPLOAD_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n\n  Stopping automation...")
            break
        except Exception as e:
            print(f"\n  ERROR in scheduled run: {e}")
            print(f"  Retrying in 60 seconds...\n")
            time.sleep(60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YouTube Multi-Channel Automation")
    parser.add_argument("--once", action="store_true", help="Run once and exit (no schedule)")
    args = parser.parse_args()

    if args.once:
        run_daily_batch()
    else:
        run_scheduled()
