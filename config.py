# YouTube Multi-Channel Automation — API Keys & Settings

import os

# Number of videos to generate per run
NUM_VIDEOS = 1

# Upload to YouTube after generation
UPLOAD_TO_YOUTUBE = True

# Run every 6 hours (GitHub Actions or optional local daemon)
UPLOAD_INTERVAL_HOURS = 6
UPLOAD_INTERVAL_SECONDS = UPLOAD_INTERVAL_HOURS * 3600

# ═══════════════════════════════════════════════════════
# AI / SCRIPT GENERATION
# ═══════════════════════════════════════════════════════
NOVA_API_KEY       = os.getenv("NOVA_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
CLAUDE_API_KEY     = os.getenv("CLAUDE_API_KEY", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", CLAUDE_API_KEY)
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
OPENAI_TEXT_MODEL  = os.getenv("OPENAI_TEXT_MODEL", "gpt-6-astra").strip()
REPLICATE_API_KEY  = os.getenv("REPLICATE_API_KEY", "")
REPLICATE_TEXT_MODEL = os.getenv(
    "REPLICATE_TEXT_MODEL", "meta/meta-llama-3-70b-instruct"
).strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
CEREBRAS_API_KEY   = os.getenv("CEREBRAS_API_KEY", "")
HF_TOKEN           = os.getenv("HF_TOKEN", "")
AI_HORDE_API_KEY   = os.getenv("AI_HORDE_API_KEY", "").strip() or "0000000000"
AI_HORDE_ENABLED   = os.getenv("AI_HORDE_ENABLED", "true").lower() in {
    "1", "true", "yes",
}
AI_HORDE_TEXT_MODEL = os.getenv("AI_HORDE_TEXT_MODEL", "").strip()
AI_HORDE_IMAGE_MODEL = os.getenv("AI_HORDE_IMAGE_MODEL", "").strip()
AI_HORDE_TEXT_TIMEOUT_SECONDS = int(
    os.getenv("AI_HORDE_TEXT_TIMEOUT_SECONDS", "120")
)
AI_HORDE_IMAGE_TIMEOUT_SECONDS = int(
    os.getenv("AI_HORDE_IMAGE_TIMEOUT_SECONDS", "420")
)
MISTRAL_API_KEY    = os.getenv("MISTRAL_API_KEY", "")
COHERE_API_KEY     = os.getenv("COHERE_API_KEY", "")
NVIDIA_API_KEY     = os.getenv("NVIDIA_API_KEY", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEEPGRAM_API_KEY   = os.getenv("DEEPGRAM_API_KEY", "")
SCRIPT_PROVIDER_COOLDOWN_SECONDS = int(
    os.getenv("SCRIPT_PROVIDER_COOLDOWN_SECONDS", "300")
)

# Amazon Bedrock (AWS)
AMAZON_ACCESS_KEY = os.getenv("AMAZON_ACCESS_KEY", "")
AMAZON_SECRET_KEY = os.getenv("AMAZON_SECRET_KEY", "")
AMAZON_REGION     = os.getenv("AMAZON_REGION", "us-east-1")
# Video and audio media source is ONLY Meta AI. No stock-media API keys.

USED_VIDEOS_FILE   = "used_videos.json"
USED_SCRIPTS_FILE  = "used_scripts.json"
USED_PROMPTS_FILE  = "used_prompts.json"
UPLOADED_TITLES_FILE = os.getenv("UPLOADED_TITLES_FILE", "uploaded_titles.json")
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
META_AI_STORAGE_STATE_FILE = os.getenv("META_AI_STORAGE_STATE_FILE", "meta_ai_storage_state.json")
META_AI_BROWSER_CHANNEL = os.getenv("META_AI_BROWSER_CHANNEL", "chromium")
META_AI_HEADLESS = os.getenv("META_AI_HEADLESS", "false").lower() in {"1", "true", "yes"}
META_AI_TIMEOUT_SECONDS = int(os.getenv("META_AI_TIMEOUT_SECONDS", "900"))
META_AI_MAX_RETRIES = int(os.getenv("META_AI_MAX_RETRIES", "4"))
META_SCENE_COUNT = 5
META_SCENE_DURATION = 10
META_SCENE_FPS = 30
# Meta image-to-video commonly reframes the supplied PNG slightly even when it
# preserves the same subject and set.  Deltas above this still indicate a gross
# reset; accepted boundaries are made frame-exact and smoothed by the assembler.
META_MAX_HANDOFF_DELTA = float(os.getenv("META_MAX_HANDOFF_DELTA", "0.18"))
META_MAX_DUPLICATE_DELTA = float(os.getenv("META_MAX_DUPLICATE_DELTA", "0.025"))



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
END_SCREEN_DURATION = 0   # no CTA: preserve generated scenes completely

# ── VIDEO QUALITY ───────────────────────────────────────────
# Higher than Full HD for better quality
VIDEO_WIDTH  = 1440  # 2K width (better than 1080)
VIDEO_HEIGHT = 2560  # 2K height (better than 1920)
VIDEO_BITRATE = 12_000_000  # 12 Mbps for higher quality
VIDEO_CRF     = 16     # Lower CRF = higher quality

# No external voice-over / music generator in the production pipeline.

# ── META-ONLY SCHEDULE / OUTPUT ───────────────────────────
# Each run generates one 50-second Short per channel; GitHub Actions
# invokes the same pipeline four times/day (every 6 hours).
VIDEOS_PER_CHANNEL_PER_DAY  = 1  # legacy name; means one upload per channel per run
SHORT_DURATION_TARGET        = META_SCENE_COUNT * META_SCENE_DURATION  # exactly 50 seconds
VIDEO_DURATION_TARGET        = SHORT_DURATION_TARGET
OUTPUT_DIR                   = "output_videos"
TEMP_DIR                     = "temp"

# ── CHANNELS ─────────────────────────────────────────────
CHANNELS = [
    {
        "id": "channel_1",
        "media_source": "meta_ai_browser",
        "scene_count": META_SCENE_COUNT,
        "scene_duration": META_SCENE_DURATION,
        "target_duration": META_SCENE_COUNT * META_SCENE_DURATION,
        "end_screen_duration": 0,
        "seamless_scenes": True,
        "native_clip_audio": True,
        "show_overlays": False,
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
        "use_voice": False,
        "use_music": False,


        "category_id": "28",

        "script_type": "tech_corporate_true_crime",



        "strict_ai_prompts": True,
        "allow_curated_fallback": False,
        "track_prompt_history": True,
        "strict_upload_dedup": True,
        "prompt_reserve_db": PROMPT_RESERVE_DB_CHANNEL_1,
    },
    {
        "id": "channel_2",
        "media_source": "meta_ai_browser",
        "scene_count": META_SCENE_COUNT,
        "scene_duration": META_SCENE_DURATION,
        "target_duration": META_SCENE_COUNT * META_SCENE_DURATION,
        "end_screen_duration": 0,
        "seamless_scenes": True,
        "native_clip_audio": True,
        "show_overlays": False,
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
        "use_voice": False,
        "use_music": False,


        "category_id": "24",

        "script_type": "deep_storytelling",


        "strict_ai_prompts": True,
        "allow_curated_fallback": False,
        "track_prompt_history": True,
        "strict_upload_dedup": True,
        "prompt_reserve_db": PROMPT_RESERVE_DB_CHANNEL_2,
    },
    {
        "id": "channel_3",
        "scene_count": META_SCENE_COUNT,
        "scene_duration": META_SCENE_DURATION,
        "name": "Epic History Kids",
        "handle": "@EpicHistoryKids",
        "niche": "Kid-safe historical stories for ages 7-12 about ancient civilizations, famous people, inventions, discoveries, and everyday life, told with simple vocabulary, curiosity-first hooks, accurate facts, and no graphic violence",
        "keywords": ["history for kids", "kids history", "ancient civilizations", "historical stories", "famous people in history", "educational stories"],
        "client_secrets_file": "credentials/channel3_secrets.json",
        "token_file": "credentials/channel3_token.json",
        "use_voice": False,
        "use_music": False,

        "category_id": "27",

        "script_type": "kids_history",
        "made_for_kids": True,
        "media_source": "meta_ai_browser",
        "character_name": "Milo",
        "target_duration": META_SCENE_COUNT * META_SCENE_DURATION,
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
        "media_source": "meta_ai_browser",
        "scene_count": META_SCENE_COUNT,
        "scene_duration": META_SCENE_DURATION,
        "target_duration": META_SCENE_COUNT * META_SCENE_DURATION,
        "end_screen_duration": 0,
        "seamless_scenes": True,
        "native_clip_audio": True,
        "show_overlays": False,
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
        "use_voice": False,
        "use_music": False,


        "category_id": "27",

        "script_type": "educational",


        "strict_ai_prompts": True,
        "allow_curated_fallback": False,
        "track_prompt_history": True,
        "strict_upload_dedup": True,
        "prompt_reserve_db": PROMPT_RESERVE_DB_CHANNEL_4,
    },
]
