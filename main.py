"""
main.py (v9 — Voice + Music, 12-hour schedule)
- Voiceover using ElevenLabs/Deepgram TTS
- Background music mixed with voice
- Videos uploaded every 12 hours
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
    SHORT_DURATION_TARGET, USED_SCRIPTS_FILE, USED_PROMPTS_FILE,
    UPLOAD_INTERVAL_SECONDS,
)
from modules.script_generator import ScriptGenerationError, generate_script
from modules.music_fetcher import generate_background_music
from modules.video_fetcher import fetch_video_clips
from modules.video_assembler import assemble_video
from modules.uploader import upload_video
from modules.voiceover import generate_voiceover
from modules.meta_ai_generator import (
    MetaAIAutomationError,
    bootstrap_meta_login,
    create_job,
    ensure_rendered_clips,
    find_active_job,
    mark_job_complete,
)
from modules.prompt_reserve import (
    available_prompt_count,
    consume_prompt,
    reserve_prompt,
)

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
        json.dump(sorted(used), f, separators=(",", ":"))


def _load_used_prompts() -> set:
    if os.path.exists(USED_PROMPTS_FILE):
        try:
            with open(USED_PROMPTS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_used_prompts(used: set) -> None:
    """Persist compact hashes only; never store full generated prompts."""
    with open(USED_PROMPTS_FILE, "w") as f:
        json.dump(sorted(used), f, separators=(",", ":"))


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


def _normalized_text(value: str) -> str:
    return " ".join("".join(
        char.lower() if char.isalnum() else " " for char in value
    ).split())


def _prompt_hashes(channel_id: str, data: dict) -> set[str]:
    """Create compact channel and global hashes for duplicate blocking."""
    title = _normalized_text(data.get("title", ""))
    script = _normalized_text(data.get("script", ""))
    query = _normalized_text(data.get("search_query", ""))
    values = {"t": title, "s": script, "p": f"{title}|{script}|{query}"}
    hashes = {
        f"{channel_id}:{kind}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"
        for kind, value in values.items() if value
    }
    # Titles and scripts are also fingerprinted without a channel prefix. This
    # prevents two different channels from publishing the same episode while
    # keeping each channel's SQLite reserve physically independent.
    hashes.update(
        f"global:{kind}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"
        for kind, value in {"t": title, "s": script}.items() if value
    )
    return hashes


def _generate_unique_script(
    channel: dict,
    used_scripts: set,
    used_prompts: set,
) -> dict:
    """Exhaust providers and fail closed instead of accepting a duplicate."""
    niche = channel["niche"]
    track_prompts = channel.get("track_prompt_history", False)

    def is_duplicate(candidate: dict) -> bool:
        if _script_hash(candidate) in used_scripts:
            return True
        return bool(track_prompts and (_prompt_hashes(channel["id"], candidate) & used_prompts))

    last_error = None
    for attempt in range(1, 4):
        seed = hashlib.sha256(
            f"{channel['id']}|{datetime.datetime.now().isoformat()}|{attempt}".encode()
        ).hexdigest()[:12]
        try:
            data = generate_script(
                niche,
                allow_fallback=channel.get(
                    "allow_curated_fallback",
                    not channel.get("strict_ai_prompts", False),
                ),
                reject_candidate=is_duplicate,
                uniqueness_seed=seed,
            )
        except ScriptGenerationError as error:
            last_error = error
            print(f"[ScriptGen] Provider round {attempt}/3 produced no usable unique script")
            continue

        script_hash = _script_hash(data)
        prompt_hashes = _prompt_hashes(channel["id"], data)
        if script_hash in used_scripts or (track_prompts and prompt_hashes & used_prompts):
            last_error = ScriptGenerationError("Generator returned a previously used prompt")
            continue

        used_scripts.add(script_hash)
        _save_used_scripts(used_scripts)
        if track_prompts:
            used_prompts.update(prompt_hashes)
            _save_used_prompts(used_prompts)
        return data

    reserve_db = channel.get("prompt_reserve_db")
    if reserve_db:
        reservation_id = (
            f"{channel['id']}:{datetime.datetime.now().isoformat()}:{os.getpid()}"
        )
        while True:
            data = reserve_prompt(reserve_db, reservation_id, channel["id"])
            if data is None:
                break
            if not is_duplicate(data):
                print(
                    f"[ScriptGen] All AI providers exhausted -> SQLite reserve "
                    f"prompt {data['_reserve_prompt_id']}"
                )
                return data
            # A reseeded/restored database may contain an older used prompt.
            # Delete it permanently and continue to the next unused row.
            consume_prompt(reserve_db, data["_reserve_prompt_id"])

    raise ScriptGenerationError(
        "All configured AI providers and the SQLite prompt reserve were "
        "exhausted without a new unique prompt; no duplicate will be published."
    ) from last_error


# ── Per-video pipeline ───────────────────────────────────────
def process_video(
    channel: dict,
    video_index: int,
    used_scripts: set,
    used_prompts: set,
):
    channel_name = channel["name"]
    niche        = channel["niche"]
    music_mood   = channel.get("music_mood", "relaxing")
    use_voice    = channel.get("use_voice", True)
    use_music    = channel.get("use_music", True)
    native_audio = channel.get("native_clip_audio", False)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = channel["id"].replace(" ", "_")

    print(f"\n{'='*60}")
    audio_mode = "Meta native" if native_audio else ("TTS" if use_voice else "music")
    print(f"  {channel_name} | Audio: {audio_mode} | Music: {use_music}")
    print(f"  Video {video_index + 1}/{VIDEOS_PER_CHANNEL_PER_DAY}")
    print(f"{'='*60}\n")

    media_source = channel.get("media_source", "stock")
    meta_job_dir = None
    meta_manifest = None
    media_credits = []

    # 1. Script (unique — no repeats). An interrupted Meta AI job always resumes
    # before a new script is generated, so completed scenes are never orphaned.
    print("[1/6] Script (unique)...")
    active_meta_job = find_active_job(channel["id"]) if media_source == "meta_ai_browser" else None
    if active_meta_job:
        meta_manifest, meta_job_dir = active_meta_job
        data = meta_manifest["story"]
        print(f"      Resuming Meta AI job: {meta_manifest['job_id']}")
    else:
        data = _generate_unique_script(channel, used_scripts, used_prompts)

    title        = data["title"]
    script       = data["script"]
    tags         = data["tags"]
    search_query = data.get("search_query", title)
    print(f"      Title: {title}")
    print(f"      Words: {len(script.split())} | Query: {search_query}")

    # Meta AI runs through the dedicated signed-in Playwright Chrome profile.
    # No media-generation API key is stored or required.
    clips = None
    if media_source == "meta_ai_browser":
        if meta_manifest is None:
            meta_manifest, meta_job_dir = create_job(channel, data)
            print(f"      Meta AI prompt batch: {meta_job_dir / 'meta_prompts.txt'}")
        clips = ensure_rendered_clips(meta_manifest, meta_job_dir)
        print(f"      Meta AI renders ready: {len(clips)} seamless scenes")

    # 2. Voiceover (if enabled)
    voice_path = None
    if use_voice:
        print("[2/6] Voiceover (Deepgram/Edge TTS)...")
        voice_path = os.path.join(TEMP_DIR, f"{safe_name}_{timestamp}_voice.mp3")
        generate_voiceover(
            script,
            voice_path,
            channel_id=channel["id"],
            strict_voice=channel.get("strict_voice", False),
            voice_provider=channel.get("voice_provider"),
            require_timestamps=channel.get("require_word_timestamps", False),
        )
    elif native_audio:
        print("[2/6] Voiceover skipped (using Meta AI native character voice)")
    else:
        print("[2/6] Voiceover skipped (music only)")

    # 3. Background music
    music_path = None
    if use_music:
        print("[3/6] Music...")
        music_path = os.path.join(TEMP_DIR, f"{safe_name}_{timestamp}_music.mp3")
        generate_background_music(music_mood, SHORT_DURATION_TARGET, music_path)
    else:
        print("[3/6] Music skipped (using Meta AI native audio)")

    # 4. Footage
    if media_source == "meta_ai_browser":
        print(f"[4/6] Using {len(clips)} Meta AI scenes...")
    else:
        clip_count = 3 if channel.get("align_visual_beats", False) else CLIP_COUNT
        print(f"[4/6] Fetching {clip_count} topic-matched clips...")
        clips, media_credits = fetch_video_clips(
            query=search_query,
            num_clips=clip_count,
            script=script,
            niche_keywords=channel.get("keywords", []),
            visual_queries=data.get("visual_queries", []),
            include_attributions=True,
            source_url=data.get("source_url", ""),
        )

    # 5. Assemble (Full HD 1080x1920, 9:16 Shorts)
    print("[5/6] Assembling...")
    fname      = f"{safe_name}_{timestamp}.mp4"

    # Channel 3 keeps Meta's native audio; other channels use voice or music.
    audio_for_video = None if native_audio else (voice_path if voice_path else music_path)

    video_path = assemble_video(
        clip_paths=clips,
        audio_path=audio_for_video,
        script=script,
        output_filename=fname,
        channel_name=channel_name,
        music_path=music_path if voice_path else None,
        target_duration=channel.get("target_duration"),
        end_screen_duration=channel.get("end_screen_duration"),
        seamless_scenes=channel.get("seamless_scenes", False),
        native_clip_audio=native_audio,
        show_overlays=channel.get("show_overlays", True),
        opening_style=channel.get("opening_style", "default"),
        hook_sfx=channel.get("hook_sfx"),
        hook_overlay=data.get("hook_overlay", ""),
        hook_accent=data.get("hook_accent", ""),
        evidence_label=data.get("evidence_label", ""),
        require_visuals=channel.get("require_visuals", False),
        align_visual_beats=channel.get("align_visual_beats", False),
        reject_synthetic_visuals=channel.get("reject_synthetic_visuals", False),
        require_word_timestamps=channel.get("require_word_timestamps", False),
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
        source_url=data.get("source_url", ""),
        media_credits=media_credits,
    )

    if meta_job_dir is not None:
        mark_job_complete(meta_job_dir, video_id)

    reserve_prompt_id = data.get("_reserve_prompt_id")
    reserve_db = channel.get("prompt_reserve_db")
    if reserve_prompt_id is not None and reserve_db:
        # The row remains reserved through generation and assembly. It is
        # deleted only after upload_video returned a confirmed YouTube ID.
        consume_prompt(reserve_db, int(reserve_prompt_id))
        used_scripts.add(_script_hash(data))
        _save_used_scripts(used_scripts)
        used_prompts.update(_prompt_hashes(channel["id"], data))
        _save_used_prompts(used_prompts)
        print(
            f"[ScriptGen] Consumed SQLite prompt {reserve_prompt_id}; "
            f"{available_prompt_count(reserve_db, channel['id'])} prompts remain"
        )

    print(f"\n  {channel_name} → https://youtube.com/shorts/{video_id}\n")
    return video_id


# ── Daily batch ──────────────────────────────────────────────
def run_daily_batch(channel_ids: set[str] | None = None):
    now   = datetime.datetime.now()
    channels = [
        channel for channel in CHANNELS
        if not channel_ids or channel["id"] in channel_ids
    ]
    total = len(channels) * VIDEOS_PER_CHANNEL_PER_DAY

    print(f"\n  YouTube Automation — {now.strftime('%Y-%m-%d %H:%M %A')}")
    print(f"  Channels: {len(channels)} | Videos/channel: {VIDEOS_PER_CHANNEL_PER_DAY} | Total: {total}\n")

    used_scripts = _load_used_scripts()
    used_prompts = _load_used_prompts()
    results = []

    for channel_index, ch in enumerate(channels):
        for i in range(VIDEOS_PER_CHANNEL_PER_DAY):
            try:
                clean_temp()
                vid = process_video(ch, i, used_scripts, used_prompts)
                results.append({"ch": ch["name"], "vid": vid, "ok": True})
                if i < VIDEOS_PER_CHANNEL_PER_DAY - 1:
                    time.sleep(30)
            except MetaAIAutomationError as e:
                print(f"\n  META AI ERROR {ch['name']}: {e}")
                results.append({"ch": ch["name"], "vid": None, "ok": False})
            except Exception as e:
                print(f"\n  ERROR {ch['name']}: {e}")
                results.append({"ch": ch["name"], "vid": None, "ok": False})
        if channel_index < len(channels) - 1:
            time.sleep(60)

    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}")
    print(f"  DONE: {ok}/{len(results)} uploaded")
    for r in results:
        s = "OK" if r["ok"] else "FAIL"
        print(f"  [{s}] {r['ch']} — {r.get('vid', 'error')}")
    print(f"{'='*60}\n")
    return bool(results) and ok == len(results)


# ── 12-hour schedule loop ──────────────────────────────────────
def run_scheduled():
    """Run the pipeline every 12 hours."""
    print(f"\n{'='*60}")
    print(f"  YouTube Automation — 12-Hour Schedule")
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


def prepare_meta_job_only() -> str:
    """Generate or resume Channel 3's Meta AI job without rendering/uploading."""
    channel = next(
        (item for item in CHANNELS if item.get("media_source") == "meta_ai_browser"),
        None,
    )
    if channel is None:
        raise RuntimeError("No Meta AI browser channel is configured.")

    active = find_active_job(channel["id"])
    if active:
        manifest, job_dir = active
        print(f"[MetaAI] Resuming job: {manifest['job_id']}")
    else:
        used_scripts = _load_used_scripts()
        used_prompts = _load_used_prompts()
        story = _generate_unique_script(channel, used_scripts, used_prompts)
        manifest, job_dir = create_job(channel, story)
        print(f"[MetaAI] Created job: {manifest['job_id']}")

    print(f"[MetaAI] Video prompt batch: {job_dir / 'meta_prompts.txt'}")
    print("[MetaAI] The scheduled browser runner will render this job automatically.")
    return str(job_dir)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YouTube Multi-Channel Automation")
    parser.add_argument("--once", action="store_true", help="Run once and exit (no schedule)")
    parser.add_argument(
        "--prepare-meta",
        action="store_true",
        help="Create/resume Channel 3's Meta AI prompt job only",
    )
    parser.add_argument(
        "--meta-login",
        action="store_true",
        help="Open the persistent Chrome profile for the one-time Meta login",
    )
    parser.add_argument(
        "--channel",
        action="append",
        choices=["1", "2", "3", "4"],
        help="With --once, process only this channel (repeatable)",
    )
    args = parser.parse_args()

    if args.meta_login:
        bootstrap_meta_login()
    elif args.prepare_meta:
        prepare_meta_job_only()
    elif args.once:
        selected = {f"channel_{value}" for value in args.channel} if args.channel else None
        if not run_daily_batch(selected):
            raise SystemExit(1)
    else:
        if args.channel:
            parser.error("--channel requires --once")
        run_scheduled()
