"""
test_pipeline.py — Full pipeline WITHOUT uploading. Preview in output_videos/.
Usage: python test_pipeline.py         # all channels
       python test_pipeline.py 2       # channel_2 only
"""
import os, sys, time, datetime, shutil
sys.path.insert(0, os.path.dirname(__file__))
from config import CHANNELS, TEMP_DIR, OUTPUT_DIR, SHORT_DURATION_TARGET
from modules.script_generator import generate_script
from modules.voiceover import generate_voiceover
from modules.music_fetcher import generate_background_music
from modules.video_fetcher import fetch_video_clips
from modules.video_assembler import assemble_video

def test_channel(ch):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sn = ch["id"].replace(" ", "_")
    uv = ch.get("use_voice", True)
    mm = ch.get("music_mood", "relaxing")

    print(f"\n  TEST: {ch['name']} | Voice: {uv} | Music: {mm}\n")

    data = generate_script(ch["niche"])
    print(f"  Title: {data['title']} | {len(data['script'].split())}w | Query: {data['search_query']}")

    # Generate voiceover
    voice_path = None
    if uv:
        voice_path = os.path.join(TEMP_DIR, f"{sn}_{ts}_voice.mp3")
        voice_style = ch.get("hook_style", "default")
        generate_voiceover(data["script"], voice_path, voice_style=voice_style)

    # Generate background music
    music_path = os.path.join(TEMP_DIR, f"{sn}_{ts}_music.mp3")
    generate_background_music(mm, SHORT_DURATION_TARGET, music_path)

    # Fetch clips
    clips = fetch_video_clips(query=data["search_query"], num_clips=6,
                               script=data["script"], niche_keywords=ch.get("keywords", []))

    # Assemble video with voice + music
    audio_for_video = voice_path if voice_path else music_path
    path = assemble_video(
        clip_paths=clips,
        audio_path=audio_for_video,
        script=data["script"],
        output_filename=f"TEST_{sn}_{ts}.mp4",
        channel_name=ch["name"],
        music_path=music_path if voice_path else None,
    )
    print(f"\n  OUTPUT: {path}\n")
    return path

if __name__ == "__main__":
    ids = {f"channel_{a}" for a in sys.argv[1:]} if len(sys.argv) > 1 else set()
    chs = [c for c in CHANNELS if c["id"] in ids] if ids else CHANNELS
    for ch in chs:
        if os.path.exists(TEMP_DIR): shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)
        try: test_channel(ch)
        except Exception as e: print(f"  FAIL: {ch['name']}: {e}")
