"""
script_generator.py (v9 — Conversational Voice-Optimized Scripts)
Key changes:
- Scripts written for VOICE (conversational, easy to listen to)
- Discovers active models across seven prompt providers at runtime
- Shorter scripts (80-100 words = ~35s) for higher completion rate
- Searchable titles ("How to...", "Why...") for Shorts search filter
- Loop-friendly endings that reference the hook
- Visual-descriptive search queries for relevant footage
"""

import requests
import json
import random
import re
import time
import boto3
from botocore.exceptions import ClientError
from config import (
    AMAZON_ACCESS_KEY,
    AMAZON_REGION,
    AMAZON_SECRET_KEY,
    ANTHROPIC_API_KEY,
    CEREBRAS_API_KEY,
    CLAUDE_API_KEY,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    NOVA_API_KEY,
    OPENROUTER_API_KEY,
)

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODELS_URL = "https://api.anthropic.com/v1/models"
NOVA_URL   = "https://api.nova.ai/v1/chat/completions"
NOVA_MODELS_URL = "https://api.nova.ai/v1/models"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODELS_URL = "https://api.cerebras.ai/v1/models"

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
    "kids_history": [
        "ancient Egyptian temple in sunlight",
        "medieval castle exterior daytime",
        "Roman ruins with people exploring",
        "old sailing ship on the ocean",
        "historic invention in a museum",
        "ancient city reconstruction animation",
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
    "kids_history": [ # For the "Epic History Kids" Channel
        {"title": "Could You Rule Egypt at Nine Years Old?", "script": "Imagine becoming king before finishing elementary school. Tutankhamun was about nine when he became pharaoh of ancient Egypt. Advisors helped him rule while he learned the job. He restored temples and reversed changes from the previous ruler. Tutankhamun died around nineteen. More than three thousand years later, archaeologists opened his nearly intact tomb. Its treasures made the young pharaoh world-famous. Could you rule a kingdom at nine? Like and Subscribe for more.", "tags": ["historyforkids", "ancientegypt", "tutankhamun", "kidshistory", "educationalshorts"], "search_query": "golden Egyptian pharaoh mask museum close up"},
        {"title": "How Did the Great Wall Send Messages?", "script": "What if a wall could send a message faster than a horse? Milo visits ancient China, where guards watched from towers. Smoke signals warned nearby towers during daylight. Fire signals carried warnings after dark. Different dynasties built and rebuilt many sections over centuries. The famous Ming walls linked forts across huge distances. One signal could race along the frontier. Would you spot it in time? Like and Subscribe for more.", "tags": ["historyforkids", "ancientchina", "greatwall", "kidshistory", "educationalshorts"], "search_query": "Great Wall of China watchtower smoke signal animation"},
        {"title": "The City Hidden Under Ancient Ash", "script": "What if an ancient city suddenly became a time capsule? Milo arrives in Pompeii before Mount Vesuvius erupted in 79 CE. Ash covered streets, shops, mosaics, and everyday objects. Centuries later, explorers began uncovering the buried city. Archaeologists now study its buildings and belongings to understand Roman daily life. Even old bread ovens survived beneath the ash. What would your room reveal to historians? Like and Subscribe for more.", "tags": ["historyforkids", "pompeii", "ancientrome", "kidshistory", "educationalshorts"], "search_query": "ancient Pompeii street mosaic archaeology animation"},
        {"title": "The Machine That Made Books Travel", "script": "What if every book had to be copied by hand? Milo enters a workshop in Mainz around 1450. Johannes Gutenberg combined movable metal type, ink, and a press to print pages repeatedly. Printers could make books faster and in greater numbers. Reading material traveled farther, helping ideas spread across Europe. The machine did not invent writing, but it transformed publishing. Which book would you print first? Like and Subscribe for more.", "tags": ["historyforkids", "gutenberg", "printingpress", "kidshistory", "inventions"], "search_query": "Gutenberg printing press workshop movable type animation"},
        {"title": "The First Computer Program Came Before Computers", "script": "What if you wrote computer instructions before computers existed? Milo meets Ada Lovelace in 1843. She studied Charles Babbage's planned Analytical Engine, a mechanical calculating machine. In her published notes, Ada described steps for calculating Bernoulli numbers. That sequence is often called the first published computer program. The engine was never completed in her lifetime, but her ideas looked far ahead. What would you ask Ada to calculate? Like and Subscribe for more.", "tags": ["historyforkids", "adalovelace", "computerhistory", "kidshistory", "stemforkids"], "search_query": "Ada Lovelace Victorian mechanical computer gears animation"},
        {"title": "How Sailors Found Islands Without Compasses", "script": "What if you crossed a giant ocean without a map or compass? Milo joins Polynesian navigators in a double-hulled canoe. They read star paths, ocean swells, winds, clouds, and the flights of birds. Knowledge passed carefully between generations. Using these clues, voyagers traveled across the Pacific and settled distant islands centuries before European explorers arrived. The ocean became their living map. Could you follow the stars home? Like and Subscribe for more.", "tags": ["historyforkids", "polynesiahistory", "navigation", "kidshistory", "oceanexplorers"], "search_query": "Polynesian double hulled canoe navigating by stars animation"},
        {"title": "The Underground Army Found by Farmers", "script": "What if thousands of clay soldiers waited underground for two thousand years? Milo travels to China in 1974, when farmers digging a well found pottery fragments. Archaeologists uncovered a vast terracotta army made for Emperor Qin Shi Huang. Soldiers, horses, and chariots stood in huge pits near his tomb. Many figures have different faces and hairstyles. The discovery revealed astonishing ancient craftsmanship. Which warrior would you investigate first? Like and Subscribe for more.", "tags": ["historyforkids", "terracottaarmy", "ancientchina", "archaeology", "educationalshorts"], "search_query": "Terracotta Army excavation archaeologists 3D animation"},
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

    # Kids' history needs age-appropriate scripts and visuals, not mystery content.
    if any(w in n for w in ["kid", "children", "young audience"]) and any(
        w in n for w in ["history", "historical", "ancient civilization"]
    ):
        return "kids_history"

    # NEW: Psychology & Human Behavior (Fast viral potential)
    if any(w in n for w in ["psychology", "human behavior", "mind tricks", "social psychology", "cognitive bias", "behavior"]):
        return "psychology"

    # NEW: English Learning Shorts (21x growth, $11.88 RPM, least saturated)
    if any(w in n for w in ["english", "language", "vocabulary", "grammar", "pronunciation", "learning"]):
        return "educational"

    # NEW: Karma & Revenge Stories (High Growth)
    if any(w in n for w in ["karma", "revenge", "justice", "betrayal", "storytelling"]):
        return "storytelling"

    # Modern Stoicism must be detected before generic history words. Channel 4
    # includes the phrase "ancient wisdom", which previously misclassified it
    # as documentary content and selected Channel 2's history fallback.
    if any(w in n for w in ["stoic", "philosophy", "mental health", "discipline", "mindset"]):
        return "educational"

    # NEW: History Mystery (Deep Dives)
    if any(w in n for w in ["history", "ancient", "mystery", "unexplained", "unsolved"]):
        return "documentary"

    # NEW: Digital & Home Declutter (Specific Utility)
    if any(w in n for w in ["declutter", "organizing", "setup", "minimalism", "productivity"]):
        return "tutorial"

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


def _build_prompt(niche: str, uniqueness_seed: str = "") -> str:
    kids_history = _detect_niche_key(niche) == "kids_history"
    length_rule = (
        "50-65 words, written for a 30-second narration."
        if kids_history else
        "80-90 words, written for a 30-40 second narration."
    )
    json_length = "50-65" if kids_history else "80-90"
    kids_rules = """
KIDS' HISTORY EPISODE RULES:
- Tell one accurate, chronological story with three clear visual beats.
- Use simple language for ages 7-12 and no graphic violence, fear, or adult themes.
- Milo is the recurring ten-year-old time-travel guide and the only speaker. Write the exact words Milo says; never add another narrator or character voice.
- Group the narration into three concrete visual beats, one for each ten-second animated scene.
- Never change Milo's appearance, clothing, age, or personality.
""" if kids_history else ""
    uniqueness_rule = (
        f"UNIQUE EPISODE SEED: {uniqueness_seed}. Use this seed to choose a fresh "
        "historical subject and angle. Never mention the seed in the output."
        if uniqueness_seed else
        "Choose a fresh subject and angle that is unlikely to repeat an earlier episode."
    )
    return f"""You are a viral YouTube Shorts scriptwriter optimized for human-like VOICE narration.

Niche: {niche}
{kids_rules}
{uniqueness_rule}

VOICE-OPTIMIZED RULES:
1. SCRIPT LENGTH: {length_rule}
2. CONVERSATIONAL TONE: Use contractions (don't, it's). No complex jargon. Speak like a person, not a bot.
3. THE HOOK: The first sentence must trigger an emotional response (Anger, Curiosity, or Shock).
   - For English Learning: Start with a surprising fact or common mistake.
   - For Stories: Start with the conflict.
   - For Mystery: Start with a mystery.
   - For Kids' History: Start with an imaginative "What if...?" or a surprising factual question. Keep every detail accurate, age-appropriate, and free of graphic violence.
4. STRUCTURE: No "Welcome back" or "Thanks for watching." Get straight to the point.
5. THE LOOP: The final sentence must flow back into the first sentence to encourage re-watches.
6. SENTENCE LENGTH: 5-12 words max. Short sentences keep generated speech clear.
7. CRITICAL: Do NOT repeat the first sentence at the end. The loop should be thematic, not literal repetition.
8. CRITICAL: End with "Like and Subscribe for more" as the final call-to-action.

SEARCH QUERY RULE: The search_query must describe CLEAR VISUAL ACTION for stock footage.
GOOD: "person studying english book", "teacher writing on whiteboard", "student taking notes"
BAD: "success", "mystery", "hacks"

Respond ONLY with valid JSON (no markdown, no backticks):
{{"title": "Searchable title under 60 chars", "script": "{json_length} word voice-ready script ending with Like and Subscribe for more", "tags": ["tag1","tag2","tag3","tag4","tag5"], "search_query": "specific visual description"}}"""


def _parse_json(raw: str) -> dict:
    """Parse plain, fenced, or reasoning-prefixed provider JSON safely."""
    raw = raw.strip().lstrip("\ufeff")
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", raw):
            try:
                value, _ = decoder.raw_decode(raw[match.start():])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
        raise original_error


def _log_provider_error(provider: str, error: Exception) -> None:
    """Log useful failure information without printing request URLs or credentials."""
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        detail = f"HTTP {status_code}"
    elif isinstance(error, ClientError):
        detail = error.response.get("Error", {}).get("Code", "ClientError")
    else:
        detail = type(error).__name__
    print(f"[ScriptGen] {provider} failed ({detail})")


def _ordered_text_models(
    available: list[str],
    preferred: tuple[str, ...] = (),
) -> list[str]:
    """Prefer known efficient models, then use any active text-chat model."""
    excluded = (
        "audio", "embed", "guard", "image", "live", "moderation",
        "rerank", "speech", "transcribe", "tts", "veo", "whisper",
    )
    usable = [
        model for model in available
        if model and not any(term in model.lower() for term in excluded)
    ]
    ordered = [model for model in preferred if model in usable]
    ordered.extend(sorted((model for model in usable if model not in ordered), reverse=True))
    return ordered


def _discover_openai_models(
    provider: str,
    catalog_url: str,
    api_key: str,
    preferred: tuple[str, ...],
) -> list[str]:
    """Query an OpenAI-compatible provider catalog once per workflow run."""
    try:
        response = requests.get(
            catalog_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=(8, 20),
        )
        response.raise_for_status()
        available = [
            item.get("id", "") for item in response.json().get("data", [])
            if isinstance(item, dict)
        ]
        models = _ordered_text_models(available, preferred)
        if models:
            print(f"[ScriptGen] {provider} catalog: {len(models)} active text models")
            return models
    except Exception as error:
        _log_provider_error(f"{provider} model discovery", error)
    # These are only a last-known bootstrap. A successful catalog response
    # always replaces them, so retired models are not pinned forever.
    return list(preferred)


def _try_openai_chat_provider(
    provider: str,
    url: str,
    api_key: str,
    prompt: str,
    models: list[str],
) -> dict | None:
    """Try every active model, with JSON mode and a plain-output retry."""
    last_error: Exception | None = None
    for model in models:
        for json_mode in (True, False):
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
                "max_tokens": 500,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            try:
                response = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=(8, 25),
                )
                if response.status_code == 429:
                    print(f"[ScriptGen] {provider} rate-limited -> next provider")
                    return None
                if response.status_code in (401, 403):
                    response.raise_for_status()
                if response.status_code in (400, 404, 422):
                    if json_mode:
                        continue
                    break
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                result = _parse_json(content)
                print(f"[ScriptGen] Script via {provider} ({model})")
                return result
            except Exception as error:
                last_error = error
                status_code = getattr(getattr(error, "response", None), "status_code", None)
                if status_code in (401, 403):
                    _log_provider_error(provider, error)
                    return None
                if json_mode:
                    continue
                break
    if last_error is not None:
        _log_provider_error(provider, last_error)
    return None


def _try_nova(prompt: str) -> dict | None:
    if not NOVA_API_KEY:
        return None
    models = _discover_openai_models(
        "Nova", NOVA_MODELS_URL, NOVA_API_KEY, ("nova-lite-v1",)
    )
    return _try_openai_chat_provider(
        "Nova", NOVA_URL, NOVA_API_KEY, prompt, models
    )


def _try_groq(prompt: str) -> dict | None:
    if not GROQ_API_KEY:
        return None
    models = _discover_openai_models(
        "Groq",
        GROQ_MODELS_URL,
        GROQ_API_KEY,
        ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"),
    )
    return _try_openai_chat_provider(
        "Groq", GROQ_URL, GROQ_API_KEY, prompt, models
    )


def _try_openrouter(prompt: str) -> dict | None:
    if not OPENROUTER_API_KEY:
        return None
    return _try_openai_chat_provider(
        "OpenRouter Free",
        OPENROUTER_URL,
        OPENROUTER_API_KEY,
        prompt,
        ["openrouter/free"],
    )


def _try_cerebras(prompt: str) -> dict | None:
    if not CEREBRAS_API_KEY:
        return None
    models = _discover_openai_models(
        "Cerebras",
        CEREBRAS_MODELS_URL,
        CEREBRAS_API_KEY,
        ("zai-glm-4.7", "gpt-oss-120b", "llama3.1-8b"),
    )
    return _try_openai_chat_provider(
        "Cerebras", CEREBRAS_URL, CEREBRAS_API_KEY, prompt, models
    )


def _try_gemini(prompt: str) -> dict | None:
    if not GEMINI_API_KEY:
        return None
    try:
        catalog = requests.get(
            GEMINI_MODELS_URL,
            params={"key": GEMINI_API_KEY, "pageSize": 1000},
            timeout=(8, 20),
        )
        catalog.raise_for_status()
        available = []
        for model in catalog.json().get("models", []):
            methods = model.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
            name = model.get("name", "").removeprefix("models/")
            available.append(name)
        models = _ordered_text_models(
            available,
            ("gemini-flash-latest", "gemini-3.8-flash", "gemini-3.7-flash"),
        )
        print(f"[ScriptGen] Gemini catalog: {len(models)} active text models")
        for model in models:
            for json_mode in (True, False):
                generation_config = {
                    "temperature": 0.9,
                    "maxOutputTokens": 500,
                }
                if json_mode:
                    generation_config["responseMimeType"] = "application/json"
                response = requests.post(
                    GEMINI_GENERATE_URL.format(model=model),
                    params={"key": GEMINI_API_KEY},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": generation_config,
                    },
                    timeout=(8, 25),
                )
                if response.status_code == 429:
                    print("[ScriptGen] Gemini rate-limited -> next provider")
                    return None
                if response.status_code in (400, 404) and json_mode:
                    continue
                if response.status_code in (400, 404):
                    break
                response.raise_for_status()
                text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                data = _parse_json(text)
                print(f"[ScriptGen] Script via Gemini ({model})")
                return data
        return None
    except Exception as e:
        _log_provider_error("Gemini", e)
        return None


