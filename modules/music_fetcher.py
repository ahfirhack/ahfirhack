"""
music_fetcher.py — Real music from Jamendo API, with generated fallback.
Tries Jamendo first (CC-licensed real music), then falls back to ffmpeg synthesis.
Moods: wisdom, mysterious, suspense, upbeat, playful, relaxing, cinematic.
Cached in music_cache/ for reuse across runs.
"""

import os
import subprocess
import random
import requests
from config import MUSIC_CACHE_DIR, JAMENDO_CLIENT_ID

MAX_CACHED_PER_MOOD = 8

# Jamendo tag mapping per mood
JAMENDO_MOOD_TAGS = {
    "wisdom":     "ambient meditation",
    "mysterious": "dark ambient",
    "suspense":   "suspense cinematic",
    "upbeat":     "upbeat positive",
    "playful":    "playful fun",
    "relaxing":   "ambient relaxing",
    "cinematic":  "cinematic dramatic",
}


def _ffmpeg_gen(args: list, output: str, label: str = ""):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + args + [output]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Music [{label}] failed:\n{result.stderr}")


def _get_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ── Real Music: Jamendo ────────────────────────────────────────
def _fetch_jamendo(mood: str, duration: float, out: str) -> bool:
    """Download a CC-licensed track from Jamendo. Returns True on success."""
    if not JAMENDO_CLIENT_ID:
        return False

    tags = JAMENDO_MOOD_TAGS.get(mood, "ambient")
    try:
        resp = requests.get(
            "https://api.jamendo.com/v3.0/tracks/",
            params={
                "client_id": JAMENDO_CLIENT_ID,
                "format": "json",
                "limit": "20",
                "tags": tags,
                "audioformat": "mp32",
                "order": "popularity_total",
            },
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return False
    except Exception as e:
        print(f"[Music/Jamendo] API error: {e}")
        return False

    random.shuffle(results[:10])
    for track in results[:5]:
        audio_url = track.get("audiodownload") or track.get("audio")
        if not audio_url:
            continue
        tmp = out + ".tmp.mp3"
        try:
            r = requests.get(audio_url, stream=True, timeout=60)
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            dl_dur = _get_duration(tmp)
            if dl_dur >= duration:
                _ffmpeg_gen(["-i", tmp, "-t", str(duration), "-c", "copy"], out, "trim_jamendo")
                os.remove(tmp)
                print(f"[Music/Jamendo] '{track.get('name', 'track')}' ({dl_dur:.0f}s)")
                return True
            elif dl_dur > 10:
                loop_count = int(duration / dl_dur) + 2
                _ffmpeg_gen(["-stream_loop", str(loop_count), "-i", tmp,
                             "-t", str(duration), "-c", "copy"], out, "loop_jamendo")
                os.remove(tmp)
                print(f"[Music/Jamendo] Looped '{track.get('name', 'track')}' x{loop_count}")
                return True
        except Exception as e:
            print(f"[Music/Jamendo] Download failed: {e}")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    return False


# ── Upbeat — bright major chords + subtle rhythm (Life Hacks) ──
def _gen_upbeat(dur: float, out: str):
    base = random.choice([261.63, 293.66, 329.63, 349.23])  # C4-F4
    third = base * 1.25
    fifth = base * 1.5
    octave = base * 2
    echo_d = random.choice(["30|60", "35|70", "40|80"])
    _ffmpeg_gen(
        ["-f", "lavfi", "-i", f"sine=f={base}:d={dur},volume=0.12",
         "-f", "lavfi", "-i", f"sine=f={third}:d={dur},volume=0.08",
         "-f", "lavfi", "-i", f"sine=f={fifth}:d={dur},volume=0.07",
         "-f", "lavfi", "-i", f"sine=f={octave}:d={dur},volume=0.04",
         "-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=pink:r=44100,highpass=f=2000,lowpass=f=6000,volume=0.05",
         "-filter_complex",
         f"[0][1][2][3][4]amix=inputs=5:duration=first,"
         f"aecho=0.6:0.5:{echo_d}:0.3|0.2,"
         f"equalizer=f=400:t=q:w=2:g=3,"
         f"volume=2.0"],
        out, "upbeat")


# ── Playful — bouncy, light, fun feel (Funny Animals) ─────────
def _gen_playful(dur: float, out: str):
    base = random.choice([329.63, 392.00, 440.00, 523.25])  # E4-C5
    fifth = base * 1.5
    high = base * 2
    low = base * 0.5
    echo_d = random.choice(["20|40", "25|50", "30|60"])
    _ffmpeg_gen(
        ["-f", "lavfi", "-i", f"sine=f={base}:d={dur},volume=0.10",
         "-f", "lavfi", "-i", f"sine=f={fifth}:d={dur},volume=0.07",
         "-f", "lavfi", "-i", f"sine=f={high}:d={dur},volume=0.05",
         "-f", "lavfi", "-i", f"sine=f={low}:d={dur},volume=0.06",
         "-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=pink:r=44100,highpass=f=800,lowpass=f=4000,volume=0.04",
         "-filter_complex",
         f"[0][1][2][3][4]amix=inputs=5:duration=first,"
         f"aecho=0.5:0.4:{echo_d}:0.25|0.15,"
         f"tremolo=f=4:d=0.3,"
         f"equalizer=f=1000:t=q:w=1:g=2,"
         f"volume=2.0"],
        out, "playful")


# ── Relaxing — warm ambient pad, slow (Self Improvement) ──────
def _gen_relaxing(dur: float, out: str):
    base = random.choice([174.61, 196.00, 220.00, 246.94])  # F3-B3
    fifth = base * 1.5
    octave = base * 2
    echo_d = random.choice(["120|240", "150|300", "180|360"])
    _ffmpeg_gen(
        ["-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=pink:r=44100,highpass=f=80,lowpass=f=500,volume=0.20",
         "-f", "lavfi", "-i", f"sine=f={base}:d={dur},volume=0.10",
         "-f", "lavfi", "-i", f"sine=f={fifth}:d={dur},volume=0.06",
         "-f", "lavfi", "-i", f"sine=f={octave}:d={dur},volume=0.04",
         "-filter_complex",
         f"[0][1][2][3]amix=inputs=4:duration=first,"
         f"aecho=0.8:0.88:{echo_d}:0.5|0.3,"
         f"lowpass=f=1500,"
         f"volume=1.8"],
        out, "relaxing")


# ── Wisdom — peaceful, meditative, ethereal (Wisdom Quotes) ──
def _gen_wisdom(dur: float, out: str):
    base = random.choice([174.61, 196.00, 220.00, 246.94])  # F3-B3
    fifth = base * 1.5
    octave = base * 2
    third = base * 1.25
    echo_d = random.choice(["180|360", "200|400", "220|440"])
    _ffmpeg_gen(
        ["-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=pink:r=44100,highpass=f=60,lowpass=f=400,volume=0.18",
         "-f", "lavfi", "-i", f"sine=f={base}:d={dur},volume=0.08",
         "-f", "lavfi", "-i", f"sine=f={fifth}:d={dur},volume=0.05",
         "-f", "lavfi", "-i", f"sine=f={octave}:d={dur},volume=0.03",
         "-f", "lavfi", "-i", f"sine=f={third}:d={dur},volume=0.04",
         "-filter_complex",
         f"[0][1][2][3][4]amix=inputs=5:duration=first,"
         f"aecho=0.85:0.9:{echo_d}:0.4|0.25,"
         f"lowpass=f=1200,"
         f"volume=1.6"],
        out, "wisdom")


# ── Mysterious — eerie, suspenseful, dark (Weird Facts) ──
def _gen_mysterious(dur: float, out: str):
    base = random.choice([130.81, 146.83, 155.56, 164.81])  # C3-E3
    minor_third = base * 1.2
    tritone = base * 1.414
    sub = base * 0.5
    echo_d = random.choice(["250|500", "300|600", "350|700"])
    _ffmpeg_gen(
        ["-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=brown:r=44100,highpass=f=30,lowpass=f=300,volume=0.20",
         "-f", "lavfi", "-i", f"sine=f={base}:d={dur},volume=0.08",
         "-f", "lavfi", "-i", f"sine=f={minor_third}:d={dur},volume=0.04",
         "-f", "lavfi", "-i", f"sine=f={tritone}:d={dur},volume=0.03",
         "-f", "lavfi", "-i", f"sine=f={sub}:d={dur},volume=0.06",
         "-filter_complex",
         f"[0][1][2][3][4]amix=inputs=5:duration=first,"
         f"aecho=0.9:0.95:{echo_d}:0.5|0.35,"
         f"lowpass=f=800,"
         f"volume=1.5"],
        out, "mysterious")


# ── Suspense — tense, building, dramatic (People Stories) ──
def _gen_suspense(dur: float, out: str):
    base = random.choice([110.00, 116.54, 123.47, 130.81])  # A2-C3
    minor_third = base * 1.2
    fifth = base * 1.5
    sub = base * 0.5
    echo_d = random.choice(["150|300", "180|360", "200|400"])
    _ffmpeg_gen(
        ["-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=brown:r=44100,highpass=f=35,lowpass=f=400,volume=0.18",
         "-f", "lavfi", "-i", f"sine=f={base}:d={dur},volume=0.09",
         "-f", "lavfi", "-i", f"sine=f={minor_third}:d={dur},volume=0.05",
         "-f", "lavfi", "-i", f"sine=f={fifth}:d={dur},volume=0.04",
         "-f", "lavfi", "-i", f"sine=f={sub}:d={dur},volume=0.06",
         "-filter_complex",
         f"[0][1][2][3][4]amix=inputs=5:duration=first,"
         f"aecho=0.85:0.88:{echo_d}:0.45|0.3,"
         f"lowpass=f=900,"
         f"volume=1.6"],
        out, "suspense")


# ── Cinematic — dark, suspenseful, low drone (People Stories under voice) ──
def _gen_cinematic(dur: float, out: str):
    base = random.choice([130.81, 138.59, 146.83, 155.56])  # C3-Eb3
    minor_third = base * 1.2
    sub = base * 0.5
    echo_d = random.choice(["200|400", "250|500", "300|600"])
    _ffmpeg_gen(
        ["-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=brown:r=44100,highpass=f=40,lowpass=f=350,volume=0.22",
         "-f", "lavfi", "-i", f"sine=f={base}:d={dur},volume=0.10",
         "-f", "lavfi", "-i", f"sine=f={minor_third}:d={dur},volume=0.05",
         "-f", "lavfi", "-i", f"sine=f={sub}:d={dur},volume=0.07",
         "-filter_complex",
         f"[0][1][2][3]amix=inputs=4:duration=first,"
         f"aecho=0.9:0.9:{echo_d}:0.6|0.4,"
         f"lowpass=f=1000,"
         f"volume=1.5"],
        out, "cinematic")


GENERATORS = {
    "upbeat":    _gen_upbeat,
    "playful":   _gen_playful,
    "relaxing":  _gen_relaxing,
    "cinematic": _gen_cinematic,
    "wisdom":    _gen_wisdom,
    "mysterious": _gen_mysterious,
    "suspense":  _gen_suspense,
}


def generate_background_music(mood: str, duration: float, output_path: str) -> str:
    """
    Get mood-matched background music.
    Order: 1) cached Jamendo track  2) new Jamendo download  3) generated fallback
    Returns path to the output MP3.
    """
    os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # ── Check cache ────────────────────────────────────────────
    cached = [f for f in os.listdir(MUSIC_CACHE_DIR)
              if f.startswith(f"{mood}_") and f.endswith(".mp3")]

    if len(cached) >= MAX_CACHED_PER_MOOD:
        pick      = random.choice(cached)
        cached_path = os.path.join(MUSIC_CACHE_DIR, pick)
        cached_dur  = _get_duration(cached_path)
        if cached_dur >= duration:
            _ffmpeg_gen(["-i", cached_path, "-t", str(duration), "-c", "copy"],
                        output_path, "trim_cached")
            print(f"[Music] Reused cached {mood} track")
            return output_path

    # ── Try Jamendo (real CC-licensed music) ───────────────────
    cache_idx  = len(cached) + 1
    cache_path = os.path.join(MUSIC_CACHE_DIR, f"{mood}_{cache_idx}.mp3")

    if _fetch_jamendo(mood, duration + 15, cache_path):
        _ffmpeg_gen(["-i", cache_path, "-t", str(duration), "-c", "copy"],
                    output_path, "trim_jamendo_final")
        print(f"[Music] Jamendo {mood} track ready -> {output_path}")
        return output_path

    # ── Fallback: synthesise with ffmpeg ───────────────────────
    gen_fn       = GENERATORS.get(mood, _gen_relaxing)
    gen_duration = duration + 15
    print(f"[Music] Generating {mood} track ({gen_duration:.0f}s) [synthesised fallback]...")
    gen_fn(gen_duration, cache_path)

    _ffmpeg_gen(["-i", cache_path, "-t", str(duration), "-c", "copy"],
                output_path, "trim_new")
    print(f"[Music] {mood} track ready -> {output_path}")
    return output_path
