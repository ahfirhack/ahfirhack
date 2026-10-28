"""
video_assembler.py (v9 — 2K Quality, Voice-Synced Captions)
- 2K Quality 1440×2560, 9:16 vertical, 12 Mbps, CRF 16
- Captions sync with voice timing
- Channel-specific voices
- Visual hook in first 2s (stand-alone effect)
- End-screen fade to black
"""

import os
import sys
import subprocess
import random
import re
import shutil
import requests
from config import TEMP_DIR, OUTPUT_DIR, FONT_BASE_DIR, PREFERRED_FONTS, WINDOWS_FONT_PATHS, END_SCREEN_DURATION, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_BITRATE, VIDEO_CRF

# Use quality settings from config
WIDTH  = VIDEO_WIDTH   # 1440 (2K)
HEIGHT = VIDEO_HEIGHT # 2560 (2K)

# Caption constants
WORDS_PER_LINE         = 5
MIN_LINES_PER_BLOCK    = 2
MAX_LINES_PER_BLOCK    = 2
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

CHANNEL_THEMES = {
    "silicon crime files": {
        "accent": "0xFF3131",
        "tagline": "CODE. POWER. CONSEQUENCES.",
        "hooks": (
            "THE EVIDENCE WAS DIGITAL",
            "THE CODE TOLD THE TRUTH",
            "THE NUMBERS DID NOT MATCH",
        ),
    },
    "storyfuse": {
        "accent": "0xFF5A36",
        "tagline": "BIG STAKES. SHARP TWISTS. NO FILLER.",
        "hooks": (
            "THIS CHANGES EVERYTHING",
            "THE CHOICE WAS IMPOSSIBLE",
            "THEN THE TRUTH ARRIVED",
        ),
    },
    "stoic reset": {
        "accent": "0xE8B56A",
        "tagline": "ANCIENT WISDOM. MODERN STRENGTH.",
        "hooks": (
            "RESET YOUR RESPONSE",
            "CONTROL THIS FIRST",
            "PAUSE BEFORE YOU REACT",
        ),
    },
}

DEFAULT_THEME = {
    "accent": "0xFFFF00",
    "tagline": "ONE IDEA. ONE ACTION.",
    "hooks": ("WATCH THIS", "DID YOU KNOW", "TRY THIS NOW"),
}


def _channel_theme(channel_name: str) -> dict:
    return CHANNEL_THEMES.get(channel_name.lower().strip(), DEFAULT_THEME)


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


