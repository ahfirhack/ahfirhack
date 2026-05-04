"""
script_generator.py (v9 — Conversational Voice-Optimized Scripts)
Key changes:
- Scripts written for VOICE (conversational, easy to listen to)
- Uses Groq, Nova, Gemini, or Claude for generation
- Shorter scripts (80-100 words = ~35s) for higher completion rate
- Searchable titles ("How to...", "Why...") for Shorts search filter
- Loop-friendly endings that reference the hook
- Visual-descriptive search queries for relevant footage
"""

import requests
import json
import random
import time
import boto3
from botocore.exceptions import ClientError
from config import GEMINI_API_KEY, GROQ_API_KEY, CLAUDE_API_KEY, NOVA_API_KEY, AMAZON_NAME_KEY, AMAZON_API_KEY, AMAZON_REGION

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent?key=" + GEMINI_API_KEY
)
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
NOVA_URL   = "https://api.nova.ai/v1/chat/completions"
GROQ_HEADERS   = {"Authorization": f"Bearer {GROQ_API_KEY}",   "Content-Type": "application/json"}
CLAUDE_HEADERS = {"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
NOVA_HEADERS   = {"Authorization": f"Bearer {NOVA_API_KEY}",   "Content-Type": "application/json"}

# ── VISUAL SEARCH HINTS FOR FOOTAGE ──
NICHE_SEARCH_HINTS = {
    "psychology": [
        "person thinking deeply alone",
        "brain illustration with neurons",
        "people interacting socially",
        "person looking confused thinking",
        "psychology book on desk",
        "mind trick demonstration",
    ],
    "storytelling": [
        "person walking away satisfied",
        "angry person looking at construction",
        "person smiling after winning",
        "dramatic sunset over city",
        "person looking at phone surprised",
    ],
    "documentary": [
        "ancient artifact close up",
        "mysterious dark forest path",
        "old book with glowing pages",
        "underwater ancient ruins",
        "stars and galaxy night sky",
    ],
    "tutorial": [
        "clean organized desk workspace",
        "person organizing digital files",
        "minimalist home office setup",
        "person using smartphone efficiently",
        "tidy room with natural light",
    ],
    "educational": [
        "person standing alone peaceful",
        "mountain top sunrise view",
        "person meditating in nature",
        "calm ocean waves at sunset",
        "person reading book quietly",
    ],
}

# ── UPDATED FALLBACK SCRIPTS (Optimized for 2026 High-Retention Niches) ──

FALLBACK_SCRIPTS = {
    "storytelling": [ # For the "Karma & Revenge" Channel
        {"title": "The Neighbor Who Regretted Everything", "script": "My neighbor blocked my driveway for six months. He laughed every time I asked him to move. He thought he was untouchable because he knew the city council. So I stopped asking. I spent three weeks researching local zoning laws. I found out his entire garage was built two feet over the property line. One anonymous tip later and the city ordered him to tear it down. It cost him forty thousand dollars. Now my driveway is clear and he doesn't even look at me. Justice is a dish best served with blueprints.", "tags": ["prorevenge", "karma", "satisfying", "neighborwars", "justice"], "search_query": "angry man looking at construction site"},
       
    ],
    "documentary": [ # For the "History Mystery" Channel
        {"title": "The Machine That Shouldn't Exist", "script": "In 1901, divers found a rusted bronze device in an ancient shipwreck. They thought it was a gear. It turned out to be a computer built two thousand years ago. It’s called the Antikythera Mechanism. It could predict eclipses and track the stars with terrifying accuracy. But there's a problem. This level of technology wasn't supposed to exist for another thousand years. Who built it? And where did that knowledge go? History isn't a straight line. It's a series of lost secrets.", "tags": ["historymystery", "ancienttech", "unexplained", "lostcivilization", "science"], "search_query": "ancient rusted bronze gears artifact"},
    ],
    "tutorial": [ # For the "Digital & Home Declutter" Channel
        {"title": "The 'One-Touch' Rule for a Clean Desk", "script": "Your desk is messy because you touch things twice. You pick up a bill, look at it, and put it down. That's two touches. The 'One-Touch' rule says if you touch it, you must finish it. File it, delete it, or throw it away. Never put it back down to 'deal with later.' I tried this for one week and my workspace stayed spotless without any extra effort. Your brain can't focus in chaos. Clear the desk, clear the mind. Try the one-touch rule today.", "tags": ["productivity", "minimalism", "desksetup", "organizing", "lifehack"], "search_query": "clean minimalist desk workspace setup"},
    ],
    "educational": [ # For the "Modern Stoic" Channel
        {"title": "The Secret to Not Caring What People Think", "script": "Marcus Aurelius once wrote: 'It never ceases to amaze me. We love ourselves more than others, but care more about their opinion than our own.' Think about that. You are living your life based on the guesses of people who don't even know your heart. Stop seeking external validation. The only person you need to impress is the person in the mirror. If you are okay with your choices, the world's opinion doesn't matter. Focus on your character, not your reputation.", "tags": ["stoicism", "mentalhealth", "philosophy", "wisdom", "mindset"], "search_query": "person standing alone mountain top peaceful"},
    ],
    "psychology": [ # For the "Psychology & Human Behavior" Channel
        {"title": "The Memory Trick That Always Works", "script": "You remember things better when you're about to sleep. Your brain consolidates memories during deep sleep. Study for 30 minutes before bed, then sleep. You'll wake up knowing it. This is called the spacing effect. It's how your brain stores long-term memories. Try it tonight. Your brain will thank you. Like and Subscribe for more.", "tags": ["psychology", "memory", "learning", "brain", "study tips"], "search_query": "person studying at night desk"},
        {"title": "Why We Judge People So Quickly", "script": "Your brain judges people in 0.1 seconds. It's called thin-slicing. You decide if someone is trustworthy before they even speak. This comes from evolution. It kept our ancestors alive. But it's often wrong today. Give people a chance. Your first impression might be completely wrong. Slow down and think. Like and Subscribe for more.", "tags": ["psychology", "judgment", "first impressions", "social", "behavior"], "search_query": "person looking thoughtful confused"},
        {"title": "The Power of Saying No", "script": "Saying no is a superpower. Most people say yes to avoid conflict. But this drains your energy. When you say no, you protect your time. You protect your mental health. You protect your priorities. Practice saying no to small things. It gets easier. Your life will improve. Like and Subscribe for more.", "tags": ["psychology", "boundaries", "mental health", "self-care", "behavior"], "search_query": "person saying no confidently"},
    ],
}



def _detect_niche_key(niche: str) -> str:
    n = niche.lower()

    # NEW: Psychology & Human Behavior (Fast viral potential)
    if any(w in n for w in ["psychology", "human behavior", "mind tricks", "social psychology", "cognitive bias", "behavior"]):
        return "psychology"

    # NEW: English Learning Shorts (21x growth, $11.88 RPM, least saturated)
    if any(w in n for w in ["english", "language", "vocabulary", "grammar", "pronunciation", "learning"]):
        return "educational"

    # NEW: Karma & Revenge Stories (High Growth)
    if any(w in n for w in ["karma", "revenge", "justice", "betrayal", "storytelling"]):
        return "storytelling"

    # NEW: History Mystery (Deep Dives)
    if any(w in n for w in ["history", "ancient", "mystery", "unexplained", "unsolved"]):
        return "documentary"

    # NEW: Digital & Home Declutter (Specific Utility)
    if any(w in n for w in ["declutter", "organizing", "setup", "minimalism", "productivity"]):
        return "tutorial"

    # NEW: Modern Stoicism (Men's Mental Health)
    if any(w in n for w in ["stoic", "philosophy", "mental health", "discipline", "mindset"]):
        return "educational"

    return "psychology" # Default to psychology (highest viral potential)



def _get_fallback(niche: str) -> dict:
    key     = _detect_niche_key(niche)
    scripts = FALLBACK_SCRIPTS.get(key, FALLBACK_SCRIPTS["storytelling"])
    data    = random.choice(scripts)
    # Ensure search query is visual and specific
    if len(data["search_query"].split()) < 3:
        hints = NICHE_SEARCH_HINTS.get(key, ["nature background video"])
        data["search_query"] = random.choice(hints)
    return data


def _build_prompt(niche: str) -> str:
    return f"""You are a viral YouTube Shorts scriptwriter optimized for human-like VOICE narration.

Niche: {niche}

VOICE-OPTIMIZED RULES:
1. SCRIPT LENGTH: 80-100 words. (Crucial for a 30-40 second pace).
2. CONVERSATIONAL TONE: Use contractions (don't, it's). No complex jargon. Speak like a person, not a bot.
3. THE HOOK: The first sentence must trigger an emotional response (Anger, Curiosity, or Shock).
   - For English Learning: Start with a surprising fact or common mistake.
   - For Stories: Start with the conflict.
   - For Mystery: Start with a mystery.
4. STRUCTURE: No "Welcome back" or "Thanks for watching." Get straight to the point.
5. THE LOOP: The final sentence must flow back into the first sentence to encourage re-watches.
6. SENTENCE LENGTH: 5-12 words max. Short sentences create better rhythm in ElevenLabs.
7. CRITICAL: Do NOT repeat the first sentence at the end. The loop should be thematic, not literal repetition.
8. CRITICAL: End with "Like and Subscribe for more" as the final call-to-action.

SEARCH QUERY RULE: The search_query must describe CLEAR VISUAL ACTION for stock footage.
GOOD: "person studying english book", "teacher writing on whiteboard", "student taking notes"
BAD: "success", "mystery", "hacks"

Respond ONLY with valid JSON (no markdown, no backticks):
{{"title": "Searchable title under 60 chars", "script": "80-100 word voice-ready script ending with Like and Subscribe for more", "tags": ["tag1","tag2","tag3","tag4","tag5"], "search_query": "specific visual description"}}"""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.lstrip("`").lstrip("json").lstrip("`")
    if raw.endswith("```"):
        raw = raw.rstrip("`")
    return json.loads(raw.strip())


def _try_nova(prompt: str) -> dict | None:
    if not NOVA_API_KEY:
        return None
    try:
        resp = requests.post(NOVA_URL,
            headers={"Authorization": f"Bearer {NOVA_API_KEY}", "Content-Type": "application/json"},
            json={"model": "nova-lite-v1",
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.9, "max_tokens": 500},
            timeout=(8, 20))
        if resp.status_code == 429:
            print("[ScriptGen] Nova rate-limited -> next")
            return None
        resp.raise_for_status()
        data = _parse_json(resp.json()["choices"][0]["message"]["content"])
        print("[ScriptGen] Script via Nova")
        return data
    except Exception as e:
        print(f"[ScriptGen] Nova: {e}")
        return None


def _try_groq(prompt: str) -> dict | None:
    if not GROQ_API_KEY:
        return None
    try:
        resp = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.9, "max_tokens": 500},
            timeout=(8, 20))  # (connect_timeout, read_timeout)
        if resp.status_code == 429:
            print("[ScriptGen] Groq rate-limited -> next")
            return None
        resp.raise_for_status()
        data = _parse_json(resp.json()["choices"][0]["message"]["content"])
        print("[ScriptGen] Script via Groq")
        return data
    except Exception as e:
        print(f"[ScriptGen] Groq: {e}")
        return None


