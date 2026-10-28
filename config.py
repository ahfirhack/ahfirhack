# YouTube Multi-Channel Automation — API Keys & Settings

import os

# Number of videos to generate per run
NUM_VIDEOS = 1

# Upload to YouTube after generation
UPLOAD_TO_YOUTUBE = True

# Upload every 8 hours (in seconds)
UPLOAD_INTERVAL_HOURS = 8
UPLOAD_INTERVAL_SECONDS = UPLOAD_INTERVAL_HOURS * 3600

# ═══════════════════════════════════════════════════════
# AI / SCRIPT GENERATION
# ═══════════════════════════════════════════════════════
NOVA_API_KEY       = os.getenv("NOVA_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
CLAUDE_API_KEY     = os.getenv("CLAUDE_API_KEY", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", CLAUDE_API_KEY)
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEEPGRAM_API_KEY   = os.getenv("DEEPGRAM_API_KEY", "")

# Amazon Bedrock (AWS)
AMAZON_ACCESS_KEY = os.getenv("AMAZON_ACCESS_KEY", "")
AMAZON_SECRET_KEY = os.getenv("AMAZON_SECRET_KEY", "")
AMAZON_REGION     = os.getenv("AMAZON_REGION", "us-east-1")
# ═══════════════════════════════════════════════════════
# STOCK MEDIA
# ═══════════════════════════════════════════════════════
PEXELS_API_KEY        = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY       = os.getenv("PIXABAY_API_KEY", "")
COVERR_API_KEY        = os.getenv("COVERR_API_KEY", "")
VIDEEZY_CLIENT_ID     = os.getenv("VIDEEZY_CLIENT_ID", "")
VIDEEZY_CLIENT_SECRET = os.getenv("VIDEEZY_CLIENT_SECRET", "")
YOUTUBE_API_KEY       = os.getenv("YOUTUBE_API_KEY", "")
JAMENDO_CLIENT_ID     = os.getenv("JAMENDO_CLIENT_ID", "")
FREESOUND_API_KEY     = os.getenv("FREESOUND_API_KEY", "")

USED_VIDEOS_FILE   = "used_videos.json"
USED_SCRIPTS_FILE  = "used_scripts.json"
MUSIC_CACHE_DIR    = "music_cache"
META_AI_JOBS_DIR = os.getenv("META_AI_JOBS_DIR", "meta_ai_jobs")
META_AI_CREATE_URL = os.getenv("META_AI_CREATE_URL", "https://meta.ai/create")
META_AI_CHROME_PROFILE_DIR = os.getenv("META_AI_CHROME_PROFILE_DIR", "")
META_AI_CHARACTER_IMAGE = os.getenv("META_AI_CHARACTER_IMAGE", "")
META_AI_BROWSER_CHANNEL = os.getenv("META_AI_BROWSER_CHANNEL", "chromium")
META_AI_HEADLESS = os.getenv("META_AI_HEADLESS", "false").lower() in {"1", "true", "yes"}
META_AI_TIMEOUT_SECONDS = int(os.getenv("META_AI_TIMEOUT_SECONDS", "900"))
META_AI_MAX_RETRIES = int(os.getenv("META_AI_MAX_RETRIES", "2"))
META_SCENE_COUNT = 3
META_SCENE_DURATION = 10



# ── FONT ─────────────────────────────────────────────────
FONT_BASE_DIR    = "fonts"
PREFERRED_FONTS  = ["Montserrat-Bold", "Lato-Bold", "Raleway-Bold"]
WINDOWS_FONT_PATHS = {
    "Montserrat-Bold": "C\\:/Windows/Fonts/Montserrat-Bold.ttf",
    "Lato-Bold":       "C\\:/Windows/Fonts/Lato-Bold.ttf",
    "Raleway-Bold":    "C\\:/Windows/Fonts/Raleway-Bold.ttf",
    "_fallback":       "C\\:/Windows/Fonts/arial.ttf",
}

# ── END SCREEN ───────────────────────────────────────────
END_SCREEN_DURATION = 4   # reduced from 5 — every second of dead time kills completion rate

# ── VIDEO QUALITY ───────────────────────────────────────────
# Higher than Full HD for better quality
VIDEO_WIDTH  = 1440  # 2K width (better than 1080)
VIDEO_HEIGHT = 2560  # 2K height (better than 1920)
VIDEO_BITRATE = 12000  # 12 Mbps for higher quality
VIDEO_CRF     = 16     # Lower CRF = higher quality

# ── CHANNEL-SPECIFIC VOICE SETTINGS ───────────────────────
# Using Deepgram models for each channel theme
CHANNEL_VOICES = {
    "channel_1": "aura-2-zeus-en",      # Psychology: Deep, commanding, dramatic
    "channel_2": "aura-2-orpheus-en",   # History: Authoritative, discovery-channel vibe
    "channel_3": "aura-2-atlas-en",     # Kids history: Friendly, energetic storyteller
    "channel_4": "aura-odysseus-en",    # Stoic: Calm, steady, philosophical
}

# Edge TTS fallback voices (if Deepgram fails)
EDGE_VOICES = {
    "channel_1": "en-US-GuyNeural",      # Male, energetic
    "channel_2": "en-GB-RyanNeural",      # Male, British, serious
    "channel_3": "en-US-GuyNeural",       # Milo: fixed energetic male narrator
    "channel_4": "en-US-ChristopherNeural", # Male, deep, authoritative
}

# ── ALGORITHM-OPTIMIZED SCHEDULE ─────────────────────────
# Sweet spot: 30-45 second Shorts get highest completion rates.
# 13s and 60s are also proven high performers.
# Target 35s voiceover + 4s end screen = ~39s total (under 60s sweet spot)
VIDEOS_PER_CHANNEL_PER_DAY  = 1
SHORT_DURATION_TARGET        = 30   # seconds — voiceover/music length (NOT total)
VIDEO_DURATION_TARGET        = SHORT_DURATION_TARGET
OUTPUT_DIR                   = "output_videos"
TEMP_DIR                     = "temp"

# Upload 1-2 hours before peak audience time (algorithm tests early viewers)
# Peak times: US audience 6-9 PM EST → upload at 4-5 PM EST
UPLOAD_HOUR_UTC = 6   # 21:00 UTC = 5:00 PM EST = 2:00 PM PST

# ── CHANNELS ─────────────────────────────────────────────
CHANNELS = [
    {
        "id": "channel_1",
        "name": "Psychology & Human Behavior", # Fast viral potential, broad audience
        "niche": "Psychology facts, human behavior patterns, mind tricks, social psychology, and cognitive biases explained simply",
        "keywords": ["psychology", "human behavior", "mind tricks", "social psychology", "cognitive bias", "psychology facts"],
        "client_secrets_file": "credentials/channel1_secrets.json",
        "token_file": "credentials/channel1_token.json",
        "use_voice": True,
        "music_mood": "suspenseful",
        "category_id": "27",
        "hook_style": "surprising",
        "script_type": "educational",
    },
    {
        "id": "channel_2",
        "name": "The History Mystery", # PIVOT: From Weird Facts to Historical Deep Dives
        "niche": "Deep dives into forgotten history, ancient technology, and unsolved historical mysteries",
        "keywords": ["lost history", "ancient mystery", "unsolved mysteries", "archaeology", "historical puzzles"],
        "client_secrets_file": "credentials/channel2_secrets.json",
        "token_file": "credentials/channel2_token.json",
        "use_voice": True,
        "music_mood": "mysterious",
        "category_id": "27",
        "hook_style": "question_unsolved", # Start with a mystery no one can explain
        "script_type": "documentary",
    },
    {
        "id": "channel_3",
        "name": "Epic History Kids",
        "handle": "@EpicHistoryKids",
        "niche": "Kid-safe historical stories for ages 7-12 about ancient civilizations, famous people, inventions, discoveries, and everyday life, told with simple vocabulary, curiosity-first hooks, accurate facts, and no graphic violence",
        "keywords": ["history for kids", "kids history", "ancient civilizations", "historical stories", "famous people in history", "educational stories"],
        "client_secrets_file": "credentials/channel3_secrets.json",
        "token_file": "credentials/channel3_token.json",
        "use_voice": True,
        "voice_provider": "edge",
        "music_mood": "playful",
        "category_id": "27",
        "hook_style": "curiosity_adventure",
        "script_type": "kids_history",
        "made_for_kids": True,
        "media_source": "meta_ai_browser",
        "character_name": "Milo",
        "target_duration": 30,
        "end_screen_duration": 0,
        "seamless_scenes": True,
        "strict_voice": True,
    },
    {
        "id": "channel_4",
        "name": "The Modern Stoic", # PIVOT: From Self-Improvement to Men's Mental Health/Stoicism
        "niche": "Applying ancient wisdom to modern stress, career burnout, and relationship mental health",
        "keywords": ["stoicism", "mental toughness", "modern philosophy", "career advice", "emotional intelligence"],
        "client_secrets_file": "credentials/channel4_secrets.json",
        "token_file": "credentials/channel4_token.json",
        "use_voice": True,
        "music_mood": "epic_cinematic",
        "category_id": "27",
        "hook_style": "pain_point", # Start with a common modern struggle (e.g., burnout)
        "script_type": "educational",
    },
]
