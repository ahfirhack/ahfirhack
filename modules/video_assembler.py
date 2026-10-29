"""
video_assembler.py (v10 — fail-closed visuals and word-timed captions)
- 2K Quality 1440×2560, 9:16 vertical, 12 Mbps, CRF 16
- Large two-line captions use the narrator's real word boundaries
- Black, flat-color, and broadcast test-pattern inputs are rejected
- Visual hook in first 2s (stand-alone effect)
- Brief translucent CTA keeps the real footage visible
"""

import os
import sys
import subprocess
import random
import re
import shutil
import requests
import json
import statistics
from collections import Counter
from config import TEMP_DIR, OUTPUT_DIR, FONT_BASE_DIR, PREFERRED_FONTS, WINDOWS_FONT_PATHS, END_SCREEN_DURATION, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_BITRATE, VIDEO_CRF

# Use quality settings from config
WIDTH  = VIDEO_WIDTH   # 1440 (2K)
HEIGHT = VIDEO_HEIGHT # 2560 (2K)

# Short phrase blocks are easier to read on a phone than sentence paragraphs.
WORDS_PER_CAPTION = 4

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
        "caption_y_ratio": 0.69,
        "caption_fontsize": 78,
        "tagline": "CODE. POWER. CONSEQUENCES.",
        "hooks": (
            "THE EVIDENCE WAS DIGITAL",
            "THE CODE TOLD THE TRUTH",
            "THE NUMBERS DID NOT MATCH",
        ),
    },
    "storyfuse": {
        "accent": "0xFF5A36",
        "caption_y_ratio": 0.70,
        "caption_fontsize": 82,
        "tagline": "BIG STAKES. SHARP TWISTS. NO FILLER.",
        "hooks": (
            "THIS CHANGES EVERYTHING",
            "THE CHOICE WAS IMPOSSIBLE",
            "THEN THE TRUTH ARRIVED",
        ),
    },
    "stoic reset": {
        "accent": "0xE8B56A",
        "caption_y_ratio": 0.70,
        "caption_fontsize": 76,
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
    "caption_y_ratio": 0.70,
    "caption_fontsize": 76,
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


def _visual_quality_ok(path: str) -> bool:
    """Reject black, flat-color, and broadcast test-pattern source clips."""
    duration = _dur(path)
    if duration <= 0:
        print(f"[Assembler/VisualGuard] Unreadable clip rejected: {path}")
        return False
    frames = []
    for ratio in (0.20, 0.50, 0.80):
        result = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-ss", f"{duration * ratio:.3f}",
                "-i", path, "-frames:v", "1", "-vf", "scale=160:284",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
            ],
            capture_output=True,
        )
        expected = 160 * 284 * 3
        if result.returncode != 0 or len(result.stdout) < expected:
            print(f"[Assembler/VisualGuard] Frame extraction failed: {path}")
            return False
        frames.append(result.stdout[:expected])

    black_ratios = []
    saturation_ratios = []
    top_color_shares = []
    luminance_variances = []
    for frame in frames:
        pixels = [tuple(frame[index:index + 3]) for index in range(0, len(frame), 3)]
        luminance = [
            0.2126 * red + 0.7152 * green + 0.0722 * blue
            for red, green, blue in pixels
        ]
        quantized = Counter(
            (red // 32, green // 32, blue // 32)
            for red, green, blue in pixels
        )
        black_ratios.append(
            sum(max(pixel) < 24 for pixel in pixels) / len(pixels)
        )
        saturation_ratios.append(
            sum(max(pixel) - min(pixel) > 96 for pixel in pixels) / len(pixels)
        )
        top_color_shares.append(
            sum(count for _, count in quantized.most_common(8)) / len(pixels)
        )
        luminance_variances.append(statistics.pvariance(luminance))

    black_ratio = statistics.fmean(black_ratios)
    saturation_ratio = statistics.fmean(saturation_ratios)
    top_color_share = statistics.fmean(top_color_shares)
    luminance_variance = statistics.fmean(luminance_variances)
    rejected = (
        black_ratio > 0.75
        or luminance_variance < 90
        or top_color_share > 0.97
        or (saturation_ratio > 0.60 and top_color_share > 0.65)
    )
    print(
        f"[Assembler/VisualGuard] {os.path.basename(path)}: "
        f"black={black_ratio:.2f}, colors={top_color_share:.2f}, "
        f"saturation={saturation_ratio:.2f}, variance={luminance_variance:.0f} "
        f"-> {'REJECT' if rejected else 'PASS'}"
    )
    return not rejected


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
        f"[0:a]adelay=1000|1000,highpass=f=65,"
        f"acompressor=threshold=-18dB:ratio=2.5:attack=5:release=80,"
        f"volume=1.12[voice];"
        f"[1:a]volume={music_volume}[music];"
        f"[voice][music]amix=inputs=2:duration=first:weights=1 1,"
        f"loudnorm=I=-14:TP=-2.0:LRA=7[mixed]",
        "-map", "[mixed]",
        "-t", str(total_dur),
        "-c:a", "libmp3lame", "-b:a", "320k",
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
        "alimiter=limit=0.92:level=false[sfx]",
        "-map", "[sfx]", "-c:a", "pcm_s16le", sfx_path,
    ], "tech_hook_sfx")
    _ffmpeg([
        "-i", audio_path,
        "-i", sfx_path,
        "-filter_complex",
        "[0:a]volume=1[base];[1:a]volume=0.9[sfx];"
        "[base][sfx]amix=inputs=2:duration=first:dropout_transition=0,"
        "alimiter=limit=0.82:level=false[outa]",
        "-map", "[outa]", "-t", f"{total:.3f}",
        "-c:a", "libmp3lame", "-b:a", "320k", output_path,
    ], "mix_tech_hook_sfx")
    print("[Assembler] Added timestamp-zero tech glitch/sub-boom")
    return output_path