def _try_gemini(prompt: str) -> dict | None:
    if not GEMINI_API_KEY:
        return None
    try:
        resp = requests.post(GEMINI_URL,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.9, "maxOutputTokens": 500}},
            timeout=(8, 25))
        if resp.status_code == 429:
            print("[ScriptGen] Gemini rate-limited -> next")
            return None
        resp.raise_for_status()
        data = _parse_json(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
        print("[ScriptGen] Script via Gemini")
        return data
    except Exception as e:
        print(f"[ScriptGen] Gemini: {e}")
        return None


def _try_claude(prompt: str) -> dict | None:
    if not CLAUDE_API_KEY:
        return None
    try:
        resp = requests.post(CLAUDE_URL,
            headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 500,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=(8, 25))
        if resp.status_code in (429, 401, 403):
            return None
        resp.raise_for_status()
        data = _parse_json(resp.json()["content"][0]["text"])
        print("[ScriptGen] Script via Claude")
        return data
    except Exception as e:
        print(f"[ScriptGen] Claude: {e}")
        return None


def _try_amazon(prompt: str) -> dict | None:
    """Generate script using Amazon Bedrock (Claude or other models)."""
    if not AMAZON_NAME_KEY or not AMAZON_API_KEY:
        return None
    try:
        # Decode the base64 API key to get access key and secret key
        import base64
        decoded = base64.b64decode(AMAZON_API_KEY).decode('utf-8')
        # The decoded string should contain the access key and secret key
        # Format: "AccessKeyID:SecretAccessKey"
        if ':' in decoded:
            access_key, secret_key = decoded.split(':', 1)
        else:
            # If no colon, use the whole string as access key (fallback)
            access_key = decoded
            secret_key = AMAZON_NAME_KEY

        client = boto3.client(
            service_name="bedrock-runtime",
            region_name=AMAZON_REGION,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        response = client.invoke_model(
            modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
            body=json.dumps({
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        result = json.loads(response["body"].read())
        data = _parse_json(result["content"][0]["text"])
        print("[ScriptGen] Script via Amazon Bedrock")
        return data
    except ClientError as e:
        print(f"[ScriptGen] Amazon Bedrock: {e}")
        return None
    except Exception as e:
        print(f"[ScriptGen] Amazon: {e}")
        return None


# Accept scripts 30-150 words. Caption-only videos work fine at any length in this range.
# A 36-word script = 9 caption lines = 3-4 blocks shown across a 30-second video.
MIN_WORDS = 30
MAX_WORDS = 90


def _post_process_script(script: str) -> str:
    """
    Post-process the script to ensure:
    1. First sentence is not repeated at the end
    2. Ends with "Subscribe for more"
    """
    # Split into sentences
    sentences = [s.strip() for s in script.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    if not sentences:
        return script

    # Get first sentence (normalized for comparison)
    first_sentence = sentences[0].lower().strip()
    first_words = set(first_sentence.split())

    # Check if last sentence repeats the first
    if len(sentences) > 1:
        last_sentence = sentences[-1].lower().strip()
        last_words = set(last_sentence.split())

        # If more than 50% of words match, it's a repetition
        if first_words & last_words and len(first_words & last_words) / len(first_words) > 0.5:
            # Remove the last sentence
            sentences = sentences[:-1]

    # Ensure "Like and Subscribe for more" is at the end
    if sentences:
        last = sentences[-1].lower()
        if "subscribe" not in last:
            sentences.append("Like and Subscribe for more")

    return ". ".join(sentences).replace("..", ".").strip() + "."


def generate_script(niche: str) -> dict:
    prompt = _build_prompt(niche)
    providers = [(_try_groq, "Groq"), (_try_nova, "Nova"), (_try_gemini, "Gemini"), (_try_claude, "Claude"), (_try_amazon, "Amazon")]

    for fn, name in providers:
        result = fn(prompt)
        if not result:
            continue
        if not all(k in result for k in ("title", "script", "tags", "search_query")):
            continue

        # Post-process the script
        result["script"] = _post_process_script(result["script"])

        wc = len(result["script"].split())

        # Fix generic search queries
        sq = result.get("search_query", "")
        if len(sq.split()) < 3:
            key = _detect_niche_key(niche)
            result["search_query"] = random.choice(
                NICHE_SEARCH_HINTS.get(key, ["nature background video"]))

        if MIN_WORDS <= wc <= MAX_WORDS:
            print(f"[ScriptGen] Accepted: {wc}w | {result['title'][:50]}")
            return result

        print(f"[ScriptGen] {name}: {wc}w out of range ({MIN_WORDS}-{MAX_WORDS}) -> next provider")

    print("[ScriptGen] All providers failed -> fallback")
    fallback = _get_fallback(niche)
    fallback["script"] = _post_process_script(fallback["script"])
    return fallback
