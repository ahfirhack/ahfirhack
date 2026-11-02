"""Hybrid four-channel YouTube Shorts pipeline.

Channel 3 keeps the current five-scene Meta/native-audio workflow. Channels
1, 2, and 4 use the pre-Meta sourced-media pipeline with locked narration,
background music, synchronized captions, and visual-quality safeguards.
"""

import os
import sys
import time
import datetime
import shutil
import hashlib
import json
import threading

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    CHANNELS, VIDEOS_PER_CHANNEL_PER_DAY, TEMP_DIR, OUTPUT_DIR,
    SHORT_DURATION_TARGET, USED_SCRIPTS_FILE, USED_PROMPTS_FILE,
    UPLOAD_INTERVAL_SECONDS, LEGACY_SHORT_DURATION_TARGET,
)
from modules.script_generator import ScriptGenerationError, generate_script
from modules.video_assembler import assemble_meta_short
from modules.legacy_video_assembler import assemble_video
from modules.music_fetcher import generate_background_music
from modules.video_fetcher import fetch_video_clips
from modules.voiceover import generate_voiceover
from modules.uploader import upload_video
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

# Script/prompt dedup uses two shared JSON files across channels. Protect both
# the in-memory sets and file writes while rendering happens in parallel.
_STATE_LOCK = threading.RLock()
# Three concurrent 2K FFmpeg encoders can exhaust a small GitHub runner. Only
# assembly is serialized; Meta generations remain concurrent.
_ASSEMBLY_LOCK = threading.Lock()


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
def _process_meta_video(
    channel: dict,
    video_index: int,
    used_scripts: set,
    used_prompts: set,
    *,
    isolated_browser: bool = False,
):
    """Fail-closed 5x10s Meta pipeline used only by Channel 3."""
    channel_id = channel["id"]
    channel_name = channel["name"]
    if channel.get("media_source") != "meta_ai_browser":
        raise RuntimeError(f"Meta pipeline violation: {channel_name} is not Meta AI")
    required = {
        "use_voice": False,
        "use_music": False,
        "native_clip_audio": True,
        "seamless_scenes": True,
        "show_overlays": False,
    }
    for key, expected in required.items():
        if channel.get(key) is not expected:
            raise RuntimeError(f"Meta pipeline violation: {channel_name}.{key}")

    print(f"\n{'='*60}")
    print(f"  {channel_name} — Meta AI only | 5 x 10 seconds | native audio")
    print(f"{'='*60}\n")
    # Picking a unique script and reserving its identity must be atomic
    # across all four channels. Different channels keep separate job dirs.
    with _STATE_LOCK:
        active = find_active_job(channel_id)
        if active:
            manifest, job_dir = active
            story = manifest["story"]
            print(f"[1/4] Resuming unfinished Meta job: {manifest['job_id']}")
        else:
            print("[1/4] Choosing a unique story...")
            story = _generate_unique_script(channel, used_scripts, used_prompts)
            manifest, job_dir = create_job(channel, story)

    print(f"  Title: {story['title']}")
    print("[2/4] Generating five Meta AI video scenes with frame handoffs...")
    clips = ensure_rendered_clips(
        manifest, job_dir, isolated_browser=isolated_browser,
    )
    if len(clips) != 5 or len(manifest["scenes"]) != 5:
        raise RuntimeError("Meta-only policy violation: expected exactly five scenes")
    if manifest.get("render_backend") not in (None, "meta_ai"):
        raise RuntimeError("Meta-only policy violation: non-Meta scene backend")

    print("[3/4] Stitching five 10s scenes, no gaps, no other media or audio...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{channel_id}_{timestamp}.mp4"
    with _ASSEMBLY_LOCK:
        video_path = assemble_meta_short(
            clip_paths=clips,
            output_filename=output_file,
            continuity_dir=job_dir / "continuity",
            scene_seconds=10,
        )
    print("[4/4] Uploading 50-second YouTube Short...")
    video_id = upload_video(
        video_path=video_path,
        title=f"{story['title']} #Shorts"[:100],
        tags=list(story.get("tags", [])) + ["Shorts"],
        channel_config=channel,
        script=story["script"],
        source_url=story.get("source_url", ""),
        media_credits=[],
    )
    if not video_id:
        raise RuntimeError("YouTube did not confirm an upload ID")
    mark_job_complete(job_dir, video_id)

    reserve_prompt_id = story.get("_reserve_prompt_id")
    reserve_db = channel.get("prompt_reserve_db")
    if reserve_prompt_id is not None and reserve_db:
        with _STATE_LOCK:
            consume_prompt(reserve_db, int(reserve_prompt_id))
            used_scripts.add(_script_hash(story))
            _save_used_scripts(used_scripts)
            used_prompts.update(_prompt_hashes(channel_id, story))
            _save_used_prompts(used_prompts)
            print(f"[ScriptGen] {available_prompt_count(reserve_db, channel_id)} queued prompts remain")
    print(f"\n  {channel_name} -> https://youtube.com/shorts/{video_id}\n")
    return video_id


def _legacy_visual_queries(story: dict) -> list[str]:
    """Return the old hook/escalation/payoff search plan when available."""
    configured = story.get("visual_queries")
    if isinstance(configured, list):
        queries = [str(value).strip() for value in configured if str(value).strip()]
        if len(queries) >= 3:
            return queries[:3]

    primary = str(story.get("search_query") or story.get("title") or "").strip()
    rows = story.get("scene_plan")
    if isinstance(rows, list):
        queries = []
        # The current generator emits five Meta scenes. For the restored stock
        # pipeline, the first three actions become the classic three visual beats.
        for row in rows[:3]:
            action = str(row.get("action", "")).strip() if isinstance(row, dict) else ""
            query = " ".join(part for part in (primary, action) if part).strip()
            if query:
                queries.append(query)
        if len(queries) == 3:
            return queries
    # video_fetcher will derive three queries from the title/script.
    return []


def _consume_uploaded_reserve(channel: dict, story: dict, used_scripts: set,
                              used_prompts: set) -> None:
    """Delete a reserved prompt only after YouTube confirmed the upload."""
    reserve_prompt_id = story.get("_reserve_prompt_id")
    reserve_db = channel.get("prompt_reserve_db")
    if reserve_prompt_id is None or not reserve_db:
        return
    with _STATE_LOCK:
        consume_prompt(reserve_db, int(reserve_prompt_id))
        used_scripts.add(_script_hash(story))
        _save_used_scripts(used_scripts)
        used_prompts.update(_prompt_hashes(channel["id"], story))
        _save_used_prompts(used_prompts)
        print(
            f"[ScriptGen] Consumed SQLite prompt {reserve_prompt_id}; "
            f"{available_prompt_count(reserve_db, channel['id'])} prompts remain"
        )


def _process_legacy_video(
    channel: dict,
    video_index: int,
    used_scripts: set,
    used_prompts: set,
):
    """Run the pre-all-Meta pipeline for Channels 1, 2, and 4."""
    if channel.get("media_source", "stock") == "meta_ai_browser":
        raise RuntimeError(f"Legacy pipeline violation: {channel['name']} is Meta AI")
    if not channel.get("use_voice") or not channel.get("use_music"):
        raise RuntimeError(
            f"Legacy pipeline requires locked narration and music: {channel['name']}"
        )

    channel_id = channel["id"]
    channel_name = channel["name"]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = channel_id.replace(" ", "_")

    print(f"\n{'='*60}")
    print(f"  {channel_name} — sourced visuals | locked voice + music")
    print(f"  Video {video_index + 1}/{VIDEOS_PER_CHANNEL_PER_DAY}")
    print(f"{'='*60}\n")

    print("[1/6] Choosing a unique story...")
    with _STATE_LOCK:
        story = _generate_unique_script(channel, used_scripts, used_prompts)
    title = story["title"]
    script = story["script"]
    search_query = story.get("search_query") or title
    print(f"  Title: {title}")

    print("[2/6] Generating locked narration...")
    voice_path = os.path.join(TEMP_DIR, f"{safe_name}_{timestamp}_voice.mp3")
    generate_voiceover(
        script,
        voice_path,
        channel_id=channel_id,
        strict_voice=channel.get("strict_voice", False),
        voice_provider=channel.get("voice_provider"),
        require_timestamps=channel.get("require_word_timestamps", False),
    )

    print("[3/6] Preparing background music...")
    music_path = os.path.join(TEMP_DIR, f"{safe_name}_{timestamp}_music.mp3")
    generate_background_music(
        channel.get("music_mood", "relaxing"),
        LEGACY_SHORT_DURATION_TARGET,
        music_path,
    )

    print("[4/6] Fetching three topic-matched visual beats...")
    clips, media_credits = fetch_video_clips(
        query=search_query,
        num_clips=3,
        script=script,
        niche_keywords=channel.get("keywords", []),
        visual_queries=_legacy_visual_queries(story),
        include_attributions=True,
        source_url=story.get("source_url", ""),
    )

    print("[5/6] Assembling the restored narration-timed Short...")
    output_file = f"{safe_name}_{timestamp}.mp4"
    video_path = assemble_video(
        clip_paths=clips,
        audio_path=voice_path,
        script=script,
        output_filename=output_file,
        channel_name=channel_name,
        music_path=music_path,
        # The old assembler follows the narration length (plus its short end
        # screen). The 30-second constant sizes music; it must not cut speech.
        target_duration=channel.get("target_duration"),
        end_screen_duration=channel.get("end_screen_duration"),
        seamless_scenes=False,
        native_clip_audio=False,
        show_overlays=channel.get("show_overlays", True),
        opening_style=channel.get("opening_style", "default"),
        hook_sfx=channel.get("hook_sfx"),
        hook_overlay=story.get("hook_overlay", ""),
        hook_accent=story.get("hook_accent", ""),
        evidence_label=story.get("evidence_label", ""),
        require_visuals=channel.get("require_visuals", False),
        align_visual_beats=channel.get("align_visual_beats", False),
        reject_synthetic_visuals=channel.get("reject_synthetic_visuals", False),
        require_word_timestamps=channel.get("require_word_timestamps", False),
    )

    print("[6/6] Uploading as a YouTube Short...")
    video_id = upload_video(
        video_path=video_path,
        title=f"{title} #Shorts"[:100],
        tags=list(story.get("tags", [])) + ["Shorts"],
        channel_config=channel,
        script=script,
        source_url=story.get("source_url", ""),
        media_credits=media_credits,
    )
    if not video_id:
        raise RuntimeError("YouTube did not confirm an upload ID")
    _consume_uploaded_reserve(channel, story, used_scripts, used_prompts)
    print(f"\n  {channel_name} -> https://youtube.com/shorts/{video_id}\n")
    return video_id


def process_video(
    channel: dict,
    video_index: int,
    used_scripts: set,
    used_prompts: set,
    *,
    isolated_browser: bool = False,
):
    """Route only Channel 3 to Meta; restore the legacy flow for the rest."""
    if channel.get("media_source") == "meta_ai_browser":
        return _process_meta_video(
            channel, video_index, used_scripts, used_prompts,
            isolated_browser=isolated_browser,
        )
    return _process_legacy_video(channel, video_index, used_scripts, used_prompts)


# ── Scheduled batch ──────────────────────────────────────────────
def _worker_count(requested: int | None, channel_count: int) -> int:
    """Bound browser workers to the number of selected Meta channels."""
    value = int(os.getenv("META_CHANNEL_WORKERS", "1")) if requested is None else requested
    if not 1 <= value <= 3:
        raise ValueError("--workers / META_CHANNEL_WORKERS must be 1, 2, or 3")
    return min(value, channel_count)


def _process_channel_worker(channel: dict, used_scripts: set, used_prompts: set,
                            *, isolated_browser: bool) -> dict:
    """Run one channel and convert its error into a batch result."""
    try:
        vid = process_video(
            channel, 0, used_scripts, used_prompts,
            isolated_browser=isolated_browser,
        )
        return {"ch": channel["name"], "vid": vid, "ok": True}
    except MetaAIAutomationError as error:
        print(f"\n  META AI ERROR {channel['name']}: {error}", flush=True)
    except Exception as error:
        print(f"\n  ERROR {channel['name']}: {error}", flush=True)
    return {"ch": channel["name"], "vid": None, "ok": False}


def run_channel_batch(channel_ids: set[str] | None = None,
                      *, workers: int | None = None):
    """Run one video per channel using the restored hybrid routing.

    The sourced-media modules use shared temporary filenames, so channels run
    sequentially. Only Channel 3 opens a Meta browser session.
    """
    now = datetime.datetime.now()
    channels = [
        channel for channel in CHANNELS
        if not channel_ids or channel["id"] in channel_ids
    ]
    if not channels:
        raise ValueError("No selected channel exists")
    meta_count = sum(
        channel.get("media_source") == "meta_ai_browser" for channel in channels
    )
    meta_workers = _worker_count(workers, meta_count)
    print(f"\n  YouTube Automation — {now.strftime('%Y-%m-%d %H:%M %A')}")
    print(f"  Channels: {len(channels)} | Meta browser workers: {meta_workers} | "
          f"Videos per run: {len(channels)}\n")

    used_scripts = _load_used_scripts()
    used_prompts = _load_used_prompts()
    results = []
    for channel in channels:
        # The legacy assembler/fetcher use TEMP_DIR working names. Cleaning it
        # between sequential channels prevents cross-channel media reuse.
        clean_temp()
        results.append(_process_channel_worker(
            channel, used_scripts, used_prompts, isolated_browser=False,
        ))

    ok = sum(bool(row["ok"]) for row in results)
    print(f"\n{'='*60}")
    print(f"  DONE: {ok}/{len(results)} uploaded")
    for row in sorted(results, key=lambda r: r["ch"]):
        status = "OK" if row["ok"] else "FAIL"
        print(f"  [{status}] {row['ch']} — {row.get('vid') or 'error'}")
    print(f"{'='*60}\n")
    return bool(results) and ok == len(results)


# ── 6-hour schedule loop ──────────────────────────────────────
def run_scheduled(*, workers: int | None = None):
    """Run the pipeline every 6 hours when launched as a local daemon."""
    print(f"\n{'='*60}")
    print(f"  YouTube Automation — 6-Hour Schedule")
    print(f"  Upload interval: {UPLOAD_INTERVAL_SECONDS / 3600} hours")
    print(f"{'='*60}\n")

    while True:
        try:
            run_channel_batch(workers=workers)

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


def prepare_meta_job_only(channel_id: str = "channel_3") -> str:
    """Generate or resume the selected channel's Meta AI job."""
    channel = next(
        (item for item in CHANNELS if item["id"] == channel_id),
        None,
    )
    if channel is None or channel.get("media_source") != "meta_ai_browser":
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
        help="Create/resume a channel's five-scene Meta AI prompt job",
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
        help="With --once or --prepare-meta, select a channel (repeatable with --once)",
    )
    parser.add_argument(
        "--workers", type=int, default=None, choices=(1, 2, 3),
        help="Maximum Meta browser workers (the hybrid pipeline currently uses one)",
    )
    args = parser.parse_args()

    if args.meta_login:
        bootstrap_meta_login()
    elif args.prepare_meta:
        prepare_meta_job_only(f"channel_{args.channel[0]}" if args.channel else "channel_3")
    elif args.once:
        selected = {f"channel_{value}" for value in args.channel} if args.channel else None
        if not run_channel_batch(selected, workers=args.workers):
            raise SystemExit(1)
    else:
        if args.channel:
            parser.error("--channel requires --once")
        run_scheduled(workers=args.workers)
