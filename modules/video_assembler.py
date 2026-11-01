"""Offline FFmpeg assembler for five genuine Meta AI native-audio videos.

Does not download pictures, footage, audio, fonts or other resources.
The only inputs are five generated .mp4 files and their extracted handoff
PNG frames, all produced from those same clips.
"""

import json
import os
import subprocess
from config import OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_CRF

WIDTH = VIDEO_WIDTH
HEIGHT = VIDEO_HEIGHT


def _ffmpeg(args, label=""):
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error"] + list(args),
        capture_output=True, text=True, timeout=1800,
    )
    if result.returncode:
        raise RuntimeError(f"FFmpeg {label} failed: {result.stderr[-2500:]}")


def _dur(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(result.stdout.strip()) if result.returncode == 0 else 0.0
    except ValueError:
        return 0.0


def _has_audio(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_type", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode == 0 and any(
        stream.get("codec_type") == "audio"
        for stream in json.loads(result.stdout).get("streams", [])
    )


def _dimensions(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        return 0, 0
    try:
        stream = (json.loads(result.stdout).get("streams") or [{}])[0]
        return int(stream.get("width") or 0), int(stream.get("height") or 0)
    except (ValueError, TypeError, IndexError, json.JSONDecodeError):
        return 0, 0


def assemble_meta_short(
    clip_paths,
    output_filename: str,
    continuity_dir,
    scene_seconds: int = 10,
) -> str:
    """Assemble EXACTLY five native-audio Meta clips into one continuous Short.

    The preceding clip's actual frame 299 is reused at frame 0 of the next
    segment (no insertion or added duration). This guarantees a visually
    matched frame, subject to normal H.264 re-encoding differences; the Meta
    reference-image prompting is what makes subsequent motion coherent.

    No third-party images, footage, overlays, soundtrack, subtitles, silence
    insertion beyond a possible codec tail <0.2s, stock video or TTS is used.
    """
    from pathlib import Path
    from modules.meta_ai_generator import _extract_last_frame, _validate_meta_clip

    if not isinstance(clip_paths, (list, tuple)) or len(clip_paths) != 5:
        raise RuntimeError("Meta-only Short needs exactly five 10-second clips")
    if scene_seconds != 10:
        raise RuntimeError("Meta-only duration policy needs 10 seconds per clip")
    if WIDTH < 1080 or HEIGHT < 1920:
        raise RuntimeError(
            f"Final output resolution must be at least 1080x1920, got {WIDTH}x{HEIGHT}"
        )
    if os.path.basename(output_filename) != output_filename or not output_filename.endswith(".mp4"):
        raise RuntimeError("Output must be a single filename ending .mp4")
    for item in clip_paths:
        _validate_meta_clip(Path(item))

    target_dir = Path(continuity_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    handoffs = []
    for index, clip in enumerate(clip_paths[:-1], start=1):
        # Derive the exact last frame with the SAME scale/fps/trim filter used
        # for final rendering. No image sources are downloaded or generated.
        frame = target_dir / f"scene_{index:02d}_assembler_last.png"
        _extract_last_frame(Path(clip), frame)
        handoffs.append(frame)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output = os.path.join(OUTPUT_DIR, output_filename)
    input_args = []
    for path in clip_paths:
        input_args += ["-i", str(path)]
    for image in handoffs:
        input_args += ["-loop", "1", "-framerate", "30", "-t", "10", "-i", str(image)]

    filters = []
    segments = []
    for index in range(5):
        # fps before trim produces exactly 300 pictures (0..299), timestamps
        # start at zero so ffmpeg concat cannot introduce a blank scene gap.
        base = f"v{index}base"
        filters.append(
            f"[{index}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},setsar=1,fps=30,trim=duration=10,"
            f"setpts=PTS-STARTPTS,format=yuv420p[{base}]"
        )
        v = f"v{index}"
        if index:
            # The attached prior-frame image replaces the *existing* initial
            # frame, does not prepend a new frame or create a hold/gap.
            image_input = 5 + index - 1
            filters.append(
                f"[{base}][{image_input}:v]overlay=0:0:"
                f"enable='eq(n,0)':eof_action=repeat:shortest=1:format=auto,"
                f"format=yuv420p[{v}]"
            )
        else:
            filters.append(f"[{base}]null[{v}]")
        a = f"a{index}"
        filters.append(
            f"[{index}:a]aresample=48000:async=1:first_pts=0,"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"apad=pad_dur=0.2,atrim=duration=10,asetpts=PTS-STARTPTS[{a}]"
        )
        segments.append(f"[{v}][{a}]")
    filters.append("".join(segments) + "concat=n=5:v=1:a=1[outv][outa]")
    _ffmpeg(
        input_args + [
            "-filter_complex", ";".join(filters),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(VIDEO_CRF),
            "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "30000",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-t", "50", "-movflags", "+faststart", output,
        ],
        "meta_only_5x10_seamless",
    )
    if not os.path.isfile(output) or os.path.getsize(output) < 10000:
        raise RuntimeError("The Meta-only Short was not produced")
    duration = _dur(output)
    width, height = _dimensions(output)
    if (not 49.9 <= duration <= 50.1 or not _has_audio(output)
            or width < 1080 or height < 1920):
        os.remove(output)
        raise RuntimeError(
            f"Assembled Short failed duration/audio/resolution QA "
            f"({duration:.3f}s, {width}x{height}); "
            "no incomplete or silent upload permitted"
        )
    print(
        f"[Assembler] Meta-only 5x10sec output: {output} "
        f"({duration:.3f}s, {width}x{height})"
    )
    return output