def _has_audio(path: str) -> bool:
    """Return True when a media file contains at least one audio stream."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and "audio" in r.stdout.lower()


def _mix_audio(voice_path: str, music_path: str, output_path: str, music_volume: float = 0.3) -> str:
    """
    Mix voiceover with background music.
    Music is lowered to not overpower the voice.
    Voice starts after 1 second delay.
    """
    voice_probe_path = voice_path
    music_probe_path = music_path

    # Escape paths for Windows
    if sys.platform == "win32":
        voice_path = voice_path.replace("\\", "/").replace(":", "\\:", 1)
        music_path = music_path.replace("\\", "/").replace(":", "\\:", 1)
        output_path = output_path.replace("\\", "/").replace(":", "\\:", 1)

    voice_dur = _dur(voice_probe_path)
    music_dur = _dur(music_probe_path)

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


def _add_tech_hook_sfx(audio_path: str, total: float, output_path: str) -> str:
    """Mix a synthesized sub-boom and digital glitch at timestamp zero."""
    sfx_path = os.path.join(TEMP_DIR, "tech_glitch_boom.wav")
    _ffmpeg([
        "-f", "lavfi", "-i",
        "sine=frequency=48:sample_rate=48000:duration=0.95",
        "-f", "lavfi", "-i",
        "anoisesrc=color=white:amplitude=0.8:sample_rate=48000:duration=0.22",
        "-filter_complex",
        "[0:a]volume=0.82,afade=t=out:st=0.12:d=0.83[boom];"
        "[1:a]highpass=f=1400,lowpass=f=7000,volume=0.18,"
        "tremolo=f=35:d=0.85[glitch];"
        "[boom][glitch]amix=inputs=2:duration=longest:dropout_transition=0,"
        "alimiter=limit=0.92[sfx]",
        "-map", "[sfx]", "-c:a", "pcm_s16le", sfx_path,
    ], "tech_hook_sfx")
    _ffmpeg([
        "-i", audio_path,
        "-i", sfx_path,
        "-filter_complex",
        "[0:a]volume=1[base];[1:a]volume=0.9[sfx];"
        "[base][sfx]amix=inputs=2:duration=first:dropout_transition=0,"
        "alimiter=limit=0.95[outa]",
        "-map", "[outa]", "-t", f"{total:.3f}",
        "-c:a", "libmp3lame", "-b:a", "320k", output_path,
    ], "mix_tech_hook_sfx")
    print("[Assembler] Added timestamp-zero tech glitch/sub-boom")
    return output_path


def _resize(inp, out):
    """Scale to 2K portrait 1440×2560, high quality."""
    _ffmpeg(["-i", inp,
             "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
             "-c:v", "libx264", "-preset", "medium", "-crf", str(VIDEO_CRF),
             "-c:a", "aac", "-b:a", "320k", "-r", "30",
             "-pix_fmt", "yuv420p", out], "resize")


def _safe_text(text: str) -> str:
    return (text.replace("'", "").replace('"', "").replace(":", " ")
            .replace("\\", "").replace("[", "").replace("]", "")
            .replace(",", "").replace(";", "").replace("%", ""))


def _build_hook_filter(font_bold: str, channel_name: str = "") -> str:
    theme = _channel_theme(channel_name)
    hook_text = random.choice(theme["hooks"])
    accent = theme["accent"]
    tagline = _safe_text(theme["tagline"])
    hook_size = min(96, max(60, int(1180 / max(len(hook_text) * 0.62, 1))))
    filters = []
    # 1. Stylish Top & Bottom Dark Vignette 
    # This darkens the top and bottom 25% of the screen for a cinematic feel
    filters.append(
        f"drawbox=y=0:w={WIDTH}:h={HEIGHT}/4:color=black@0.5:t=fill:enable='lt(t,2.2)'"
    )
    filters.append(
        f"drawbox=y={HEIGHT}*0.75:w={WIDTH}:h={HEIGHT}/4:color=black@0.5:t=fill:enable='lt(t,2.2)'"
    )
    
    # 2. A channel-specific branded hook with a strong mobile-safe outline.
    filters.append(
        f"drawtext="
        f"fontfile='{font_bold}':"
        f"text='{hook_text}':"
        f"fontsize={hook_size}:"
        f"fontcolor={accent}:"
        f"borderw=10:bordercolor=black@0.9:"
        f"shadowx=6:shadowy=6:shadowcolor=black@0.65:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-100:"
        f"enable='lt(t,2.2)'"
    )

    # 3. Reinforce the channel's promise instead of a generic wait-for-it line.
    filters.append(
        f"drawtext="
        f"fontfile='{font_bold}':"
        f"text='{tagline}':"
        f"fontsize=38:"
        f"fontcolor=white:"
        f"borderw=4:bordercolor=black@0.8:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='lt(t,2.2)'"
    )
    
    return ",".join(filters)


def _build_tech_evidence_hook_filter(
    font_bold: str,
    hook_overlay: str,
    hook_accent: str,
    evidence_label: str,
) -> str:
    """Cover generic footage with a high-contrast evidence card for 3 seconds."""
    overlay = _safe_text(hook_overlay.upper())[:64] or "THE EVIDENCE WAS IN THE CODE"
    accent_text = _safe_text(hook_accent.upper())[:32] or "CASE FILE"
    label = _safe_text(evidence_label.upper())[:52] or "PUBLIC RECORD"
    accent_color = (
        "0x45FF6A" if re.search(r"[$0-9]", accent_text) else "0xFF3131"
    )
    overlay_words = overlay.split()
    if len(overlay) > 24 and len(overlay_words) > 1:
        split_at = min(
            range(1, len(overlay_words)),
            key=lambda index: abs(
                len(" ".join(overlay_words[:index]))
                - len(" ".join(overlay_words[index:]))
            ),
        )
        overlay_lines = [
            " ".join(overlay_words[:split_at]),
            " ".join(overlay_words[split_at:]),
        ]
    else:
        overlay_lines = [overlay]
    longest_line = max(len(line) for line in overlay_lines)
    overlay_size = min(76, max(48, int(1180 / max(longest_line * 0.62, 1))))
    accent_size = 112 if len(accent_text) <= 18 else 82
    active = "lt(t,3.05)"
    glitch = "between(t,0,0.08)+between(t,0.42,0.48)+between(t,1.37,1.43)"
    filters = [
        f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=0x05080D@0.96:t=fill:enable='{active}'",
        f"drawbox=x=72:y=250:w=12:h={HEIGHT}-500:color=0xFF3131@0.95:t=fill:enable='{active}'",
        f"drawbox=x=0:y={HEIGHT}*0.27:w={WIDTH}:h=8:color=0xFF3131@0.85:t=fill:enable='{glitch}'",
        f"drawbox=x=0:y={HEIGHT}*0.69:w={WIDTH}:h=5:color={accent_color}@0.75:t=fill:enable='{glitch}'",
        f"drawtext=fontfile='{font_bold}':text='CASE FILE // {label}':fontsize=34:fontcolor=0xFF5959:borderw=3:bordercolor=black:x=(w-text_w)/2:y={HEIGHT}*0.28:enable='{active}'",
        f"drawtext=fontfile='{font_bold}':text='{accent_text}':fontsize={accent_size}:fontcolor={accent_color}:borderw=9:bordercolor=black:shadowx=6:shadowy=6:shadowcolor=black@0.8:x=(w-text_w)/2:y={HEIGHT}*0.51:enable='{active}'",
        f"drawtext=fontfile='{font_bold}':text='CODE. POWER. CONSEQUENCES.':fontsize=34:fontcolor=0xD8DEE9:borderw=3:bordercolor=black:x=(w-text_w)/2:y={HEIGHT}*0.66:enable='{active}'",
    ]
    if len(overlay_lines) == 1:
        headline_positions = [(overlay_lines[0], 0.41)]
    else:
        headline_positions = [
            (overlay_lines[0], 0.385),
            (overlay_lines[1], 0.435),
        ]
    for line, y_position in headline_positions:
        filters.append(
            f"drawtext=fontfile='{font_bold}':text='{line}':fontsize={overlay_size}:"
            f"fontcolor=white:borderw=7:bordercolor=black:shadowx=5:shadowy=5:"
            f"shadowcolor=black@0.8:x=(w-text_w)/2:y={HEIGHT}*{y_position}:"
            f"enable='{active}'"
        )
    return ",".join(filters)


def _build_caption_filter(
    script: str,
    total_dur: float,
    font_bold: str,
    end_screen_duration: float = END_SCREEN_DURATION,
    speech_start: float = 0.0,
    speech_duration: float | None = None,
    minimum_start: float | None = None,
) -> str:
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
    caption_end = max(0.0, total_dur - end_screen_duration)
    speech_start = max(0.0, speech_start)
    minimum_start = speech_start if minimum_start is None else max(
        speech_start, minimum_start
    )
    if speech_duration is None or speech_duration <= 0:
        speech_duration = max(0.0, caption_end - speech_start)
    speech_duration = min(speech_duration, max(0.0, caption_end - speech_start))

    # Build lines of exactly 4 words (last line may have fewer)
    all_lines = []
    for i in range(0, len(words), WORDS_PER_LINE):
        line = " ".join(words[i:i + WORDS_PER_LINE])
        all_lines.append(_safe_text(line))

    # ── SHORT SCRIPT: display all lines continuously until end ──
    if len(words) <= SHORT_SCRIPT_THRESHOLD:
        filters = []
        short_start = minimum_start
        short_end = min(caption_end, speech_start + speech_duration)
        if short_end <= short_start:
            return ""
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
                f"box=1:boxcolor=black@0.42:boxborderw=14:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,{short_start:.2f},{short_end:.2f})'"
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

    if speech_duration <= 0:
        return ""

    total_spoken_words = sum(len(" ".join(block).split()) for block in blocks)
    filters = []
    elapsed_words = 0
    for block in blocks:
        block_words = len(" ".join(block).split())
        raw_start = speech_start + speech_duration * (
            elapsed_words / max(total_spoken_words, 1)
        )
        elapsed_words += block_words
        raw_end = speech_start + speech_duration * (
            elapsed_words / max(total_spoken_words, 1)
        )
        if raw_end <= minimum_start:
            continue
        t_start = max(raw_start, minimum_start)
        t_end = min(raw_end, caption_end)
        if t_end <= t_start:
            continue
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
                f"box=1:boxcolor=black@0.42:boxborderw=16:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
    return ",".join(filters)


def _build_end_screen_filter(
    total_dur,
    font_bold,
    font_regular,
    channel_name="",
    end_screen_duration: float = END_SCREEN_DURATION,
):
    if end_screen_duration <= 0:
        return ""
    t0 = total_dur - end_screen_duration
    eb = f"gte(t,{t0:.2f})"
    theme = _channel_theme(channel_name)
    accent = theme["accent"]
    safe_name = _safe_text(channel_name.upper())
    return ",".join([
        f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=black@0.88:t=fill:enable='{eb}'",
        f"drawbox=x={WIDTH}*0.18:y={HEIGHT}*0.39:w={WIDTH}*0.64:h=8:color={accent}:t=fill:enable='{eb}'",
        f"drawtext=fontfile='{font_bold}':text='{safe_name}':fontsize=76:fontcolor=white:borderw=5:bordercolor=black:x=(w-text_w)/2:y=(h-text_h)/2-90:enable='{eb}'",
        f"drawtext=fontfile='{font_bold}':text='SUBSCRIBE FOR MORE':fontsize=48:fontcolor={accent}:borderw=4:bordercolor=black:x=(w-text_w)/2:y=(h-text_h)/2+40:enable='{eb}'",
    ])


def _concat_seamless_scenes(
    resized: list[str],
    total: float,
    output_path: str,
    preserve_audio: bool = False,
) -> None:
    """Join equal-length scenes with normalized timestamps and no A/V gaps."""
    scene_duration = total / len(resized)
    inputs = []
    filters = []
    video_labels = []
    audio_labels = []
    for index, path in enumerate(resized):
        inputs.extend(["-i", path])
        video_label = f"v{index}"
        video_labels.append(f"[{video_label}]")
        source_duration = _dur(path)
        # A browser generator may return a clip longer than the assigned scene
        # window. Keep its newest final segment so earlier action is not repeated.
        trim_start = (
            max(source_duration - scene_duration, 0.0)
            if source_duration > scene_duration + 0.25
            else 0.0
        )
        filters.append(
            f"[{index}:v]fps=30,"
            f"tpad=stop_mode=clone:stop_duration={scene_duration:.3f},"
            f"trim=start={trim_start:.3f}:duration={scene_duration:.3f},"
            f"setpts=PTS-STARTPTS[{video_label}]"
        )
        if preserve_audio:
            if not _has_audio(path):
                raise RuntimeError(
                    f"Meta AI scene has no native audio stream: {path}"
                )
            audio_label = f"a{index}"
            audio_labels.append(f"[{audio_label}]")
            filters.append(
                f"[{index}:a]atrim=start={trim_start:.3f}:duration={scene_duration:.3f},"
                f"asetpts=PTS-STARTPTS,aresample=48000:async=1:first_pts=0,"
                f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"apad=pad_dur={scene_duration:.3f},"
                f"atrim=duration={scene_duration:.3f}[{audio_label}]"
            )

    if preserve_audio:
        interleaved = "".join(
            video + audio for video, audio in zip(video_labels, audio_labels)
        )
        filters.append(
            interleaved + f"concat=n={len(resized)}:v=1:a=1[outv][outa]"
        )
        maps_and_codecs = [
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(VIDEO_CRF),
            "-c:a", "aac", "-b:a", "320k",
        ]
    else:
        filters.append(
            "".join(video_labels) + f"concat=n={len(resized)}:v=1:a=0[outv]"
        )
        maps_and_codecs = [
            "-map", "[outv]", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(VIDEO_CRF),
        ]

    _ffmpeg(
        inputs + [
            "-filter_complex", ";".join(filters),
        ] + maps_and_codecs + [
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-t", f"{total:.3f}",
            output_path,
        ],
        "seamless_concat",
    )


def assemble_video(
    clip_paths,
    audio_path,
    script,
    output_filename,
    channel_name="",
    music_path=None,
    target_duration=None,
    end_screen_duration=None,
    seamless_scenes=False,
    native_clip_audio=False,
    show_overlays=True,
    opening_style="default",
    hook_sfx=None,
    hook_overlay="",
    hook_accent="",
    evidence_label="",
    require_visuals=False,
) -> str:
    """
    Assemble video with clips and audio.
    If music_path is provided, mixes voice (audio_path) with background music.
    If native_clip_audio is enabled, keeps each generated clip's own audio and
    refuses external voice/music replacement.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    out = os.path.join(OUTPUT_DIR, output_filename)

    end_duration = END_SCREEN_DURATION if end_screen_duration is None else float(end_screen_duration)
    ext_audio = None
    voice_duration = 0.0
    speech_start = 0.0
    if native_clip_audio:
        if audio_path or music_path:
            raise RuntimeError(
                "Native Meta audio mode cannot be combined with external voice or music."
            )
        if not seamless_scenes:
            raise RuntimeError("Native Meta audio requires seamless scene assembly.")
        missing_audio = [path for path in clip_paths if not _has_audio(path)]
        if missing_audio:
            raise RuntimeError(
                "One or more Meta AI scenes have no native audio; refusing to "
                "publish a silent or partly silent episode: " + ", ".join(missing_audio)
            )
        total = (
            float(target_duration)
            if target_duration
            else sum(_dur(path) for path in clip_paths)
        )
        print(f"[Assembler] Preserving Meta AI native voice across {total:.1f}s")
    else:
        if not audio_path:
            raise RuntimeError("External audio path is required when native audio is disabled.")
        voice_duration = _dur(audio_path)
        # Mix voice + music if music is provided
        if music_path and os.path.exists(music_path):
            mixed_audio = os.path.join(TEMP_DIR, "mixed_audio.mp3")
            audio_path = _mix_audio(audio_path, music_path, mixed_audio, music_volume=0.25)
            speech_start = 1.0

        # Escape audio path for Windows
        if sys.platform == "win32":
            audio_path = audio_path.replace("\\", "/").replace(":", "\\:", 1)

        a_dur = _dur(audio_path)
        total = float(target_duration) if target_duration else a_dur + end_duration

        # Pad or trim audio to the exact final duration.
        ext_audio = os.path.join(TEMP_DIR, "audio_ext.mp3")
        _ffmpeg(["-i", audio_path, "-af", f"apad=pad_dur={max(total - a_dur, 0):.3f}",
                 "-t", str(total), ext_audio], "ext_audio")
        if hook_sfx == "tech_glitch_boom":
            hooked_audio = os.path.join(TEMP_DIR, "audio_with_tech_hook.mp3")
            ext_audio = _add_tech_hook_sfx(ext_audio, total, hooked_audio)
        print(f"[Assembler] {a_dur:.1f}s audio -> exact {total:.1f}s video")

    # Resize clips to Full HD portrait
    resized = []
    for i, cp in enumerate(clip_paths):
        rp = os.path.join(TEMP_DIR, f"r_{i}.mp4")
        try:
            _resize(cp, rp)
            resized.append(rp)
        except Exception as e:
            print(f"[Assembler] Skip clip: {e}")

    if seamless_scenes and len(resized) != len(clip_paths):
        raise RuntimeError(
            "One or more generated scenes could not be normalized; refusing "
            "to assemble an incomplete continuity sequence."
        )

    if not resized:
        if require_visuals:
            raise RuntimeError(
                "No usable visual clips were downloaded; refusing to publish "
                "a black or visually empty episode."
            )
        black = os.path.join(TEMP_DIR, "black.mp4")
        _ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r=30:d={total}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", black], "black")
        resized = [black]

    # Concat clips to fill total duration. Browser-generated scenes use
    # normalized equal segments and reset timestamps, preventing black gaps.
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

    cr = os.path.join(TEMP_DIR, "cr.mp4")
    ct = os.path.join(TEMP_DIR, "ct.mp4")
    if seamless_scenes:
        _concat_seamless_scenes(
            resized, total, ct, preserve_audio=native_clip_audio
        )
    else:
        with open(cl, "w") as f:
            for rp in used:
                f.write(f"file '{os.path.abspath(rp)}'\n")
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", cl, "-c", "copy", cr], "concat")
        _ffmpeg(["-i", cr, "-t", str(total), "-c", "copy", ct], "trim")

    # Channel 3 uses clean Meta frames: no hook, captions, or end screen.
    vf = ""
    if show_overlays:
        fb = _resolve_font(True)
        fr = _resolve_font(False)
        if opening_style == "tech_evidence":
            hook_f = _build_tech_evidence_hook_filter(
                fb, hook_overlay, hook_accent, evidence_label
            )
            caption_minimum_start = 3.05
        else:
            hook_f = _build_hook_filter(fb, channel_name)
            caption_minimum_start = max(speech_start, 2.2)
        caption_f = _build_caption_filter(
            script,
            total,
            fb,
            end_duration,
            speech_start=speech_start,
            speech_duration=voice_duration,
            minimum_start=caption_minimum_start,
        )
        end_f = _build_end_screen_filter(total, fb, fr, channel_name, end_duration)
        parts = [p for p in [hook_f, caption_f, end_f] if p]
        vf = ",".join(parts)

    print(f"[Assembler] Rendering 2K {WIDTH}×{HEIGHT} (9:16) at {VIDEO_BITRATE/1000} Mbps CRF {VIDEO_CRF}...")
    if native_clip_audio and not vf:
        # The seamless concat is already normalized and encoded. Copying it
        # avoids another generation boundary and preserves its continuous A/V.
        shutil.copyfile(ct, out)
    else:
        render_inputs = ["-i", ct]
        audio_map = ["-map", "0:a:0"]
        if not native_clip_audio:
            render_inputs.extend(["-i", ext_audio])
            audio_map = ["-map", "1:a:0"]
        video_filter = ["-vf", vf] if vf else []
        _ffmpeg(render_inputs + video_filter +
                ["-map", "0:v:0"] + audio_map +
                ["-c:v", "libx264", "-preset", "medium", "-crf", str(VIDEO_CRF),
                 "-b:v", str(VIDEO_BITRATE), "-c:a", "aac", "-b:a", "320k",
                 "-pix_fmt", "yuv420p", "-t", str(total), "-r", "30", out],
                "render")

    print(f"[Assembler] Done -> {out} ({total:.0f}s)")
    return out
