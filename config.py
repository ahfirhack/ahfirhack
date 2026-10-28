# YouTube Multi-Channel Automation — API Keys & Settings

import os

# Number of videos to generate per run
NUM_VIDEOS = 1

# Upload to YouTube after generation
UPLOAD_TO_YOUTUBE = True

# Upload every 12 hours (in seconds)
UPLOAD_INTERVAL_HOURS = 12
UPLOAD_INTERVAL_SECONDS = UPLOAD_INTERVAL_HOURS * 3600

# ═══════════════════════════════════════════════════════
# AI / SCRIPT GENERATION
# ═══════════════════════════════════════════════════════
NOVA_API_KEY       = os.getenv("NOVA_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
CLAUDE_API_KEY     = os.getenv("CLAUDE_API_KEY", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", CLAUDE_API_KEY)
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
CEREBRAS_API_KEY   = os.getenv("CEREBRAS_API_KEY", "")
HF_TOKEN           = os.getenv("HF_TOKEN", "")
MISTRAL_API_KEY    = os.getenv("MISTRAL_API_KEY", "")
COHERE_API_KEY     = os.getenv("COHERE_API_KEY", "")
NVIDIA_API_KEY     = os.getenv("NVIDIA_API_KEY", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
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
USED_PROMPTS_FILE  = "used_prompts.json"
PROMPT_RESERVE_DB  = os.getenv("PROMPT_RESERVE_DB", "prompt_reserve.sqlite3")
PROMPT_RESERVE_DB_CHANNEL_1 = os.getenv(
    "PROMPT_RESERVE_DB_CHANNEL_1", "prompt_reserve_channel_1.sqlite3"
)
PROMPT_RESERVE_DB_CHANNEL_2 = os.getenv(
    "PROMPT_RESERVE_DB_CHANNEL_2", "prompt_reserve_channel_2.sqlite3"
)
PROMPT_RESERVE_DB_CHANNEL_4 = os.getenv(
    "PROMPT_RESERVE_DB_CHANNEL_4", "prompt_reserve_channel_4.sqlite3"
)
MUSIC_CACHE_DIR    = "music_cache"
META_AI_JOBS_DIR = os.getenv("META_AI_JOBS_DIR", "meta_ai_jobs")
META_AI_CREATE_URL = os.getenv("META_AI_CREATE_URL", "https://meta.ai/create")
META_AI_CHROME_PROFILE_DIR = os.getenv("META_AI_CHROME_PROFILE_DIR", "")
META_AI_STORAGE_STATE_FILE = os.getenv("META_AI_STORAGE_STATE_FILE", "")
META_AI_BROWSER_CHANNEL = os.getenv("META_AI_BROWSER_CHANNEL", "chromium")
META_AI_HEADLESS = os.getenv("META_AI_HEADLESS", "false").lower() in {"1", "true", "yes"}
META_AI_TIMEOUT_SECONDS = int(os.getenv("META_AI_TIMEOUT_SECONDS", "900"))
META_AI_MAX_RETRIES = int(os.getenv("META_AI_MAX_RETRIES", "4"))
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
    "channel_1": "aura-2-zeus-en",      # Tech crime: Deep, urgent, investigative
    "channel_2": "aura-2-orpheus-en",   # Storytelling: Authoritative, cinematic tension
    "channel_3": "aura-2-atlas-en",     # Kids history: Friendly, energetic storyteller
    "channel_4": "aura-odysseus-en",    # Stoic: Calm, steady, philosophical
}

# Edge TTS fallback voices (if Deepgram fails)
EDGE_VOICES = {
    "channel_1": "en-US-GuyNeural",      # Male, urgent investigative delivery
    "channel_2": "en-GB-RyanNeural",      # Male, British, dramatic storyteller
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
        "name": "Silicon Crime Files",
        "handle": "@SiliconCrimeFiles",
        "tagline": "Code. Power. Consequences.",
        "description": "The biggest technology crimes rarely begin with a siren. Silicon Crime Files investigates publicly documented hacks, startup deceptions, corporate fraud cases, billion-dollar failures, and the evidence hidden inside code and boardrooms. Every cinematic Short distinguishes allegations, charges, settlements, and convictions clearly. Subscribe for true cases where code, power, and consequences collide.",
        "logo_file": "assets/branding/channel_1/logo.png",
        "banner_file": "assets/branding/channel_1/banner.jpg",
        "niche": "High-stakes technology and corporate true crime based on documented public cases involving cybercrime, startup deception, corporate fraud, data breaches, code failures, regulatory investigations, and billion-dollar consequences",
        "keywords": ["tech true crime", "corporate crime", "cybercrime", "startup fraud", "tech scandals", "financial crime", "data breach"],
        "client_secrets_file": "credentials/channel1_secrets.json",
        "token_file": "credentials/channel1_token.json",
        "use_voice": True,
        "require_visuals": True,
        "music_mood": "suspense",
        "category_id": "28",
        "hook_style": "evidence_first",
        "script_type": "tech_corporate_true_crime",
        "opening_style": "tech_evidence",
        "hook_sfx": "tech_glitch_boom",
        "voice_provider": "edge",
        "strict_voice": True,
        "strict_ai_prompts": True,
        "allow_curated_fallback": False,
        "track_prompt_history": True,
        "strict_upload_dedup": True,
        "prompt_reserve_db": PROMPT_RESERVE_DB_CHANNEL_1,
    },
    {
        "id": "channel_2",
        "name": "StoryFuse",
        "handle": "@StoryFuseTV",
        "tagline": "Big Stakes. Sharp Twists. No Filler.",
        "description": "Every second should earn the next. StoryFuse delivers cinematic short stories built around impossible choices, hidden motives, escalating stakes, and endings that change what came before. No filler greetings—just a gripping hook, fast reveals, and a payoff worth replaying. Subscribe and follow the fuse to the final twist.",
        "logo_file": "assets/branding/channel_2/logo.png",
        "banner_file": "assets/branding/channel_2/banner.jpg",
        "niche": "Deep high-retention storytelling with cinematic stakes, memorable characters, mysteries, impossible choices, escalating micro-reveals, emotional climaxes, and twist endings",
        "keywords": ["short stories", "storytelling", "plot twist", "cinematic stories", "mystery stories", "emotional stories"],
        "client_secrets_file": "credentials/channel2_secrets.json",
        "token_file": "credentials/channel2_token.json",
        "use_voice": True,
        "require_visuals": True,
        "music_mood": "mysterious",
        "category_id": "24",
        "hook_style": "climax_first",
        "script_type": "deep_storytelling",
        "opening_style": "story_suspense",
        "voice_provider": "edge",
        "strict_voice": True,
        "strict_ai_prompts": True,
        "allow_curated_fallback": False,
        "track_prompt_history": True,
        "strict_upload_dedup": True,
        "prompt_reserve_db": PROMPT_RESERVE_DB_CHANNEL_2,
    },
    {
        "id": "channel_3",
        "name": "Epic History Kids",
        "handle": "@EpicHistoryKids",
        "niche": "Kid-safe historical stories for ages 7-12 about ancient civilizations, famous people, inventions, discoveries, and everyday life, told with simple vocabulary, curiosity-first hooks, accurate facts, and no graphic violence",
        "keywords": ["history for kids", "kids history", "ancient civilizations", "historical stories", "famous people in history", "educational stories"],
        "client_secrets_file": "credentials/channel3_secrets.json",
        "token_file": "credentials/channel3_token.json",
        "use_voice": False,
        "use_music": False,
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
        "native_clip_audio": True,
        "show_overlays": False,
        "strict_ai_prompts": True,
        "track_prompt_history": True,
        "strict_upload_dedup": True,
        "prompt_reserve_db": PROMPT_RESERVE_DB,
    },
    {
        "id": "channel_4",
        "name": "Stoic Reset",
        "handle": "@StoicResetShorts",
        "tagline": "Ancient Wisdom. Modern Strength.",
        "description": "Ancient wisdom for modern pressure. Stoic Reset turns Stoic principles into practical tools for overthinking, burnout, discipline, relationships, and resilience—without fake quotes or empty motivation. Each Short gives you one calm idea and one action you can use today. Subscribe, reset, and build a stronger mind.",
        "logo_file": "assets/branding/channel_4/logo.png",
        "banner_file": "assets/branding/channel_4/banner.jpg",
        "niche": "Applying ancient wisdom to modern stress, career burnout, and relationship mental health",
        "keywords": ["stoicism", "mental toughness", "modern philosophy", "career advice", "emotional intelligence"],
        "client_secrets_file": "credentials/channel4_secrets.json",
        "token_file": "credentials/channel4_token.json",
        "use_voice": True,
        "require_visuals": True,
        "music_mood": "cinematic",
        "category_id": "27",
        "hook_style": "pain_point", # Start with a common modern struggle (e.g., burnout)
        "script_type": "educational",
        "opening_style": "stoic_suspense",
        "voice_provider": "edge",
        "strict_voice": True,
        "strict_ai_prompts": True,
        "allow_curated_fallback": False,
        "track_prompt_history": True,
        "strict_upload_dedup": True,
        "prompt_reserve_db": PROMPT_RESERVE_DB_CHANNEL_4,
    },
]
