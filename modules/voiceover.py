"""
voiceover.py (v8 — locked channel voices plus word boundaries)
Generates MP3 narration with channel-specific delivery. Channels 1 and 2 use
locked Edge voices and save exact word timings for synchronized captions.
"""

import os
import json
import requests
import subprocess
import asyncio
import edge_tts
from config import DEEPGRAM_API_KEY, CHANNEL_VOICES, EDGE_VOICES, EDGE_VOICE_SETTINGS

# Deepgram models for each channel theme
DEEPGRAM_MODELS = {
    "channel_1": "aura-2-zeus-en",      # Tech crime: Deep, urgent, investigative
    "channel_2": "aura-2-orpheus-en",   # Storytelling: Authoritative, cinematic tension
    "channel_3": "aura-2-atlas-en",     # Kids history: Friendly, energetic storyteller
    "channel_4": "aura-odysseus-en",    # Stoic: Calm, steady, philosophical
}


def _get_duration(path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True,
        )
        return float(r.stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        return 0.0


def _generate_deepgram(script: str, model: str, output_path: str) -> bool:
    """Generate voiceover using Deepgram API."""
    if not DEEPGRAM_API_KEY or DEEPGRAM_API_KEY == "YOUR_DEEPGRAM_API_KEY_HERE":
        return False

    url = f"https://api.deepgram.com/v1/speak?model={model}"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {"text": script}

    try:
        response = requests.post(url, json=data, headers=headers, timeout=60)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        duration = _get_duration(output_path)
        print(f"[Voiceover/Deepgram] Generated {duration:.1f}s audio with model: {model}")
        return True

    except Exception as e:
        print(f"[Voiceover/Deepgram] Error: {e}")
        return False


def _generate_edge_tts(
    script: str,
    voice: str,
    output_path: str,
    settings: dict | None = None,
    require_timestamps: bool = False,
) -> bool:
    """Generate voice plus word-boundary metadata using free Edge TTS."""
    try:
        profile = settings or {}
        metadata_path = output_path + ".words.jsonl"

        async def _synthesize():
            communicate = edge_tts.Communicate(
                script,
                voice,
                rate=profile.get("rate", "+0%"),
                pitch=profile.get("pitch", "+0Hz"),
                volume=profile.get("volume", "+0%"),
                boundary="WordBoundary",
            )
            await communicate.save(output_path, metadata_path)

        asyncio.run(_synthesize())
        duration = _get_duration(output_path)
        boundaries = 0
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        if json.loads(line).get("type") == "WordBoundary":
                            boundaries += 1
                    except (json.JSONDecodeError, TypeError):
                        continue
        minimum_boundaries = max(3, int(len(script.split()) * 0.65))
        if require_timestamps and boundaries < minimum_boundaries:
            raise RuntimeError(
                f"Edge TTS returned only {boundaries} word boundaries; "
                f"need at least {minimum_boundaries} for synchronized captions."
            )
        print(
            f"[Voiceover/EdgeTTS] Generated {duration:.1f}s audio with voice: "
            f"{voice} ({boundaries} timed words)"
        )
        return True

    except Exception as e:
        print(f"[Voiceover/EdgeTTS] Error: {e}")
        return False


def generate_voiceover(
    script: str,
    output_path: str,
    channel_id: str = None,
    strict_voice: bool = False,
    voice_provider: str | None = None,
    require_timestamps: bool = False,
) -> str:
    """
    Converts script text to MP3 voiceover.
    Uses channel-specific voice from Deepgram, falls back to Edge TTS.

    Args:
        script: Text to convert to speech
        output_path: Path to save the MP3 file
        channel_id: Channel ID to select appropriate voice (e.g., "channel_1")

    Returns:
        Path to generated MP3 file
    """
    # Ensure output directory exists
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Get channel-specific voice
    if channel_id and channel_id in DEEPGRAM_MODELS:
        deepgram_model = DEEPGRAM_MODELS[channel_id]
        edge_voice = EDGE_VOICES.get(channel_id, "en-US-GuyNeural")
    else:
        deepgram_model = DEEPGRAM_MODELS.get("channel_1", "aura-2-zeus-en")
        edge_voice = EDGE_VOICES.get("channel_1", "en-US-GuyNeural")
    edge_settings = EDGE_VOICE_SETTINGS.get(channel_id or "channel_1", {})

    print(f"[Voiceover] Generating for {channel_id or 'default'} | Deepgram: {deepgram_model} | Edge: {edge_voice}")

    if voice_provider == "edge":
        if _generate_edge_tts(
            script,
            edge_voice,
            output_path,
            settings=edge_settings,
            require_timestamps=require_timestamps,
        ):
            return output_path
        raise RuntimeError(
            f"Locked Edge voice generation failed for {channel_id or 'default'} "
            f"({edge_voice}); refusing to substitute a different voice."
        )

    # Try Deepgram first
    if _generate_deepgram(script, deepgram_model, output_path):
        return output_path

    # Character-led channels must never switch voices between episodes.
    if strict_voice:
        raise RuntimeError(
            f"Locked voice generation failed for {channel_id or 'default'} "
            f"({deepgram_model}); refusing to substitute a different voice."
        )

    # Fallback to Edge TTS
    if _generate_edge_tts(
        script,
        edge_voice,
        output_path,
        settings=edge_settings,
        require_timestamps=require_timestamps,
    ):
        return output_path

    # If both fail, raise error
    raise RuntimeError(
        "Voiceover generation failed. "
        "Please check your DEEPGRAM_API_KEY in config.py"
    )
