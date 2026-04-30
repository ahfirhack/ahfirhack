"""
video_assembler.py (v8 — Shorts Optimized 2026)
- Full HD 1080×1920, 9:16 vertical, 8 Mbps, CRF 18
- Captions: 4 words per line, 2-3 lines per block (never 1 or 4+)
- Short-script mode: script stays on screen until video ends (font size 42)
- Visual hook in first 1.5 s
- End-screen fade to black
"""

import os
import sys
import subprocess
import random
import requests
from config import TEMP_DIR, OUTPUT_DIR, FONT_BASE_DIR, PREFERRED_FONTS, WINDOWS_FONT_PATHS, END_SCREEN_DURATION

# Full HD portrait — YouTube Shorts standard
WIDTH  = 1080
HEIGHT = 1920

# Caption constants
WORDS_PER_LINE         = 5
MIN_LINES_PER_BLOCK    = 2
MAX_LINES_PER_BLOCK    = 4
# If script has ≤ this many words it is "too small" → show continuously
SHORT_SCRIPT_THRESHOLD = 24
# Font size for short-script continuous display (~14 pt equivalent at 1080p mobile)
SHORT_SCRIPT_FONTSIZE  = 42
CAPTION_FONTSIZE       = 50
CAPTION_LINE_HEIGHT    = 62

FONT_DOWNLOAD_URLS = {
    "Montserrat-Bold": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf",
    "Lato-Bold":       "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    "Raleway-Bold":    "https://github.com/impallari/Raleway/raw/master/fonts/Raleway-Bold.ttf",
}
FONT_DOWNLOAD_URLS_REGULAR = {
    "Montserrat-Regular": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Regular.ttf",
    "Lato-Regular":       "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
}

VISUAL_HOOKS = [
    "WATCH THIS",
    "WAIT FOR IT",
    "YOU NEED THIS",
    "TRY THIS NOW",
    "DID YOU KNOW",
    "STOP SCROLLING",
    "MIND BLOWN",
    "GAME CHANGER",
]


