"""
voiceover.py (v6 — ElevenLabs + Deepgram TTS)
Generates MP3 voiceover using ElevenLabs API with Deepgram fallback.
Simple, reliable, high-quality voices.
"""

import os
import requests
import subprocess
from config import ELEVENLABS_API_KEY, DEEPGRAM_API_KEY

# Voice options by style (ElevenLabs voice IDs)
VOICE_STYLES = {
    "surprising": ["21m00Tcm4TlvDq8ikWAM", "EXAVITQu4vr4xnSDxMaL"],  # Adam, Rachel
    "suspenseful": ["AZnzlk1XvdvUeBnXmlld", "D38z5RkW3weJP6r1Fqow"],  # Fin, Thomas
    "helpful": ["EXAVITQu4vr4xnSDxMaL", "MF3mGyEYCl7XYWbV9V6O"],  # Rachel, Charlie
    "default": ["21m00Tcm4TlvDq8ikWAM", "EXAVITQu4vr4xnSDxMaL", "AZnzlk1XvdvUeBnXmlld"],
    "channel_1": "aura-2-zeus-en",    # Karma/Revenge: Deep, commanding, and dramatic.
    "channel_2": "aura-2-orpheus-en", # History Mystery: Authoritative, "discovery-channel" vibe.
    "channel_3": "aura-2-atlas-en",   # Digital/Home Hacks: Friendly, energetic, and helpful.
    "channel_4": "aura-2-odysseus-en",# Modern Stoic: Calm, steady, and philosophical.
    
    # Fallback/General styles
    "surprising": "aura-2-zeus-en",
    "suspenseful": "aura-2-orpheus-en",
    "helpful": "aura-2-atlas-en",
    "default": "aura-2-zeus-en"
}

# Deepgram model for fallback
DEEPGRAM_MODEL = "aura-2-odysseus-en"


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


def _generate_elevenlabs(script: str, voice_id: str, output_path: str) -> bool:
    """Generate voiceover using ElevenLabs API."""
    if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY == "YOUR_ELEVENLABS_API_KEY_HERE":
        return False

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    data = {
        "text": script,
        "model_id": ("eleven_multilingual_v2","eleven_flash_v2_5"),
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        }
    }

    try:
        response = requests.post(url, json=data, headers=headers, timeout=60)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        duration = _get_duration(output_path)
        print(f"[Voiceover/ElevenLabs] Generated {duration:.1f}s audio")
        return True

    except Exception as e:
        print(f"[Voiceover/ElevenLabs] Error: {e}")
        return False


def _generate_deepgram(script: str, output_path: str) -> bool:
    """Generate voiceover using Deepgram API (fallback)."""
    if not DEEPGRAM_API_KEY or DEEPGRAM_API_KEY == "YOUR_DEEPGRAM_API_KEY_HERE":
        return False

    url = f"https://api.deepgram.com/v1/speak?model={DEEPGRAM_MODEL}"
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
        print(f"[Voiceover/Deepgram] Generated {duration:.1f}s audio")
        return True

    except Exception as e:
        print(f"[Voiceover/Deepgram] Error: {e}")
        return False


def generate_voiceover(script: str, output_path: str, voice_style: str = None, voice_index: int = None) -> str:
    """
    Converts script text to MP3 voiceover.
    Tries ElevenLabs first, falls back to Deepgram.

    Args:
        script: Text to convert to speech
        output_path: Path to save the MP3 file
        voice_style: 'surprising', 'suspenseful', 'helpful', or None for default
        voice_index: Index of voice to use from the style list

    Returns:
        Path to generated MP3 file
    """
    # Ensure output directory exists
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Get voices for the style
    if voice_style and voice_style in VOICE_STYLES:
        voices = VOICE_STYLES[voice_style]
    else:
        voices = VOICE_STYLES["default"]

    # Select voice
    if voice_index is not None:
        voice_id = voices[voice_index % len(voices)]
    else:
        voice_id = voices[0]

    print(f"[Voiceover] Generating with style: {voice_style or 'default'}, voice: {voice_id}")

    # Try ElevenLabs first
    if _generate_elevenlabs(script, voice_id, output_path):
        return output_path

    # Fallback to Deepgram
    if _generate_deepgram(script, output_path):
        return output_path

    # If both fail, raise error
    raise RuntimeError(
        "Voiceover generation failed. "
        "Please check your ELEVENLABS_API_KEY or DEEPGRAM_API_KEY in config.py"
    )
