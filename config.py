# YouTube Multi-Channel Automation — API Keys & Settings

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
NOVA_API_KEY      = "fe21bc7b-e17c-4c0c-8f6e-8beab658804e"
GEMINI_API_KEY    = "AIzaSyCupHa8xpgwECh299cQ9_OL3OVBbGYl38A"
CLAUDE_API_KEY    = "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"
ANTHROPIC_API_KEY = "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"
GROQ_API_KEY      = "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"
ELEVENLABS_API_KEY= "sk_fdc13676018c9820a3a429bf3cf8d1acedddf2f211491fbe"
DEEPGRAM_API_KEY  = "391bf04405ae6f72af4181e3101b6aa9e7820d7f"

# Amazon Bedrock (AWS)
AMAZON_ACCESS_KEY = "BedrockAPIKey-84vr-at-717090908379"
AMAZON_SECRET_KEY = "ABSKQmVkcm9ja0FQSUtleS04NHZyLWF0LTcxNzA5MDkwODM3OTpuTkJVcGZ1blEzZldROUlzd3ZoK1piK2VjdGl5Y1dpYWhsWWsrRWNBYUhyeFc2V3JZSFMrN3YzcStMRT0"
AMAZON_REGION     = "us-east-1"
# ═══════════════════════════════════════════════════════
# STOCK MEDIA
# ═══════════════════════════════════════════════════════
PEXELS_API_KEY        = "udmGMPeNWjWQ81FebJu2nEi4ruWEs87zqGOIGNEAMonvC1d01d9hCkDj"
PIXABAY_API_KEY       = "55350436-52eb07ed9727bda1d85df8c99"

COVERR_API_KEY        = "648670b245348e76dddb3ee52960f232"
VIDEEZY_CLIENT_ID     = "107242"
VIDEEZY_CLIENT_SECRET = "EzFApuZurTkUw4wnu2RNDvdj"
YOUTUBE_API_KEY       = "AIzaSyCEcP2KW3l_N6flKHhxanWD5Nkt3sK08XY"
REPLICATE_API_KEY     = "r8_AXOQmjn1yy8AzgEgdMUomIwdxIMzRza2NZYDb"
JAMENDO_CLIENT_ID     = "b72ab361"
FREESOUND_API_KEY     = "lXPQoR31V3wHx7CVfQZUGuJgvNKUlAjqJETiSxRQ"

POLLINATIONS_ENABLED = True
USED_VIDEOS_FILE   = "used_videos.json"
USED_SCRIPTS_FILE  = "used_scripts.json"
MUSIC_CACHE_DIR    = "music_cache"



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
    "channel_3": "aura-2-atlas-en",     # Declutter: Friendly, energetic, helpful
    "channel_4": "aura-odysseus-en",    # Stoic: Calm, steady, philosophical
}

# Edge TTS fallback voices (if Deepgram fails)
EDGE_VOICES = {
    "channel_1": "en-US-GuyNeural",      # Male, energetic
    "channel_2": "en-GB-RyanNeural",      # Male, British, serious
    "channel_3": "en-US-JennyNeural",     # Female, warm, friendly
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
        "name": "Digital & Home Declutter", # PIVOT: From General Hacks to Niche Utility
        "niche": "Specific tutorials on organizing your digital life, smart home setups, and minimalist lifestyle hacks",
        "keywords": ["digital minimalism", "organizing hacks", "clean desk setup", "productive lifestyle", "smart home"],
        "client_secrets_file": "credentials/channel3_secrets.json",
        "token_file": "credentials/channel3_token.json",
        "use_voice": True,
        "music_mood": "calm_lofi",
        "category_id": "26",
        "hook_style": "before_after", # Show the mess first, then the clean result
        "script_type": "tutorial",
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
