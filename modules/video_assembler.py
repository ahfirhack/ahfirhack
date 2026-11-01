"""Offline FFmpeg assembler for five genuine Meta AI native-audio videos.

Does not download pictures, footage, audio, fonts or other resources. Scene
continuity must be present in the generated clips themselves; the assembler
never hides a bad handoff by replacing one frame or padding audio with silence.
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


def _audio_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "format=duration:stream=duration", "-of", "json",
         str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        info = json.loads(result.stdout) if result.returncode == 0 else {}
        stream = (info.get("streams") or [{}])[0]
        value = float(
            stream.get("duration") or info.get("format", {}).get("duration") or 0
        )
    except (ValueError, TypeError, IndexError, json.JSONDecodeError):
        value = 0.0
    if value <= 0:
        raise RuntimeError(f"Cannot read native audio duration from {path}")
    return value


def assemble_meta_short(
    clip_paths,
    output_filename: str,
    continuity_dir,
    scene_seconds: int = 10,
) -> str:
    """Assemble EXACTLY five native-audio Meta clips into one continuous Short.

    Generated frame handoffs are validated before assembly, then preserved
    exactly. A bad boundary fails closed instead of being concealed for one
    frame. If Meta's native audio track ends slightly early, only its final
    two-second reaction/ambience tail is time-fitted to the video. Dialogue
    timing stays intact and the former 0.2-second silent seam is eliminated.

    No third-party images, footage, overlays, soundtrack, subtitles, silence
    insertion, stock video or TTS is used.
    """
    from pathlib import Path
    from modules.meta_ai_generator import (
        _check_scene_handoff,
        _check_scene_unique,
        _extract_last_frame,
        _validate_meta_clip,
    )

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
    target_dir = Path(continuity_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    clips = [Path(item) for item in clip_paths]
    accepted = []
    previous_frame = None
    audio_durations = []
    for index, clip in enumerate(clips, start=1):
        _validate_meta_clip(clip)
        _check_scene_unique(accepted, clip)
        if previous_frame is not None:
            _check_scene_handoff(previous_frame, clip)
        frame = target_dir / f"scene_{index:02d}_assembler_last.png"
        _extract_last_frame(clip, frame)
        previous_frame = frame
        accepted.append(clip)
        audio_durations.append(_audio_duration(clip))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output = os.path.join(OUTPUT_DIR, output_filename)
    input_args = []
    for path in clips:
        input_args += ["-i", str(path)]

    filters = []
    segments = []
    for index in range(5):
        # fps before trim produces exactly 300 pictures (0..299), timestamps
        # start at zero so ffmpeg concat cannot introduce a blank scene gap.
        v = f"v{index}"
        filters.append(
            f"[{index}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},setsar=1,fps=30,trim=duration=10,"
            f"setpts=PTS-STARTPTS,format=yuv420p[{v}]"
        )
        a = f"a{index}"
        source_audio_seconds = audio_durations[index]
        audio_base = (
            f"[{index}:a]aresample=48000,"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
        )
        if source_audio_seconds < scene_seconds:
            # Prompts place speech before 7.5s. Preserve that timing and extend
            # only the native reaction/ambience tail instead of padding silence.
            tail_start = max(0.0, source_audio_seconds - 2.0)
            tail_source = source_audio_seconds - tail_start
            tail_target = scene_seconds - tail_start
            tempo = tail_source / tail_target
            if not 0.85 <= tempo <= 1.0:
                raise RuntimeError(
                    f"Scene {index + 1} native audio cannot be safely tail-fitted "
                    f"({source_audio_seconds:.3f}s)"
                )
            main_raw = f"a{index}mainraw"
            tail_raw = f"a{index}tailraw"
            main = f"a{index}main"
            tail = f"a{index}tail"
            filters.extend((
                f"{audio_base},asplit=2[{main_raw}][{tail_raw}]",
                f"[{main_raw}]atrim=start=0:end={tail_start:.6f},"
                f"asetpts=PTS-STARTPTS[{main}]",
                f"[{tail_raw}]atrim=start={tail_start:.6f}:"
                f"end={source_audio_seconds:.6f},asetpts=PTS-STARTPTS,"
                f"atempo={tempo:.9f},apad=pad_dur=0.03,"
                f"atrim=duration={tail_target:.6f},asetpts=PTS-STARTPTS[{tail}]",
                f"[{main}][{tail}]concat=n=2:v=0:a=1[{a}]",
            ))
        else:
            filters.append(
                f"{audio_base},atrim=duration=10,asetpts=PTS-STARTPTS[{a}]"
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