def _resolve_font(bold=True) -> str:
    os.makedirs(FONT_BASE_DIR, exist_ok=True)
    urls  = FONT_DOWNLOAD_URLS if bold else FONT_DOWNLOAD_URLS_REGULAR
    names = PREFERRED_FONTS if bold else [n.replace("-Bold", "-Regular") for n in PREFERRED_FONTS]
    suffix = "-Bold" if bold else "-Regular"

    for name in names:
        local = os.path.join(FONT_BASE_DIR, f"{name}.ttf")
        if os.path.exists(local):
            return _esc(local)
        url = urls.get(name)
        if url:
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    with open(local, "wb") as f:
                        f.write(r.content)
                    return _esc(local)
            except Exception:
                pass
        # Windows system fonts
        if sys.platform == "win32":
            wp = WINDOWS_FONT_PATHS.get(name)
            if wp and os.path.exists(wp.replace("C\\:/", "C:/")):
                return wp

    # Linux system font fallbacks
    linux_bold = [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    linux_regular = [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for p in (linux_bold if bold else linux_regular):
        if os.path.exists(p):
            return p

    # Windows final fallback
    if sys.platform == "win32":
        return WINDOWS_FONT_PATHS["_fallback"]

    # Last resort: any font on the system
    for root, _, files in os.walk("/usr/share/fonts"):
        for fn in files:
            if fn.endswith(".ttf") and (suffix.lower() in fn.lower() or "sans" in fn.lower()):
                return os.path.join(root, fn)
    return "DejaVuSans.ttf"  # ffmpeg will search its own font path


def _esc(path: str) -> str:
    p = os.path.abspath(path)
    if sys.platform == "win32":
        p = p.replace("\\", "/").replace(":", "\\:", 1)
    return p


def _ffmpeg(args, label=""):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg [{label}]:\n{r.stderr}")


def _dur(path):
    # Escape path for Windows
    if sys.platform == "win32":
        path = path.replace("\\", "/").replace(":", "\\:", 1)
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _mix_audio(voice_path: str, music_path: str, output_path: str, music_volume: float = 0.3) -> str:
    """
    Mix voiceover with background music.
    Music is lowered to not overpower the voice.
    Voice starts after 1 second delay.
    """
    # Escape paths for Windows
    if sys.platform == "win32":
        voice_path = voice_path.replace("\\", "/").replace(":", "\\:", 1)
        music_path = music_path.replace("\\", "/").replace(":", "\\:", 1)
        output_path = output_path.replace("\\", "/").replace(":", "\\:", 1)

    voice_dur = _dur(voice_path.replace("\\:", ":", 1).replace("/", "\\"))
    music_dur = _dur(music_path.replace("\\:", ":", 1).replace("/", "\\"))

    # Total duration = voice + 1 second delay
    total_dur = voice_dur + 1

    # Guard: if music file is unreadable or empty, skip mixing
    if music_dur <= 0:
        print("[Assembler] Warning: Could not read music duration, skipping music mix.")
        return voice_path

    # Extend music if shorter than total duration
    if music_dur < total_dur:
        loop_count = int(total_dur / music_dur) + 1
        extended_music = output_path.replace(".mp3", "_music_ext.mp3")
        _ffmpeg(["-stream_loop", str(loop_count), "-i", music_path,
                 "-t", str(total_dur), "-c", "copy", extended_music], "extend_music")
        music_path = extended_music

    # Mix voice + music with 1 second delay on voice
    _ffmpeg([
        "-i", voice_path,
        "-i", music_path,
        "-filter_complex",
        f"[0:a]adelay=1000|1000[voice_delayed];[voice_delayed][1:a]amix=inputs=2:duration=first:weights=1 {music_volume}",
        "-t", str(total_dur),
        output_path
    ], "mix_audio")

    print(f"[Assembler] Mixed voice + music (voice starts after 1s, music volume: {music_volume})")
    return output_path


def _resize(inp, out):
    """Scale to Full HD portrait 1080×1920, high quality."""
    _ffmpeg(["-i", inp,
             "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "256k", "-r", "30",
             "-pix_fmt", "yuv420p", out], "resize")


def _safe_text(text: str) -> str:
    return (text.replace("'", "").replace('"', "").replace(":", " ")
            .replace("\\", "").replace("[", "").replace("]", "")
            .replace(",", "").replace(";", "").replace("%", ""))


def _build_hook_filter(font_bold: str) -> str:
    hook_text = random.choice(VISUAL_HOOKS)
    filters = []
    # 1. Stylish Top & Bottom Dark Vignette 
    # This darkens the top and bottom 25% of the screen for a cinematic feel
    filters.append(
        f"drawbox=y=0:w={WIDTH}:h={HEIGHT}/4:color=black@0.5:t=fill:enable='lt(t,2.2)'"
    )
    filters.append(
        f"drawbox=y={HEIGHT}*0.75:w={WIDTH}:h={HEIGHT}/4:color=black@0.5:t=fill:enable='lt(t,2.2)'"
    )
    
    # 2. The Stylish Hook Text (Neon Yellow + Shadow)
    filters.append(
        f"drawtext="
        f"fontfile='{font_bold}':"
        f"text='{hook_text}':"
        f"fontsize=110:"         # Extra large for maximum style
        f"fontcolor=0xFFFF00:"   # Bright Neon Yellow
        f"borderw=12:bordercolor=black@0.8:" # Heavy soft-edge border
        f"x=(w-text_w)/2:y=(h-text_h)/2-100:" # Shifted slightly up for better framing
        f"enable='lt(t,2.2)'"    # Hold slightly longer
    )
    
    # 3. "Emotional" Sub-Hook (Smaller, white text below the main hook)
    filters.append(
        f"drawtext="
        f"fontfile='{font_bold}':"
        f"text='(Wait for the end)':"
        f"fontsize=50:"
        f"fontcolor=white:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='lt(t,2.2)'"
    )
    
    return ",".join(filters)


def _build_caption_filter(script: str, total_dur: float, font_bold: str) -> str:
    """
    Caption rules:
    - 5 words per line
    - 2-3 lines per block (never 1, never 4+)
    - If script ≤ SHORT_SCRIPT_THRESHOLD words, show all lines continuously
      until end of video at SHORT_SCRIPT_FONTSIZE (≈14 pt at 1080p).
    """
    words = script.split()
    if not words:
        return ""

    # Build lines of exactly 4 words (last line may have fewer)
    all_lines = []
    for i in range(0, len(words), WORDS_PER_LINE):
        line = " ".join(words[i:i + WORDS_PER_LINE])
        all_lines.append(_safe_text(line))

    # ── SHORT SCRIPT: display all lines continuously until end ──
    if len(words) <= SHORT_SCRIPT_THRESHOLD:
        filters = []
        block_h = len(all_lines) * (SHORT_SCRIPT_FONTSIZE + 10)
        start_y = HEIGHT // 2 - block_h // 2
        for li, line in enumerate(all_lines):
            y = start_y + li * (SHORT_SCRIPT_FONTSIZE + 10)
            filters.append(
                f"drawtext="
                f"fontfile='{font_bold}':"
                f"text='{line}':"
                f"fontsize={SHORT_SCRIPT_FONTSIZE}:"
                f"fontcolor=white:"
                f"borderw=3:bordercolor=black:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,0,{total_dur:.2f})'"
            )
        return ",".join(filters)

    # ── NORMAL: group lines into blocks of 2-3, timed across video ──
    blocks = []
    idx = 0
    while idx < len(all_lines):
        remaining = len(all_lines) - idx
        if remaining == 1 and blocks:
            # Append orphan line to last block (keeps ≤ 3)
            blocks[-1].append(all_lines[idx])
            idx += 1
        else:
            size = MIN_LINES_PER_BLOCK if remaining == MIN_LINES_PER_BLOCK else min(MAX_LINES_PER_BLOCK, remaining)
            blocks.append(all_lines[idx:idx + size])
            idx += size

    cap_start = 2.0
    cap_end   = max(total_dur - END_SCREEN_DURATION, total_dur * 0.85)
    cap_dur   = cap_end - cap_start

    # Guard: if video is too short to fit captions, bail out
    if cap_dur <= 0:
        return ""

    seg = cap_dur / max(len(blocks), 1)

    filters = []
    for bi, block in enumerate(blocks):
        t_start = cap_start + bi * seg
        t_end   = t_start + seg
        block_h = len(block) * CAPTION_LINE_HEIGHT
        start_y = HEIGHT // 2 - block_h // 2

        for li, line in enumerate(block):
            y = start_y + li * CAPTION_LINE_HEIGHT
            filters.append(
                f"drawtext="
                f"fontfile='{font_bold}':"
                f"text='{line}':"
                f"fontsize={CAPTION_FONTSIZE}:"
                f"fontcolor=white:"
                f"borderw=4:bordercolor=black:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
    return ",".join(filters)


def _build_end_screen_filter(total_dur, font_bold, font_regular, channel_name=""):
    t0 = total_dur - END_SCREEN_DURATION
    eb = f"gte(t,{t0:.2f})"
    return f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=black@0.8:t=fill:enable='{eb}'"


def assemble_video(clip_paths, audio_path, script, output_filename, channel_name="", music_path=None) -> str:
    """
    Assemble video with clips and audio.
    If music_path is provided, mixes voice (audio_path) with background music.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    fb  = _resolve_font(True)
    fr  = _resolve_font(False)
    out = os.path.join(OUTPUT_DIR, output_filename)

    # Mix voice + music if music is provided
    if music_path and os.path.exists(music_path):
        mixed_audio = os.path.join(TEMP_DIR, "mixed_audio.mp3")
        _mix_audio(audio_path, music_path, mixed_audio, music_volume=0.25)
        audio_path = mixed_audio

    # Escape audio path for Windows
    if sys.platform == "win32":
        audio_path = audio_path.replace("\\", "/").replace(":", "\\:", 1)

    a_dur = _dur(audio_path)
    total = a_dur + END_SCREEN_DURATION

    # Extend audio with silence for end screen
    ext_audio = os.path.join(TEMP_DIR, "audio_ext.mp3")
    _ffmpeg(["-i", audio_path, "-af", f"apad=pad_dur={END_SCREEN_DURATION}",
             "-t", str(total), ext_audio], "ext_audio")
    print(f"[Assembler] {a_dur:.0f}s music + {END_SCREEN_DURATION}s end screen = {total:.0f}s")

    # Resize clips to Full HD portrait
    resized = []
    for i, cp in enumerate(clip_paths):
        rp = os.path.join(TEMP_DIR, f"r_{i}.mp4")
        try:
            _resize(cp, rp)
            resized.append(rp)
        except Exception as e:
            print(f"[Assembler] Skip clip: {e}")

    if not resized:
        black = os.path.join(TEMP_DIR, "black.mp4")
        _ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r=30:d={total}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", black], "black")
        resized = [black]

    # Concat clips to fill total duration
    cl  = os.path.join(TEMP_DIR, "cl.txt")
    acc, used = 0.0, []
    for rp in resized:
        if acc >= total:
            break
        d = _dur(rp)
        if d > 0:
            used.append(rp)
            acc += d
    while acc < total and used:
        used.append(used[-1])
        acc += _dur(used[-1])

    with open(cl, "w") as f:
        for rp in used:
            f.write(f"file '{os.path.abspath(rp)}'\n")

    cr = os.path.join(TEMP_DIR, "cr.mp4")
    ct = os.path.join(TEMP_DIR, "ct.mp4")
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", cl, "-c", "copy", cr], "concat")
    _ffmpeg(["-i", cr, "-t", str(total), "-c", "copy", ct], "trim")

    # Build combined overlay: hook → captions → end screen
    hook_f    = _build_hook_filter(fb)
    caption_f = _build_caption_filter(script, total, fb)
    end_f     = _build_end_screen_filter(total, fb, fr, channel_name)
    parts     = [p for p in [hook_f, caption_f, end_f] if p]
    vf        = ",".join(parts)

    print("[Assembler] Rendering Full HD 1080×1920 (9:16) at 8 Mbps CRF 18...")
    _ffmpeg(["-i", ct, "-i", ext_audio, "-vf", vf,
             "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-b:v", "8000k",
             "-c:a", "aac", "-b:a", "256k",
             "-pix_fmt", "yuv420p",
             "-t", str(total), "-r", "30", out], "render")

    print(f"[Assembler] Done -> {out} ({total:.0f}s)")
    return out"""
video_assembler.py (v8 — Shorts Optimized 2026)
- Full HD 1080×1920, 9:16 vertical, 8 Mbps, CRF 18
- Captions: 4 words per line, 2-3 lines per block (never 1 or 4+)
- Short-script mode: script stays on screen until video ends (font size 42)
- Visual hook in first 1.5 s
- End-screen fade to black
"""

import os
import sys
import subprocess
import random
import requests
from config import TEMP_DIR, OUTPUT_DIR, FONT_BASE_DIR, PREFERRED_FONTS, WINDOWS_FONT_PATHS, END_SCREEN_DURATION

# Full HD portrait — YouTube Shorts standard
WIDTH  = 1080
HEIGHT = 1920

# Caption constants
WORDS_PER_LINE         = 5
MIN_LINES_PER_BLOCK    = 2
MAX_LINES_PER_BLOCK    = 4
# If script has ≤ this many words it is "too small" → show continuously
SHORT_SCRIPT_THRESHOLD = 24
# Font size for short-script continuous display (~14 pt equivalent at 1080p mobile)
SHORT_SCRIPT_FONTSIZE  = 42
CAPTION_FONTSIZE       = 50
CAPTION_LINE_HEIGHT    = 62

FONT_DOWNLOAD_URLS = {
    "Montserrat-Bold": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf",
    "Lato-Bold":       "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    "Raleway-Bold":    "https://github.com/impallari/Raleway/raw/master/fonts/Raleway-Bold.ttf",
}
FONT_DOWNLOAD_URLS_REGULAR = {
    "Montserrat-Regular": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Regular.ttf",
    "Lato-Regular":       "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
}

VISUAL_HOOKS = [
    "WATCH THIS",
    "WAIT FOR IT",
    "YOU NEED THIS",
    "TRY THIS NOW",
    "DID YOU KNOW",
    "STOP SCROLLING",
    "MIND BLOWN",
    "GAME CHANGER",
]


def _resolve_font(bold=True) -> str:
    os.makedirs(FONT_BASE_DIR, exist_ok=True)
    urls  = FONT_DOWNLOAD_URLS if bold else FONT_DOWNLOAD_URLS_REGULAR
    names = PREFERRED_FONTS if bold else [n.replace("-Bold", "-Regular") for n in PREFERRED_FONTS]
    suffix = "-Bold" if bold else "-Regular"

    for name in names:
        local = os.path.join(FONT_BASE_DIR, f"{name}.ttf")
        if os.path.exists(local):
            return _esc(local)
        url = urls.get(name)
        if url:
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    with open(local, "wb") as f:
                        f.write(r.content)
                    return _esc(local)
            except Exception:
                pass
        # Windows system fonts
        if sys.platform == "win32":
            wp = WINDOWS_FONT_PATHS.get(name)
            if wp and os.path.exists(wp.replace("C\\:/", "C:/")):
                return wp

    # Linux system font fallbacks
    linux_bold = [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    linux_regular = [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for p in (linux_bold if bold else linux_regular):
        if os.path.exists(p):
            return p

    # Windows final fallback
    if sys.platform == "win32":
        return WINDOWS_FONT_PATHS["_fallback"]

    # Last resort: any font on the system
    for root, _, files in os.walk("/usr/share/fonts"):
        for fn in files:
            if fn.endswith(".ttf") and (suffix.lower() in fn.lower() or "sans" in fn.lower()):
                return os.path.join(root, fn)
    return "DejaVuSans.ttf"  # ffmpeg will search its own font path


def _esc(path: str) -> str:
    p = os.path.abspath(path)
    if sys.platform == "win32":
        p = p.replace("\\", "/").replace(":", "\\:", 1)
    return p


def _ffmpeg(args, label=""):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg [{label}]:\n{r.stderr}")


def _dur(path):
    # Escape path for Windows
    if sys.platform == "win32":
        path = path.replace("\\", "/").replace(":", "\\:", 1)
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _mix_audio(voice_path: str, music_path: str, output_path: str, music_volume: float = 0.3) -> str:
    """
    Mix voiceover with background music.
    Music is lowered to not overpower the voice.
    Voice starts after 1 second delay.
    """
    # Escape paths for Windows
    if sys.platform == "win32":
        voice_path = voice_path.replace("\\", "/").replace(":", "\\:", 1)
        music_path = music_path.replace("\\", "/").replace(":", "\\:", 1)
        output_path = output_path.replace("\\", "/").replace(":", "\\:", 1)

    voice_dur = _dur(voice_path.replace("\\:", ":", 1).replace("/", "\\"))
    music_dur = _dur(music_path.replace("\\:", ":", 1).replace("/", "\\"))

    # Total duration = voice + 1 second delay
    total_dur = voice_dur + 1

    # Guard: if music file is unreadable or empty, skip mixing
    if music_dur <= 0:
        print("[Assembler] Warning: Could not read music duration, skipping music mix.")
        return voice_path

    # Extend music if shorter than total duration
    if music_dur < total_dur:
        loop_count = int(total_dur / music_dur) + 1
        extended_music = output_path.replace(".mp3", "_music_ext.mp3")
        _ffmpeg(["-stream_loop", str(loop_count), "-i", music_path,
                 "-t", str(total_dur), "-c", "copy", extended_music], "extend_music")
        music_path = extended_music

    # Mix voice + music with 1 second delay on voice
    _ffmpeg([
        "-i", voice_path,
        "-i", music_path,
        "-filter_complex",
        f"[0:a]adelay=1000|1000[voice_delayed];[voice_delayed][1:a]amix=inputs=2:duration=first:weights=1 {music_volume}",
        "-t", str(total_dur),
        output_path
    ], "mix_audio")

    print(f"[Assembler] Mixed voice + music (voice starts after 1s, music volume: {music_volume})")
    return output_path


def _resize(inp, out):
    """Scale to Full HD portrait 1080×1920, high quality."""
    _ffmpeg(["-i", inp,
             "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "256k", "-r", "30",
             "-pix_fmt", "yuv420p", out], "resize")


def _safe_text(text: str) -> str:
    return (text.replace("'", "").replace('"', "").replace(":", " ")
            .replace("\\", "").replace("[", "").replace("]", "")
            .replace(",", "").replace(";", "").replace("%", ""))


def _build_hook_filter(font_bold: str) -> str:
    hook_text = random.choice(VISUAL_HOOKS)
    filters = []
    # 1. Stylish Top & Bottom Dark Vignette 
    # This darkens the top and bottom 25% of the screen for a cinematic feel
    filters.append(
        f"drawbox=y=0:w={WIDTH}:h={HEIGHT}/4:color=black@0.5:t=fill:enable='lt(t,2.2)'"
    )
    filters.append(
        f"drawbox=y={HEIGHT}*0.75:w={WIDTH}:h={HEIGHT}/4:color=black@0.5:t=fill:enable='lt(t,2.2)'"
    )
    
    # 2. The Stylish Hook Text (Neon Yellow + Shadow)
    filters.append(
        f"drawtext="
        f"fontfile='{font_bold}':"
        f"text='{hook_text}':"
        f"fontsize=110:"         # Extra large for maximum style
        f"fontcolor=0xFFFF00:"   # Bright Neon Yellow
        f"borderw=12:bordercolor=black@0.8:" # Heavy soft-edge border
        f"x=(w-text_w)/2:y=(h-text_h)/2-100:" # Shifted slightly up for better framing
        f"enable='lt(t,2.2)'"    # Hold slightly longer
    )
    
    # 3. "Emotional" Sub-Hook (Smaller, white text below the main hook)
    filters.append(
        f"drawtext="
        f"fontfile='{font_bold}':"
        f"text='(Wait for the end)':"
        f"fontsize=50:"
        f"fontcolor=white:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='lt(t,2.2)'"
    )
    
    return ",".join(filters)


def _build_caption_filter(script: str, total_dur: float, font_bold: str) -> str:
    """
    Caption rules:
    - 5 words per line
    - 2-3 lines per block (never 1, never 4+)
    - If script ≤ SHORT_SCRIPT_THRESHOLD words, show all lines continuously
      until end of video at SHORT_SCRIPT_FONTSIZE (≈14 pt at 1080p).
    """
    words = script.split()
    if not words:
        return ""

    # Build lines of exactly 4 words (last line may have fewer)
    all_lines = []
    for i in range(0, len(words), WORDS_PER_LINE):
        line = " ".join(words[i:i + WORDS_PER_LINE])
        all_lines.append(_safe_text(line))

    # ── SHORT SCRIPT: display all lines continuously until end ──
    if len(words) <= SHORT_SCRIPT_THRESHOLD:
        filters = []
        block_h = len(all_lines) * (SHORT_SCRIPT_FONTSIZE + 10)
        start_y = HEIGHT // 2 - block_h // 2
        for li, line in enumerate(all_lines):
            y = start_y + li * (SHORT_SCRIPT_FONTSIZE + 10)
            filters.append(
                f"drawtext="
                f"fontfile='{font_bold}':"
                f"text='{line}':"
                f"fontsize={SHORT_SCRIPT_FONTSIZE}:"
                f"fontcolor=white:"
                f"borderw=3:bordercolor=black:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,0,{total_dur:.2f})'"
            )
        return ",".join(filters)

    # ── NORMAL: group lines into blocks of 2-3, timed across video ──
    blocks = []
    idx = 0
    while idx < len(all_lines):
        remaining = len(all_lines) - idx
        if remaining == 1 and blocks:
            # Append orphan line to last block (keeps ≤ 3)
            blocks[-1].append(all_lines[idx])
            idx += 1
        else:
            size = MIN_LINES_PER_BLOCK if remaining == MIN_LINES_PER_BLOCK else min(MAX_LINES_PER_BLOCK, remaining)
            blocks.append(all_lines[idx:idx + size])
            idx += size

    cap_start = 2.0
    cap_end   = max(total_dur - END_SCREEN_DURATION, total_dur * 0.85)
    cap_dur   = cap_end - cap_start

    # Guard: if video is too short to fit captions, bail out
    if cap_dur <= 0:
        return ""

    seg = cap_dur / max(len(blocks), 1)

    filters = []
    for bi, block in enumerate(blocks):
        t_start = cap_start + bi * seg
        t_end   = t_start + seg
        block_h = len(block) * CAPTION_LINE_HEIGHT
        start_y = HEIGHT // 2 - block_h // 2

        for li, line in enumerate(block):
            y = start_y + li * CAPTION_LINE_HEIGHT
            filters.append(
                f"drawtext="
                f"fontfile='{font_bold}':"
                f"text='{line}':"
                f"fontsize={CAPTION_FONTSIZE}:"
                f"fontcolor=white:"
                f"borderw=4:bordercolor=black:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
    return ",".join(filters)


def _build_end_screen_filter(total_dur, font_bold, font_regular, channel_name=""):
    t0 = total_dur - END_SCREEN_DURATION
    eb = f"gte(t,{t0:.2f})"
    return f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=black@0.8:t=fill:enable='{eb}'"


def assemble_video(clip_paths, audio_path, script, output_filename, channel_name="", music_path=None) -> str:
    """
    Assemble video with clips and audio.
    If music_path is provided, mixes voice (audio_path) with background music.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    fb  = _resolve_font(True)
    fr  = _resolve_font(False)
    out = os.path.join(OUTPUT_DIR, output_filename)

    # Mix voice + music if music is provided
    if music_path and os.path.exists(music_path):
        mixed_audio = os.path.join(TEMP_DIR, "mixed_audio.mp3")
        _mix_audio(audio_path, music_path, mixed_audio, music_volume=0.25)
        audio_path = mixed_audio

    # Escape audio path for Windows
    if sys.platform == "win32":
        audio_path = audio_path.replace("\\", "/").replace(":", "\\:", 1)

    a_dur = _dur(audio_path)
    total = a_dur + END_SCREEN_DURATION

    # Extend audio with silence for end screen
    ext_audio = os.path.join(TEMP_DIR, "audio_ext.mp3")
    _ffmpeg(["-i", audio_path, "-af", f"apad=pad_dur={END_SCREEN_DURATION}",
             "-t", str(total), ext_audio], "ext_audio")
    print(f"[Assembler] {a_dur:.0f}s music + {END_SCREEN_DURATION}s end screen = {total:.0f}s")

    # Resize clips to Full HD portrait
    resized = []
    for i, cp in enumerate(clip_paths):
        rp = os.path.join(TEMP_DIR, f"r_{i}.mp4")
        try:
            _resize(cp, rp)
            resized.append(rp)
        except Exception as e:
            print(f"[Assembler] Skip clip: {e}")

    if not resized:
        black = os.path.join(TEMP_DIR, "black.mp4")
        _ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r=30:d={total}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", black], "black")
        resized = [black]

    # Concat clips to fill total duration
    cl  = os.path.join(TEMP_DIR, "cl.txt")
    acc, used = 0.0, []
    for rp in resized:
        if acc >= total:
            break
        d = _dur(rp)
        if d > 0:
            used.append(rp)
            acc += d
    while acc < total and used:
        used.append(used[-1])
        acc += _dur(used[-1])

    with open(cl, "w") as f:
        for rp in used:
            f.write(f"file '{os.path.abspath(rp)}'\n")

    cr = os.path.join(TEMP_DIR, "cr.mp4")
    ct = os.path.join(TEMP_DIR, "ct.mp4")
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", cl, "-c", "copy", cr], "concat")
    _ffmpeg(["-i", cr, "-t", str(total), "-c", "copy", ct], "trim")

    # Build combined overlay: hook → captions → end screen
    hook_f    = _build_hook_filter(fb)
    caption_f = _build_caption_filter(script, total, fb)
    end_f     = _build_end_screen_filter(total, fb, fr, channel_name)
    parts     = [p for p in [hook_f, caption_f, end_f] if p]
    vf        = ",".join(parts)

    print("[Assembler] Rendering Full HD 1080×1920 (9:16) at 8 Mbps CRF 18...")
    _ffmpeg(["-i", ct, "-i", ext_audio, "-vf", vf,
             "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-b:v", "8000k",
             "-c:a", "aac", "-b:a", "256k",
             "-pix_fmt", "yuv420p",
             "-t", str(total), "-r", "30", out], "render")

    print(f"[Assembler] Done -> {out} ({total:.0f}s)")
    return out"""
video_assembler.py (v8 — Shorts Optimized 2026)
- Full HD 1080×1920, 9:16 vertical, 8 Mbps, CRF 18
- Captions: 4 words per line, 2-3 lines per block (never 1 or 4+)
- Short-script mode: script stays on screen until video ends (font size 42)
- Visual hook in first 1.5 s
- End-screen fade to black
"""

import os
import sys
import subprocess
import random
import requests
from config import TEMP_DIR, OUTPUT_DIR, FONT_BASE_DIR, PREFERRED_FONTS, WINDOWS_FONT_PATHS, END_SCREEN_DURATION

# Full HD portrait — YouTube Shorts standard
WIDTH  = 1080
HEIGHT = 1920

# Caption constants
WORDS_PER_LINE         = 5
MIN_LINES_PER_BLOCK    = 2
MAX_LINES_PER_BLOCK    = 4
# If script has ≤ this many words it is "too small" → show continuously
SHORT_SCRIPT_THRESHOLD = 24
# Font size for short-script continuous display (~14 pt equivalent at 1080p mobile)
SHORT_SCRIPT_FONTSIZE  = 42
CAPTION_FONTSIZE       = 50
CAPTION_LINE_HEIGHT    = 62

FONT_DOWNLOAD_URLS = {
    "Montserrat-Bold": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf",
    "Lato-Bold":       "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    "Raleway-Bold":    "https://github.com/impallari/Raleway/raw/master/fonts/Raleway-Bold.ttf",
}
FONT_DOWNLOAD_URLS_REGULAR = {
    "Montserrat-Regular": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Regular.ttf",
    "Lato-Regular":       "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
}

VISUAL_HOOKS = [
    "WATCH THIS",
    "WAIT FOR IT",
    "YOU NEED THIS",
    "TRY THIS NOW",
    "DID YOU KNOW",
    "STOP SCROLLING",
    "MIND BLOWN",
    "GAME CHANGER",
]


def _resolve_font(bold=True) -> str:
    os.makedirs(FONT_BASE_DIR, exist_ok=True)
    urls  = FONT_DOWNLOAD_URLS if bold else FONT_DOWNLOAD_URLS_REGULAR
    names = PREFERRED_FONTS if bold else [n.replace("-Bold", "-Regular") for n in PREFERRED_FONTS]
    suffix = "-Bold" if bold else "-Regular"

    for name in names:
        local = os.path.join(FONT_BASE_DIR, f"{name}.ttf")
        if os.path.exists(local):
            return _esc(local)
        url = urls.get(name)
        if url:
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    with open(local, "wb") as f:
                        f.write(r.content)
                    return _esc(local)
            except Exception:
                pass
        # Windows system fonts
        if sys.platform == "win32":
            wp = WINDOWS_FONT_PATHS.get(name)
            if wp and os.path.exists(wp.replace("C\\:/", "C:/")):
                return wp

    # Linux system font fallbacks
    linux_bold = [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    linux_regular = [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for p in (linux_bold if bold else linux_regular):
        if os.path.exists(p):
            return p

    # Windows final fallback
    if sys.platform == "win32":
        return WINDOWS_FONT_PATHS["_fallback"]

    # Last resort: any font on the system
    for root, _, files in os.walk("/usr/share/fonts"):
        for fn in files:
            if fn.endswith(".ttf") and (suffix.lower() in fn.lower() or "sans" in fn.lower()):
                return os.path.join(root, fn)
    return "DejaVuSans.ttf"  # ffmpeg will search its own font path


def _esc(path: str) -> str:
    p = os.path.abspath(path)
    if sys.platform == "win32":
        p = p.replace("\\", "/").replace(":", "\\:", 1)
    return p


def _ffmpeg(args, label=""):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg [{label}]:\n{r.stderr}")


def _dur(path):
    # Escape path for Windows
    if sys.platform == "win32":
        path = path.replace("\\", "/").replace(":", "\\:", 1)
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _mix_audio(voice_path: str, music_path: str, output_path: str, music_volume: float = 0.3) -> str:
    """
    Mix voiceover with background music.
    Music is lowered to not overpower the voice.
    Voice starts after 1 second delay.
    """
    # Escape paths for Windows
    if sys.platform == "win32":
        voice_path = voice_path.replace("\\", "/").replace(":", "\\:", 1)
        music_path = music_path.replace("\\", "/").replace(":", "\\:", 1)
        output_path = output_path.replace("\\", "/").replace(":", "\\:", 1)

    voice_dur = _dur(voice_path.replace("\\:", ":", 1).replace("/", "\\"))
    music_dur = _dur(music_path.replace("\\:", ":", 1).replace("/", "\\"))

    # Total duration = voice + 1 second delay
    total_dur = voice_dur + 1

    # Guard: if music file is unreadable or empty, skip mixing
    if music_dur <= 0:
        print("[Assembler] Warning: Could not read music duration, skipping music mix.")
        return voice_path

    # Extend music if shorter than total duration
    if music_dur < total_dur:
        loop_count = int(total_dur / music_dur) + 1
        extended_music = output_path.replace(".mp3", "_music_ext.mp3")
        _ffmpeg(["-stream_loop", str(loop_count), "-i", music_path,
                 "-t", str(total_dur), "-c", "copy", extended_music], "extend_music")
        music_path = extended_music

    # Mix voice + music with 1 second delay on voice
    _ffmpeg([
        "-i", voice_path,
        "-i", music_path,
        "-filter_complex",
        f"[0:a]adelay=1000|1000[voice_delayed];[voice_delayed][1:a]amix=inputs=2:duration=first:weights=1 {music_volume}",
        "-t", str(total_dur),
        output_path
    ], "mix_audio")

    print(f"[Assembler] Mixed voice + music (voice starts after 1s, music volume: {music_volume})")
    return output_path


def _resize(inp, out):
    """Scale to Full HD portrait 1080×1920, high quality."""
    _ffmpeg(["-i", inp,
             "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "256k", "-r", "30",
             "-pix_fmt", "yuv420p", out], "resize")


def _safe_text(text: str) -> str:
    return (text.replace("'", "").replace('"', "").replace(":", " ")
            .replace("\\", "").replace("[", "").replace("]", "")
            .replace(",", "").replace(";", "").replace("%", ""))


def _build_hook_filter(font_bold: str) -> str:
    hook_text = random.choice(VISUAL_HOOKS)
    filters = []
    # 1. Stylish Top & Bottom Dark Vignette 
    # This darkens the top and bottom 25% of the screen for a cinematic feel
    filters.append(
        f"drawbox=y=0:w={WIDTH}:h={HEIGHT}/4:color=black@0.5:t=fill:enable='lt(t,2.2)'"
    )
    filters.append(
        f"drawbox=y={HEIGHT}*0.75:w={WIDTH}:h={HEIGHT}/4:color=black@0.5:t=fill:enable='lt(t,2.2)'"
    )
    
    # 2. The Stylish Hook Text (Neon Yellow + Shadow)
    filters.append(
        f"drawtext="
        f"fontfile='{font_bold}':"
        f"text='{hook_text}':"
        f"fontsize=110:"         # Extra large for maximum style
        f"fontcolor=0xFFFF00:"   # Bright Neon Yellow
        f"borderw=12:bordercolor=black@0.8:" # Heavy soft-edge border
        f"x=(w-text_w)/2:y=(h-text_h)/2-100:" # Shifted slightly up for better framing
        f"enable='lt(t,2.2)'"    # Hold slightly longer
    )
    
    # 3. "Emotional" Sub-Hook (Smaller, white text below the main hook)
    filters.append(
        f"drawtext="
        f"fontfile='{font_bold}':"
        f"text='(Wait for the end)':"
        f"fontsize=50:"
        f"fontcolor=white:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='lt(t,2.2)'"
    )
    
    return ",".join(filters)


def _build_caption_filter(script: str, total_dur: float, font_bold: str) -> str:
    """
    Caption rules:
    - 5 words per line
    - 2-3 lines per block (never 1, never 4+)
    - If script ≤ SHORT_SCRIPT_THRESHOLD words, show all lines continuously
      until end of video at SHORT_SCRIPT_FONTSIZE (≈14 pt at 1080p).
    """
    words = script.split()
    if not words:
        return ""

    # Build lines of exactly 4 words (last line may have fewer)
    all_lines = []
    for i in range(0, len(words), WORDS_PER_LINE):
        line = " ".join(words[i:i + WORDS_PER_LINE])
        all_lines.append(_safe_text(line))

    # ── SHORT SCRIPT: display all lines continuously until end ──
    if len(words) <= SHORT_SCRIPT_THRESHOLD:
        filters = []
        block_h = len(all_lines) * (SHORT_SCRIPT_FONTSIZE + 10)
        start_y = HEIGHT // 2 - block_h // 2
        for li, line in enumerate(all_lines):
            y = start_y + li * (SHORT_SCRIPT_FONTSIZE + 10)
            filters.append(
                f"drawtext="
                f"fontfile='{font_bold}':"
                f"text='{line}':"
                f"fontsize={SHORT_SCRIPT_FONTSIZE}:"
                f"fontcolor=white:"
                f"borderw=3:bordercolor=black:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,0,{total_dur:.2f})'"
            )
        return ",".join(filters)

    # ── NORMAL: group lines into blocks of 2-3, timed across video ──
    blocks = []
    idx = 0
    while idx < len(all_lines):
        remaining = len(all_lines) - idx
        if remaining == 1 and blocks:
            # Append orphan line to last block (keeps ≤ 3)
            blocks[-1].append(all_lines[idx])
            idx += 1
        else:
            size = MIN_LINES_PER_BLOCK if remaining == MIN_LINES_PER_BLOCK else min(MAX_LINES_PER_BLOCK, remaining)
            blocks.append(all_lines[idx:idx + size])
            idx += size

    cap_start = 2.0
    cap_end   = max(total_dur - END_SCREEN_DURATION, total_dur * 0.85)
    cap_dur   = cap_end - cap_start

    # Guard: if video is too short to fit captions, bail out
    if cap_dur <= 0:
        return ""

    seg = cap_dur / max(len(blocks), 1)

    filters = []
    for bi, block in enumerate(blocks):
        t_start = cap_start + bi * seg
        t_end   = t_start + seg
        block_h = len(block) * CAPTION_LINE_HEIGHT
        start_y = HEIGHT // 2 - block_h // 2

        for li, line in enumerate(block):
            y = start_y + li * CAPTION_LINE_HEIGHT
            filters.append(
                f"drawtext="
                f"fontfile='{font_bold}':"
                f"text='{line}':"
                f"fontsize={CAPTION_FONTSIZE}:"
                f"fontcolor=white:"
                f"borderw=4:bordercolor=black:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
    return ",".join(filters)


def _build_end_screen_filter(total_dur, font_bold, font_regular, channel_name=""):
    t0 = total_dur - END_SCREEN_DURATION
    eb = f"gte(t,{t0:.2f})"
    return f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=black@0.8:t=fill:enable='{eb}'"


def assemble_video(clip_paths, audio_path, script, output_filename, channel_name="", music_path=None) -> str:
    """
    Assemble video with clips and audio.
    If music_path is provided, mixes voice (audio_path) with background music.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    fb  = _resolve_font(True)
    fr  = _resolve_font(False)
    out = os.path.join(OUTPUT_DIR, output_filename)

    # Mix voice + music if music is provided
    if music_path and os.path.exists(music_path):
        mixed_audio = os.path.join(TEMP_DIR, "mixed_audio.mp3")
        _mix_audio(audio_path, music_path, mixed_audio, music_volume=0.25)
        audio_path = mixed_audio

    # Escape audio path for Windows
    if sys.platform == "win32":
        audio_path = audio_path.replace("\\", "/").replace(":", "\\:", 1)

    a_dur = _dur(audio_path)
    total = a_dur + END_SCREEN_DURATION

    # Extend audio with silence for end screen
    ext_audio = os.path.join(TEMP_DIR, "audio_ext.mp3")
    _ffmpeg(["-i", audio_path, "-af", f"apad=pad_dur={END_SCREEN_DURATION}",
             "-t", str(total), ext_audio], "ext_audio")
    print(f"[Assembler] {a_dur:.0f}s music + {END_SCREEN_DURATION}s end screen = {total:.0f}s")

    # Resize clips to Full HD portrait
    resized = []
    for i, cp in enumerate(clip_paths):
        rp = os.path.join(TEMP_DIR, f"r_{i}.mp4")
        try:
            _resize(cp, rp)
            resized.append(rp)
        except Exception as e:
            print(f"[Assembler] Skip clip: {e}")

    if not resized:
        black = os.path.join(TEMP_DIR, "black.mp4")
        _ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r=30:d={total}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", black], "black")
        resized = [black]

    # Concat clips to fill total duration
    cl  = os.path.join(TEMP_DIR, "cl.txt")
    acc, used = 0.0, []
    for rp in resized:
        if acc >= total:
            break
        d = _dur(rp)
        if d > 0:
            used.append(rp)
            acc += d
    while acc < total and used:
        used.append(used[-1])
        acc += _dur(used[-1])

    with open(cl, "w") as f:
        for rp in used:
            f.write(f"file '{os.path.abspath(rp)}'\n")

    cr = os.path.join(TEMP_DIR, "cr.mp4")
    ct = os.path.join(TEMP_DIR, "ct.mp4")
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", cl, "-c", "copy", cr], "concat")
    _ffmpeg(["-i", cr, "-t", str(total), "-c", "copy", ct], "trim")

    # Build combined overlay: hook → captions → end screen
    hook_f    = _build_hook_filter(fb)
    caption_f = _build_caption_filter(script, total, fb)
    end_f     = _build_end_screen_filter(total, fb, fr, channel_name)
    parts     = [p for p in [hook_f, caption_f, end_f] if p]
    vf        = ",".join(parts)

    print("[Assembler] Rendering Full HD 1080×1920 (9:16) at 8 Mbps CRF 18...")
    _ffmpeg(["-i", ct, "-i", ext_audio, "-vf", vf,
             "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-b:v", "8000k",
             "-c:a", "aac", "-b:a", "256k",
             "-pix_fmt", "yuv420p",
             "-t", str(total), "-r", "30", out], "render")

    print(f"[Assembler] Done -> {out} ({total:.0f}s)")
    return out