def _try_claude(prompt: str) -> dict | None:
    api_key = CLAUDE_API_KEY or ANTHROPIC_API_KEY
    if not api_key:
        return None
    try:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        catalog = requests.get(
            CLAUDE_MODELS_URL,
            headers=headers,
            params={"limit": 1000},
            timeout=(8, 20),
        )
        catalog.raise_for_status()
        available = [item.get("id", "") for item in catalog.json().get("data", [])]
        models = _ordered_text_models(
            available,
            ("claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-sonnet-5"),
        )
        print(f"[ScriptGen] Claude catalog: {len(models)} active text models")
        for model in models:
            response = requests.post(
                CLAUDE_URL,
                headers=headers,
                json={
                    "model": model,
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=(8, 25),
            )
            if response.status_code == 429:
                print("[ScriptGen] Claude rate-limited -> next provider")
                return None
            if response.status_code in (400, 404):
                continue
            response.raise_for_status()
            data = _parse_json(response.json()["content"][0]["text"])
            print(f"[ScriptGen] Script via Claude ({model})")
            return data
        return None
    except Exception as e:
        _log_provider_error("Claude", e)
        return None


def _try_amazon(prompt: str) -> dict | None:
    """Discover and try active Anthropic text models on Amazon Bedrock."""
    if not AMAZON_ACCESS_KEY or not AMAZON_SECRET_KEY:
        return None
    try:
        # Decode the base64 API key to get access key and secret key
        import base64
        decoded = base64.b64decode(AMAZON_SECRET_KEY).decode('utf-8')
        # The decoded string should contain the access key and secret key
        # Format: "AccessKeyID:SecretAccessKey"
        if ':' in decoded:
            access_key, secret_key = decoded.split(':', 1)
        else:
            # If no colon, use the whole string as access key (fallback)
            access_key = decoded
            secret_key = AMAZON_ACCESS_KEY

        client_kwargs = dict(
            region_name=AMAZON_REGION,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        catalog_client = boto3.client(
            service_name="bedrock",
            **client_kwargs,
        )
        summaries = catalog_client.list_foundation_models(
            byProvider="Anthropic",
            byOutputModality="TEXT",
            byInferenceType="ON_DEMAND",
        ).get("modelSummaries", [])
        available = [
            summary.get("modelId", "") for summary in summaries
            if summary.get("modelLifecycle", {}).get("status", "ACTIVE") == "ACTIVE"
        ]
        models = _ordered_text_models(available)
        print(f"[ScriptGen] Amazon Bedrock catalog: {len(models)} active Claude models")

        client = boto3.client(
            service_name="bedrock-runtime",
            **client_kwargs,
        )
        for model in models:
            candidates = [model]
            if model.startswith("anthropic."):
                candidates.append(f"us.{model}")
            for candidate in candidates:
                try:
                    response = client.invoke_model(
                        modelId=candidate,
                        body=json.dumps({
                            "max_tokens": 500,
                            "messages": [{"role": "user", "content": prompt}],
                            "anthropic_version": "bedrock-2023-05-31",
                        }),
                    )
                    result = json.loads(response["body"].read())
                    data = _parse_json(result["content"][0]["text"])
                    print(f"[ScriptGen] Script via Amazon Bedrock ({candidate})")
                    return data
                except ClientError:
                    continue
        return None
    except ClientError as e:
        _log_provider_error("Amazon Bedrock", e)
        return None
    except Exception as e:
        _log_provider_error("Amazon", e)
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


class ScriptGenerationError(RuntimeError):
    """No configured AI provider produced an acceptable unique script."""


def generate_script(
    niche: str,
    *,
    allow_fallback: bool = True,
    reject_candidate=None,
    uniqueness_seed: str = "",
) -> dict:
    prompt = _build_prompt(niche, uniqueness_seed)
    providers = [
        (_try_groq, "Groq"),
        (_try_openrouter, "OpenRouter Free"),
        (_try_cerebras, "Cerebras"),
        (_try_gemini, "Gemini"),
        (_try_nova, "Nova"),
        (_try_claude, "Claude"),
        (_try_amazon, "Amazon Bedrock"),
    ]
    niche_key = _detect_niche_key(niche)
    min_words, max_words = (48, 70) if niche_key == "kids_history" else (MIN_WORDS, MAX_WORDS)

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

        if min_words <= wc <= max_words:
            if reject_candidate is not None and reject_candidate(result):
                print(f"[ScriptGen] {name}: duplicate prompt rejected -> next provider")
                continue
            print(f"[ScriptGen] Accepted: {wc}w | {result['title'][:50]}")
            return result

        print(f"[ScriptGen] {name}: {wc}w out of range ({min_words}-{max_words}) -> next provider")

    if not allow_fallback:
        raise ScriptGenerationError(
            "Every configured AI provider failed, returned invalid output, or "
            "repeated a used prompt. Canned fallback prompts are disabled."
        )

    key = _detect_niche_key(niche)
    fallback_scripts = FALLBACK_SCRIPTS.get(key, FALLBACK_SCRIPTS["storytelling"])
    for template in random.sample(fallback_scripts, len(fallback_scripts)):
        fallback = dict(template)
        fallback["script"] = _post_process_script(fallback["script"])
        if reject_candidate is not None and reject_candidate(fallback):
            continue
        print("[ScriptGen] All providers failed -> unused fallback")
        return fallback

    raise ScriptGenerationError(
        "All AI providers and fallback prompts were exhausted without a unique script."
    )
