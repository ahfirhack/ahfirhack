"""
voiceover.py (v7 — Channel-Specific Voices, Deepgram + Edge TTS)
Generates MP3 voiceover using Deepgram API with Edge TTS fallback.
Each channel has its own voice matching the theme.
"""

import os
import requests
import subprocess
import asyncio
import edge_tts
from config import DEEPGRAM_API_KEY, CHANNEL_VOICES, EDGE_VOICES

# Deepgram models for each channel theme
DEEPGRAM_MODELS = {
    "channel_1": "aura-2-zeus-en",      # Psychology: Deep, commanding, dramatic
    "channel_2": "aura-2-orpheus-en",   # History: Authoritative, discovery-channel vibe
    "channel_3": "aura-2-atlas-en",     # Declutter: Friendly, energetic, helpful
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


def _generate_edge_tts(script: str, voice: str, output_path: str) -> bool:
    """Generate voiceover using Edge TTS (free, no key required)."""
    try:
        async def _synthesize():
            communicate = edge_tts.Communicate(script, voice, rate="+0%")
            await communicate.save(output_path)

        asyncio.run(_synthesize())
        duration = _get_duration(output_path)
        print(f"[Voiceover/EdgeTTS] Generated {duration:.1f}s audio with voice: {voice}")
        return True

    except Exception as e:
        print(f"[Voiceover/EdgeTTS] Error: {e}")
        return False


def generate_voiceover(script: str, output_path: str, channel_id: str = None) -> str:
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

    print(f"[Voiceover] Generating for {channel_id or 'default'} | Deepgram: {deepgram_model} | Edge: {edge_voice}")

    # Try Deepgram first
    if _generate_deepgram(script, deepgram_model, output_path):
        return output_path

    # Fallback to Edge TTS
    if _generate_edge_tts(script, edge_voice, output_path):
        return output_path

    # If both fail, raise error
    raise RuntimeError(
        "Voiceover generation failed. "
        "Please check your DEEPGRAM_API_KEY in config.py"
    )
