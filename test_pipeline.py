"""
test_pipeline.py — Full pipeline WITHOUT uploading. Preview in output_videos/.
Usage: python test_pipeline.py         # all channels
       python test_pipeline.py 2       # channel_2 only
"""
import atexit, glob, os, sys, time, datetime, shutil, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from config import CHANNELS, TEMP_DIR, OUTPUT_DIR, SHORT_DURATION_TARGET
from modules.script_generator import generate_script
from modules.voiceover import generate_voiceover
from modules.music_fetcher import generate_background_music
from modules.video_fetcher import fetch_video_clips
from modules import video_fetcher as video_fetcher_module
from modules.video_assembler import assemble_video
from modules.meta_ai_generator import (
    create_job,
    ensure_rendered_clips,
    find_active_job,
)
from modules.prompt_reserve import peek_prompt

# Preview media history is isolated from production deduplication state. A test
# can download real assets without making a later scheduled episode think they
# have already been published.
_PREVIEW_STATE_DIR = tempfile.mkdtemp(prefix="youtube-preview-")
video_fetcher_module.USED_VIDEOS_FILE = os.path.join(
    _PREVIEW_STATE_DIR, "used_videos.json"
)
atexit.register(shutil.rmtree, _PREVIEW_STATE_DIR, ignore_errors=True)


def _reset_channel_preview(channel_id: str) -> str:
    """Keep exactly one replaceable no-upload preview per channel."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_name = f"PREVIEW_{channel_id}.mp4"
    patterns = (
        f"TEST_{channel_id}_*.mp4",
        f"FIXED_PREVIEW_{channel_id}.mp4",
        output_name,
    )
    for pattern in patterns:
        for candidate in glob.glob(os.path.join(OUTPUT_DIR, pattern)):
            if os.path.isfile(candidate):
                os.remove(candidate)
                print(f"  Removed old local preview: {candidate}")
    return output_name

def test_channel(ch):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sn = ch["id"].replace(" ", "_")
    output_filename = _reset_channel_preview(sn)
    uv = ch.get("use_voice", True)
    use_music = ch.get("use_music", True)
    native_audio = ch.get("native_clip_audio", False)
    mm = ch.get("music_mood", "relaxing")

    print(f"\n  TEST: {ch['name']} | Voice: {uv} | Music: {use_music}\n")

    active_meta_job = find_active_job(ch["id"]) if ch.get("media_source") == "meta_ai_browser" else None
    if active_meta_job:
        manifest, meta_job_dir = active_meta_job
        data = manifest["story"]
    else:
        # A preview must not burn provider quota or mutate/consume the reserve.
        # AI-provider health has its own workflow; this test exercises every
        # downstream media, narration, assembly, and continuity stage.
        data = None
        reserve_db = ch.get("prompt_reserve_db")
        if reserve_db:
            data = peek_prompt(reserve_db, ch["id"])
        if data is None:
            data = generate_script(
                ch["niche"],
                allow_fallback=ch.get(
                    "allow_curated_fallback",
                    not ch.get("strict_ai_prompts", False),
                ),
            )
        manifest = meta_job_dir = None
    print(f"  Title: {data['title']} | {len(data['script'].split())}w | Query: {data['search_query']}")

    # Generate voiceover
    voice_path = None
    if uv:
        voice_path = os.path.join(TEMP_DIR, f"{sn}_{ts}_voice.mp3")
        generate_voiceover(
            data["script"],
            voice_path,
            channel_id=ch["id"],
            strict_voice=ch.get("strict_voice", False),
            voice_provider=ch.get("voice_provider"),
            require_timestamps=ch.get("require_word_timestamps", False),
        )

    # Generate background music
    music_path = None
    if use_music:
        music_path = os.path.join(TEMP_DIR, f"{sn}_{ts}_music.mp3")
        generate_background_music(mm, SHORT_DURATION_TARGET, music_path)

    # Fetch clips
    if ch.get("media_source") == "meta_ai_browser":
        if manifest is None:
            manifest, meta_job_dir = create_job(ch, data)
        clips = ensure_rendered_clips(manifest, meta_job_dir)
    else:
        clip_count = 3 if ch.get("align_visual_beats", False) else 6
        clips = fetch_video_clips(query=data["search_query"], num_clips=clip_count,
                                  script=data["script"], niche_keywords=ch.get("keywords", []),
                                  visual_queries=data.get("visual_queries", []),
                                  source_url=data.get("source_url", ""))

    # Assemble video with voice + music
    audio_for_video = None if native_audio else (voice_path if voice_path else music_path)
    path = assemble_video(
        clip_paths=clips,
        audio_path=audio_for_video,
        script=data["script"],
        output_filename=output_filename,
        channel_name=ch["name"],
        music_path=music_path if voice_path else None,
        target_duration=ch.get("target_duration"),
        end_screen_duration=ch.get("end_screen_duration"),
        seamless_scenes=ch.get("seamless_scenes", False),
        native_clip_audio=native_audio,
        show_overlays=ch.get("show_overlays", True),
        opening_style=ch.get("opening_style", "default"),
        hook_sfx=ch.get("hook_sfx"),
        hook_overlay=data.get("hook_overlay", ""),
        hook_accent=data.get("hook_accent", ""),
        evidence_label=data.get("evidence_label", ""),
        require_visuals=ch.get("require_visuals", False),
        align_visual_beats=ch.get("align_visual_beats", False),
        reject_synthetic_visuals=ch.get("reject_synthetic_visuals", False),
        require_word_timestamps=ch.get("require_word_timestamps", False),
    )
    print(f"\n  OUTPUT: {path}\n")
    return path

if __name__ == "__main__":
    ids = {f"channel_{a}" for a in sys.argv[1:]} if len(sys.argv) > 1 else set()
    chs = [c for c in CHANNELS if c["id"] in ids] if ids else CHANNELS
    failures = []
    for ch in chs:
        if os.path.exists(TEMP_DIR): shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)
        try:
            test_channel(ch)
        except Exception as error:
            failures.append((ch["name"], str(error)))
            print(f"  FAIL: {ch['name']}: {error}")
    if failures:
        print("\n  NO-UPLOAD TEST FAILURES:")
        for name, error in failures:
            print(f"  - {name}: {error}")
        raise SystemExit(1)