def _resize(inp, out):
    """Scale to 2K portrait 1440×2560, high quality."""
    _ffmpeg(["-i", inp,
             "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                    f"crop={WIDTH}:{HEIGHT},setsar=1",
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


def _build_suspense_hook_filter(
    font_bold: str,
    channel_name: str,
    hook_overlay: str,
    hook_accent: str,
) -> str:
    """Render an episode-specific two-second hook for StoryFuse/Stoic Reset."""
    theme = _channel_theme(channel_name)
    overlay = _safe_text(hook_overlay.upper())[:64] or random.choice(theme["hooks"])
    accent_text = _safe_text(hook_accent.upper())[:32] or "WATCH CLOSELY"
    tagline = _safe_text(theme["tagline"])
    words = overlay.split()
    if len(overlay) > 25 and len(words) > 1:
        split_at = min(
            range(1, len(words)),
            key=lambda index: abs(
                len(" ".join(words[:index])) - len(" ".join(words[index:]))
            ),
        )
        lines = [" ".join(words[:split_at]), " ".join(words[split_at:])]
    else:
        lines = [overlay]
    longest = max(len(line) for line in lines)
    headline_size = min(82, max(52, int(1180 / max(longest * 0.62, 1))))
    accent_size = 62 if len(accent_text) <= 18 else 48
    active = "lt(t,2.8)"
    pulse = "between(t,0,0.10)+between(t,0.75,0.84)+between(t,1.55,1.64)"
    filters = [
        f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=black@0.74:t=fill:enable='{active}'",
        f"drawbox=x=70:y={HEIGHT}*0.31:w={WIDTH}-140:h={HEIGHT}*0.34:color=black@0.38:t=fill:enable='{active}'",
        f"drawbox=x=70:y={HEIGHT}*0.31:w=12:h={HEIGHT}*0.34:color={theme['accent']}:t=fill:enable='{active}'",
        f"drawbox=x=0:y={HEIGHT}*0.27:w={WIDTH}:h=6:color={theme['accent']}@0.9:t=fill:enable='{pulse}'",
        f"drawtext=fontfile='{font_bold}':text='{accent_text}':fontsize={accent_size}:fontcolor={theme['accent']}:borderw=5:bordercolor=black:x=(w-text_w)/2:y={HEIGHT}*0.52:enable='{active}'",
        f"drawtext=fontfile='{font_bold}':text='{tagline}':fontsize=32:fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y={HEIGHT}*0.61:enable='{active}'",
    ]
    positions = [0.39] if len(lines) == 1 else [0.365, 0.415]
    for line, y_position in zip(lines, positions):
        filters.append(
            f"drawtext=fontfile='{font_bold}':text='{line}':fontsize={headline_size}:"
            f"fontcolor=white:borderw=8:bordercolor=black:shadowx=5:shadowy=5:"
            f"shadowcolor=black@0.8:x=(w-text_w)/2:y={HEIGHT}*{y_position}:"
            f"enable='{active}'"
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
    channel_name: str = "",
    word_timing_path: str = "",
) -> str:
    """Build large phrase captions from Edge TTS's real word boundaries."""
    theme = _channel_theme(channel_name)
    accent = theme["accent"]
    caption_fontsize = int(theme["caption_fontsize"])
    caption_line_height = caption_fontsize + 18
    caption_center_y = int(HEIGHT * float(theme["caption_y_ratio"]))
    caption_end = max(0.0, total_dur - end_screen_duration)
    speech_start = max(0.0, speech_start)
    minimum_start = speech_start if minimum_start is None else max(
        speech_start, minimum_start
    )
    if speech_duration is None or speech_duration <= 0:
        speech_duration = max(0.0, caption_end - speech_start)
    speech_duration = min(speech_duration, max(0.0, caption_end - speech_start))
    if speech_duration <= 0:
        return ""

    timed_words = []
    if word_timing_path and os.path.exists(word_timing_path):
        try:
            with open(word_timing_path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    item = json.loads(raw_line)
                    if item.get("type") != "WordBoundary":
                        continue
                    text = _safe_text(str(item.get("text", "")).strip())
                    if not text:
                        continue
                    timed_words.append({
                        "text": text,
                        "start": float(item["offset"]) / 10_000_000,
                        "end": float(item["offset"] + item["duration"]) / 10_000_000,
                    })
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"[Assembler] Ignoring invalid word timings: {error}")
            timed_words = []

    # Deepgram and older cached audio have no boundary sidecar. Retain a clean
    # estimated fallback for those channels, while Channels 1/2 require the
    # sidecar at voice generation time.
    if not timed_words:
        words = [_safe_text(word) for word in script.split() if _safe_text(word)]
        step = speech_duration / max(len(words), 1)
        timed_words = [
            {"text": word, "start": index * step, "end": (index + 1) * step}
            for index, word in enumerate(words)
        ]
    if not timed_words:
        return ""

    # Restore punctuation-aware phrase boundaries from the original script.
    # Edge returns exact timing but deliberately omits punctuation in its word
    # events, so grouping raw events alone can join two different sentences.
    script_tokens = script.split()
    if len(script_tokens) == len(timed_words):
        for item, token in zip(timed_words, script_tokens):
            cleaned = _safe_text(token).strip(".,!?()—-")
            if cleaned:
                item["text"] = cleaned
            item["break_after"] = bool(re.search(r"[.!?;:]\s*$", token))
    else:
        sentence_counts = [
            len(sentence.split())
            for sentence in re.split(r"(?<=[.!?;:])\s+", script.strip())
            if sentence.strip()
        ]
        consumed = 0
        total_script_words = max(sum(sentence_counts), 1)
        for count in sentence_counts[:-1]:
            consumed += count
            boundary = round(consumed / total_script_words * len(timed_words)) - 1
            if 0 <= boundary < len(timed_words):
                timed_words[boundary]["break_after"] = True

    sentences = []
    sentence = []
    for word in timed_words:
        sentence.append(word)
        if word.get("break_after"):
            sentences.append(sentence)
            sentence = []
    if sentence:
        sentences.append(sentence)

    cues = []
    for sentence in sentences:
        group_count = max(1, (len(sentence) + WORDS_PER_CAPTION - 1) // WORDS_PER_CAPTION)
        base_size, extra = divmod(len(sentence), group_count)
        start = 0
        for group_index in range(group_count):
            size = base_size + (1 if group_index < extra else 0)
            cues.append(sentence[start:start + size])
            start += size

    filters = []
    for cue_index, cue in enumerate(cues):
        raw_start = speech_start + cue[0]["start"]
        next_start = (
            speech_start + cues[cue_index + 1][0]["start"]
            if cue_index + 1 < len(cues)
            else speech_start + min(speech_duration, cue[-1]["end"] + 0.22)
        )
        raw_end = max(speech_start + cue[-1]["end"], next_start)
        if raw_end <= minimum_start:
            continue
        t_start = max(raw_start, minimum_start)
        t_end = min(raw_end, caption_end)
        if t_end <= t_start:
            continue

        words = [item["text"].upper() for item in cue]
        if len(words) <= 2:
            lines = [" ".join(words)]
        else:
            split_at = min(
                range(1, len(words)),
                key=lambda index: abs(
                    len(" ".join(words[:index])) - len(" ".join(words[index:]))
                ),
            )
            lines = [" ".join(words[:split_at]), " ".join(words[split_at:])]

        block_height = len(lines) * caption_line_height + 56
        box_y = caption_center_y - block_height // 2
        enable = f"between(t,{t_start:.3f},{t_end:.3f})"
        filters.extend([
            f"drawbox=x=70:y={box_y}:w={WIDTH}-140:h={block_height}:"
            f"color=black@0.72:t=fill:enable='{enable}'",
            f"drawbox=x=70:y={box_y}:w={WIDTH}-140:h=7:"
            f"color={accent}@0.98:t=fill:enable='{enable}'",
        ])
        text_y = box_y + 24
        for line_index, line in enumerate(lines):
            color = accent if len(lines) > 1 and line_index == 1 else "white"
            filters.append(
                f"drawtext=fontfile='{font_bold}':text='{line}':"
                f"fontsize={caption_fontsize}:fontcolor={color}:"
                f"borderw=6:bordercolor=black@0.95:shadowx=4:shadowy=4:"
                f"shadowcolor=black@0.75:x=(w-text_w)/2:"
                f"y={text_y + line_index * caption_line_height}:"
                f"enable='{enable}'"
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
        f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=black@0.55:t=fill:enable='{eb}'",
        f"drawbox=x={WIDTH}*0.18:y={HEIGHT}*0.39:w={WIDTH}*0.64:h=8:color={accent}:t=fill:enable='{eb}'",
        f"drawtext=fontfile='{font_bold}':text='{safe_name}':fontsize=76:fontcolor=white:borderw=5:bordercolor=black:x=(w-text_w)/2:y=(h-text_h)/2-90:enable='{eb}'",
        f"drawtext=fontfile='{font_bold}':text='SUBSCRIBE FOR MORE':fontsize=48:fontcolor={accent}:borderw=4:bordercolor=black:x=(w-text_w)/2:y=(h-text_h)/2+40:enable='{eb}'",
    ])


def _concat_seamless_scenes(
    resized: list[str],
    total: float,
    output_path: str,
    preserve_audio: bool = False,
    use_tail: bool = True,
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
            if use_tail and source_duration > scene_duration + 0.25
            else 0.0
        )
        filters.append(
            f"[{index}:v]fps=30,setsar=1,"
            f"tpad=stop_mode=clone:stop_duration={scene_duration:.3f},"
            f"trim=start={trim_start:.3f}:duration={scene_duration:.3f},"
            f"setpts=PTS-STARTPTS[{video_label}]"
        )
        if preserve_audio:
            if not _has_audio(path):
                raise RuntimeError(
                    f"Generated scene has no embedded audio stream: {path}"
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
    align_visual_beats=False,
    reject_synthetic_visuals=False,
    require_word_timestamps=False,
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
    word_timing_path = f"{audio_path}.words.jsonl" if audio_path else ""
    if native_clip_audio:
        if audio_path or music_path:
            raise RuntimeError(
                "Generated-scene audio cannot be combined with external voice or music."
            )
        if not seamless_scenes:
            raise RuntimeError("Generated-scene audio requires seamless scene assembly.")
        missing_audio = [path for path in clip_paths if not _has_audio(path)]
        if missing_audio:
            raise RuntimeError(
                "One or more generated scenes have no embedded audio; refusing to "
                "publish a silent or partly silent episode: " + ", ".join(missing_audio)
            )
        total = (
            float(target_duration)
            if target_duration
            else sum(_dur(path) for path in clip_paths)
        )
        print(f"[Assembler] Preserving generated scene audio across {total:.1f}s")
    else:
        if not audio_path:
            raise RuntimeError("External audio path is required when native audio is disabled.")
        if require_word_timestamps and not os.path.exists(word_timing_path):
            raise RuntimeError(
                "Synchronized captions require the voice word-boundary sidecar; "
                "upload stopped instead of estimating caption timing."
            )
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
            if reject_synthetic_visuals and not _visual_quality_ok(cp):
                print(f"[Assembler] Rejected synthetic/empty visual: {cp}")
                continue
            _resize(cp, rp)
            resized.append(rp)
        except Exception as e:
            print(f"[Assembler] Skip clip: {e}")

    if seamless_scenes and len(resized) != len(clip_paths):
        raise RuntimeError(
            "One or more generated scenes could not be normalized; refusing "
            "to assemble an incomplete continuity sequence."
        )

    if align_visual_beats and len(resized) != 3:
        raise RuntimeError(
            "Narrative visual alignment requires exactly three usable clips "
            "(hook, escalation, payoff)."
        )

    if not resized:
        raise RuntimeError(
            "No photographic or generated scene passed visual validation; "
            "refusing to publish a black, solid-color, or test-pattern video."
        )

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
    elif align_visual_beats:
        _concat_seamless_scenes(
            resized, total, ct, preserve_audio=False, use_tail=False
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
        elif opening_style in {"story_suspense", "stoic_suspense"}:
            hook_f = _build_suspense_hook_filter(
                fb, channel_name, hook_overlay, hook_accent
            )
            caption_minimum_start = max(speech_start, 2.8)
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
            channel_name=channel_name,
            word_timing_path=word_timing_path,
        )
        end_f = _build_end_screen_filter(total, fb, fr, channel_name, end_duration)
        parts = [p for p in [hook_f, caption_f, end_f] if p]
        vf = ",".join(parts)

    print(
        f"[Assembler] Rendering {WIDTH}×{HEIGHT} (9:16) at "
        f"{VIDEO_BITRATE / 1_000_000:.1f} Mbps CRF {VIDEO_CRF}..."
    )
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
