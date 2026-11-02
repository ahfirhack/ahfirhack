"""Build no-upload previews with the same hybrid routing as ``main.py``.

Examples:
    python test_pipeline.py 3
    python test_pipeline.py 1 2 4
    python test_pipeline.py all
"""

import argparse
import atexit
import datetime
import glob
import os
import shutil
import tempfile

from config import CHANNELS, LEGACY_SHORT_DURATION_TARGET, OUTPUT_DIR, TEMP_DIR
from modules import video_fetcher as video_fetcher_module
from modules.legacy_video_assembler import assemble_video
from modules.meta_ai_generator import create_job, ensure_rendered_clips, find_active_job
from modules.music_fetcher import generate_background_music
from modules.prompt_reserve import peek_prompt
from modules.script_generator import generate_script
from modules.video_assembler import assemble_meta_short
from modules.video_fetcher import fetch_video_clips
from modules.voiceover import generate_voiceover


# Preview downloads must not consume production footage-dedup state.
_PREVIEW_STATE_DIR = tempfile.mkdtemp(prefix="youtube-preview-")
video_fetcher_module.USED_VIDEOS_FILE = os.path.join(
    _PREVIEW_STATE_DIR, "used_videos.json"
)
atexit.register(shutil.rmtree, _PREVIEW_STATE_DIR, ignore_errors=True)


def _reset_channel_preview(channel_id: str) -> str:
    """Keep one replaceable preview per channel."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_name = f"PREVIEW_{channel_id}.mp4"
    for pattern in (f"TEST_{channel_id}_*.mp4", f"FIXED_PREVIEW_{channel_id}.mp4", output_name):
        for candidate in glob.glob(os.path.join(OUTPUT_DIR, pattern)):
            if os.path.isfile(candidate):
                os.remove(candidate)
    return output_name


def _preview_story(channel: dict) -> dict:
    reserve_db = channel.get("prompt_reserve_db")
    if reserve_db:
        story = peek_prompt(reserve_db, channel["id"])
        if story is not None:
            return story
    return generate_script(
        channel["niche"],
        allow_fallback=channel.get(
            "allow_curated_fallback",
            not channel.get("strict_ai_prompts", False),
        ),
    )


def _test_meta_channel(channel: dict, output_filename: str,
                       *, isolated_browser: bool = False) -> str:
    existing = find_active_job(channel["id"])
    if existing:
        manifest, directory = existing
    else:
        manifest, directory = create_job(channel, _preview_story(channel))
    clips = ensure_rendered_clips(
        manifest, directory, isolated_browser=isolated_browser,
    )
    return assemble_meta_short(
        clip_paths=clips,
        output_filename=output_filename,
        continuity_dir=directory / "continuity",
        scene_seconds=10,
    )


def _test_legacy_channel(channel: dict, output_filename: str) -> str:
    story = _preview_story(channel)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = channel["id"]
    print(
        f"  Title: {story['title']} | {len(story['script'].split())}w | "
        f"Query: {story.get('search_query', story['title'])}"
    )

    voice_path = os.path.join(TEMP_DIR, f"{safe_name}_{timestamp}_voice.mp3")
    generate_voiceover(
        story["script"], voice_path, channel_id=channel["id"],
        strict_voice=channel.get("strict_voice", False),
        voice_provider=channel.get("voice_provider"),
        require_timestamps=channel.get("require_word_timestamps", False),
    )
    music_path = os.path.join(TEMP_DIR, f"{safe_name}_{timestamp}_music.mp3")
    generate_background_music(
        channel.get("music_mood", "relaxing"),
        LEGACY_SHORT_DURATION_TARGET, music_path,
    )
    clips = fetch_video_clips(
        query=story.get("search_query", story["title"]), num_clips=3,
        script=story["script"], niche_keywords=channel.get("keywords", []),
        visual_queries=story.get("visual_queries", []),
        source_url=story.get("source_url", ""),
    )
    return assemble_video(
        clip_paths=clips, audio_path=voice_path, script=story["script"],
        output_filename=output_filename, channel_name=channel["name"],
        music_path=music_path,
        target_duration=channel.get("target_duration"),
        end_screen_duration=channel.get("end_screen_duration"),
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


def test_channel(channel: dict, *, isolated_browser: bool = False) -> str:
    output_filename = _reset_channel_preview(channel["id"])
    print(f"\n  PREVIEW: {channel['name']} ({channel['media_source']})\n")
    if channel.get("media_source") == "meta_ai_browser":
        return _test_meta_channel(
            channel, output_filename, isolated_browser=isolated_browser,
        )
    return _test_legacy_channel(channel, output_filename)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hybrid video preview; never uploads")
    parser.add_argument("channels", nargs="*", choices=("1", "2", "3", "4", "all"))
    # Retained for command compatibility. There is only one Meta channel now.
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args(argv)
    wanted = set(args.channels)
    channels = CHANNELS if not wanted or "all" in wanted else [
        channel for channel in CHANNELS
        if channel["id"] in {f"channel_{slot}" for slot in wanted}
    ]

    failures = []
    for channel in channels:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)
        try:
            output = test_channel(channel, isolated_browser=False)
            print(f"[Preview] {channel['name']} -> {output}")
        except Exception as error:
            failures.append((channel["name"], str(error)))
            print(f"[Preview] FAIL {channel['name']}: {error}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
