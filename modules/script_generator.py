"""
script_generator.py (v9 — Conversational Voice-Optimized Scripts)
Key changes:
- Scripts written for VOICE (conversational, easy to listen to)
- Discovers active models across thirteen prompt providers at runtime
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
    AI_HORDE_ENABLED,
    AMAZON_ACCESS_KEY,
    AMAZON_REGION,
    AMAZON_SECRET_KEY,
    ANTHROPIC_API_KEY,
    CEREBRAS_API_KEY,
    CLAUDE_API_KEY,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    COHERE_API_KEY,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    HF_TOKEN,
    MISTRAL_API_KEY,
    NVIDIA_API_KEY,
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
HF_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"
HF_MODELS_URL = "https://huggingface.co/api/models"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODELS_URL = "https://api.mistral.ai/v1/models"
COHERE_URL = "https://api.cohere.com/v2/chat"
COHERE_MODELS_URL = "https://api.cohere.com/v1/models"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"

# ── VISUAL SEARCH HINTS FOR FOOTAGE ──
NICHE_SEARCH_HINTS = {
    "tech_crime": [
        "redacted court filing on desk dramatic close up",
        "cybersecurity analyst reviewing terminal logs dark office",
        "executive silhouette at congressional hearing wide shot",
        "server room warning lights forensic investigation",
        "financial evidence documents with red string close up",
    ],
    "psychology": [
        "person thinking deeply alone",
        "brain illustration with neurons",
        "people interacting socially",
        "person looking confused thinking",
        "psychology book on desk",
        "mind trick demonstration",
    ],
    "storytelling": [
        "worried person opening sealed letter cinematic close up",
        "lone driver on rainy road at night",
        "silhouette waiting in doorway dramatic lighting",
        "person answering phone in empty room suspense",
        "pocket watch ticking beside old photograph",
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
    "tech_crime": [
        {
            "title": "Theranos: The Finger-Prick Promise That Failed",
            "script": "Theranos raised hundreds of millions around a machine that promised many blood tests from a finger prick. But federal trial evidence showed its founder, Elizabeth Holmes, made false claims to investors about the technology and company performance. In 2022, a jury convicted her on four investor-fraud counts involving more than $140 million in wire transfers. She received a sentence exceeding eleven years. The tiny blood sample was never the biggest risk. The claims around it were. Like and Subscribe for more.",
            "tags": ["theranos", "techcrime", "corporatefraud", "truecrime", "siliconvalley"],
            "search_query": "Theranos federal court records blood testing machine evidence close up",
            "visual_queries": [
                "federal court filing beside small blood vial dramatic evidence close up",
                "laboratory blood testing machine under red forensic light macro shot",
                "empty startup boardroom after verdict cold cinematic wide shot",
            ],
            "hook_overlay": "THE MACHINE SOLD A PROMISE",
            "hook_accent": "$140 MILLION",
            "evidence_label": "FEDERAL VERDICT // 2022",
            "source_url": "https://www.justice.gov/usao-ndca/pr/elizabeth-holmes-sentenced-more-11-years-defrauding-theranos-investors-hundreds",
        },
        {
            "title": "FTX Hid the Risk Inside Its Code",
            "script": "FTX customers saw a trusted crypto exchange. Behind the interface, federal prosecutors said its founder directed code changes that let Alameda withdraw effectively unlimited funds. A jury convicted Sam Bankman-Fried on seven fraud and conspiracy counts. In 2024, he received twenty-five years in prison and more than eleven billion dollars in forfeiture. The most dangerous feature was not visible on any customer screen. It was hidden in the system's privileges. Like and Subscribe for more.",
            "tags": ["ftx", "cryptocrime", "corporatefraud", "techcrime", "truecrime"],
            "search_query": "cryptocurrency exchange terminal code federal evidence dramatic close up",
            "visual_queries": [
                "crypto trading screen freezes beside federal case file dark close up",
                "software engineer reviews privileged account code red monitor light",
                "empty cryptocurrency office after conviction cinematic wide shot",
            ],
            "hook_overlay": "THE RISK WAS IN THE CODE",
            "hook_accent": "$11 BILLION",
            "evidence_label": "FEDERAL SENTENCING // 2024",
            "source_url": "https://www.justice.gov/usao-sdny/pr/samuel-bankman-fried-sentenced-25-years-prison",
        },
        {
            "title": "Uber Called a Breach a Bug Bounty",
            "script": "Uber called a one-hundred-thousand-dollar payment a bug bounty. Federal trial evidence showed hackers had stolen records tied to roughly fifty-seven million users and drivers in 2016. Prosecutors said former security chief Joseph Sullivan helped conceal the breach while the FTC was investigating Uber's security practices. A jury convicted him of obstruction and misprision of a felony in 2022. The payment looked like security work. The hidden data made it evidence. Like and Subscribe for more.",
            "tags": ["uber", "databreach", "cybercrime", "techcrime", "corporatecrime"],
            "search_query": "data breach court evidence bug bounty payment cybersecurity office",
            "visual_queries": [
                "redacted breach report marked bug bounty under red desk light close up",
                "security analyst reviews stolen user records terminal dark office",
                "federal courtroom documents beside locked server rack wide shot",
            ],
            "hook_overlay": "A BREACH BECAME A BOUNTY",
            "hook_accent": "57 MILLION RECORDS",
            "evidence_label": "FEDERAL VERDICT // 2022",
            "source_url": "https://www.justice.gov/usao-ndca/pr/former-chief-security-officer-uber-convicted-federal-charges-covering-data-breach",
        },
        {
            "title": "Volkswagen Put the Deception in Software",
            "script": "Volkswagen diesel cars appeared clean during laboratory testing. On the road, hidden software changed how emissions controls behaved. The Justice Department said the defeat device affected about five-hundred-ninety-thousand vehicles sold in the United States. Volkswagen agreed to plead guilty to three felonies and pay a 2.8-billion-dollar criminal penalty, plus 1.5 billion dollars in civil resolutions. One decision inside the code changed an entire corporation's legal future. The test was not fooled by the engine. It was fooled by software. Like and Subscribe for more.",
            "tags": ["volkswagen", "dieselgate", "corporatecrime", "software", "techcrime"],
            "search_query": "diesel emissions test software code Justice Department evidence",
            "visual_queries": [
                "diesel emissions test monitor shows conflicting readings close up",
                "automotive engineer reviews engine control software dark laboratory",
                "federal plea agreement beside car keys cinematic evidence shot",
            ],
            "hook_overlay": "THE SOFTWARE KNEW THE TEST",
            "hook_accent": "$4.3 BILLION",
            "evidence_label": "DOJ RESOLUTION // 2017",
            "source_url": "https://www.justice.gov/archives/opa/pr/volkswagen-ag-agrees-plead-guilty-and-pay-43-billion-criminal-and-civil-penalties-six",
        },
    ],
    "storytelling": [
        {
            "title": "Her Warning Came From Tomorrow",
            "script": "Mara heard her own voice on a recorder saying, do not open the door. The timestamp read tomorrow. Three knocks matched the recording exactly. She called her brother, but his phone rang outside. Behind the door sat his coat, a train ticket, and one final message: leave now. Mara reached the station before her apartment ceiling collapsed. Then she understood who recorded the warning. Tomorrow, she would send it back. Like and Subscribe for more.",
            "tags": ["shortstory", "plottwist", "mystery", "storytelling", "suspense"],
            "search_query": "young woman red coat hears recorder rainy apartment cinematic close up",
            "visual_queries": [
                "young woman red coat hears recorder rainy apartment close up",
                "young woman red coat opens dark hallway door handheld camera",
                "young woman red coat runs through train station dawn wide shot",
            ],
            "hook_overlay": "HER WARNING CAME FROM TOMORROW",
            "hook_accent": "TOMORROW",
        },
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
    "educational": [
        {
            "title": "The Two-Column Rule for Harsh Criticism",
            "script": "One harsh message can control your entire day, but only if you answer it immediately. The Stoics separated what happens from the judgment we add. Before replying, write two columns: what you control, and what you do not. Put your words, timing, and conduct in the first. Put their opinion in the second. Then respond only from the first column. The criticism may stay, but its grip weakens. Your pause becomes the strength the message tried to take. Like and Subscribe for more.",
            "tags": ["stoicism", "criticism", "selfcontrol", "resilience", "mindset"],
            "search_query": "professional pauses before replying to harsh message at desk",
            "visual_queries": [
                "professional reads harsh phone message dark office close up",
                "professional writes two control columns notebook overhead shot",
                "professional calmly closes phone at sunrise office wide shot",
            ],
            "hook_overlay": "ONE MESSAGE HIJACKED YOUR DAY",
            "hook_accent": "CONTROL",
        },
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

    # Evidence-led technology and corporate cases need stronger factual and
    # legal-status safeguards than generic documentary or story content.
    if any(w in n for w in [
        "tech true crime", "technology and corporate true crime",
        "corporate crime", "cybercrime", "startup deception",
        "corporate fraud", "data breach", "regulatory investigation",
    ]):
        return "tech_crime"

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
    """Produce a five-scene, 50-second idea; media is Meta AI ONLY."""
    niche_key = _detect_niche_key(niche)
    channel_rules = {
        "tech_crime": (
            "Silicon Crime Files: make a factual, sober tech/corporate public-record "
            "case with accurate legal status, date, official source, identifiable "
            "technical clue and documented outcome. Do not invent evidence, "
            "quotes, accusations, names, or convictions. All scenes are "
            "clearly illustrative AI reenactments, not purported documentary footage. "
            "Include source_url linking to one official public record."
        ),
        "storytelling": (
            "StoryFuse: write original cinematic live-action fiction with one "
            "memorably described protagonist, one consistent location/time, a "
            "high-stakes decision and five escalating scenes ending in a twist. "
            "Characters retain unchanged outfits and voices. No real private people."
        ),
        "kids_history": (
            "Epic History Kids: true, age-appropriate history for ages 7-12. "
            "Milo is a stable-looking 10-year-old time-travel guide and the only "
            "speaker across five continuous 3D animated scenes. Keep one place "
            "and time period and correct facts. No gore or frightening content."
        ),
        "educational": (
            "Stoic Reset: realistic continuous modern human story explaining one "
            "correct Stoic principle through an observable choice and practical "
            "action. One stable on-screen lead speaks throughout. Do not fake "
            "philosopher quotations or promise mental-health treatments."
        ),
    }
    word_budget = "55-90" if niche_key == "kids_history" else "70-110"
    extra_json = ', "source_url": "https://OFFICIAL-DOCUMENT-URL"' if niche_key == "tech_crime" else ""
    return f"""Write a unique original YouTube Short SCRIPT for native in-scene Meta AI video generation.
Niche: {niche}
Rules: {channel_rules.get(niche_key, "Grounded, continuous, visually coherent story with five connected actions.")}
Unique seed (never mention aloud): {uniqueness_seed or 'fresh original premise'}
The final film is EXACTLY five connected 10-second scenes (50 seconds):
00-10s: immediate hook; 10-20s: protagonist acts; 20-30s: evidence/conflict rises;
30-40s: decisive action/reversal; 40-50s: payoff and final image.
CRITICAL: each scene continues in the SAME place and the SAME people/wardrobe and camera direction.
All audible words must be feasible as on-screen character dialogue, generated by Meta AI, not an off-screen narrator.
Script must be {word_budget} TOTAL spoken words. Return a scene_plan with EXACTLY five rows.
Each row must contain: dialogue (one complete 5-22-word spoken line, never cut mid-sentence),
action (one precise visible action that directly advances that line), and end_frame (a concrete composition
of character positions, active prop and camera framing that the next clip can continue).
The script field MUST equal the five dialogue values joined in order. Each action must be physically filmable
in ten seconds and must preserve the same cast, location, wardrobe, props, lighting and time of day.
No external voiceover, stock footage, downloaded images, music beds, captions, slide shows, forced transitions,
intro, outro, or 'Like and Subscribe' calls to action. End on the story payoff, not a commercial prompt.
Use no fabricated facts for historical or real-world episodes.
Return JSON with title <= 60 characters, a single continuous script, scene_plan, 5 hashtag-like tags,
a search_query that briefly describes the protagonist and setting solely as text metadata.
Return ONLY valid JSON:
{{"title":"unique specific title","script":"the five dialogue lines joined in order","scene_plan":[{{"dialogue":"complete scene-one line","action":"specific visible scene-one action","end_frame":"precise final composition"}},{{"dialogue":"complete scene-two line","action":"specific visible scene-two action","end_frame":"precise final composition"}},{{"dialogue":"complete scene-three line","action":"specific visible scene-three action","end_frame":"precise final composition"}},{{"dialogue":"complete scene-four line","action":"specific visible scene-four action","end_frame":"precise final composition"}},{{"dialogue":"complete scene-five line","action":"specific visible scene-five payoff","end_frame":"precise final composition"}}],"tags":["tag1","tag2","tag3","tag4","tag5"],"search_query":"protagonist action and setting"{extra_json}}}"""


GENERIC_TITLES = {
    "tech_crime": {
        "big tech exposed",
        "corporate crime",
        "tech scam revealed",
        "the dark side of tech",
        "billion dollar scam",
    },
    "psychology": {
        "the memory trick that always works",
        "why we judge people so quickly",
        "the power of saying no",
        "mind tricks",
        "mind blown",
        "psychology facts",
    },
    "documentary": {
        "the machine that shouldnt exist",
        "lost city",
        "ancient secrets",
        "ancient technology",
        "history mystery",
    },
    "storytelling": {
        "the neighbor who regretted everything",
        "what happened next",
        "you wont believe this",
        "wait until the end",
        "a story with a twist",
    },
    "educational": {
        "burnout alert",
        "stoic motivation",
        "the secret to not caring what people think",
        "the secret to not caring",
        "burned out",
    },
}


def _normalize_title(title: str) -> str:
    """Normalize a title for template-quality checks, not upload deduplication."""
    collapsed_apostrophes = str(title).lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", collapsed_apostrophes).strip()


def _reject_generic_title(title: str, niche_key: str) -> bool:
    normalized = _normalize_title(title)
    word_count = len(normalized.split())
    return (
        not normalized
        or normalized in GENERIC_TITLES.get(niche_key, set())
        or not 4 <= word_count <= 12
        or len(str(title).strip()) >= 60
    )


def _valid_visual_packaging(result: dict, niche_key: str) -> bool:
    """No stock-media search packaging is needed for Meta-only videos."""
    if niche_key != "tech_crime":
        return True
    source = str(result.get("source_url") or "").strip()
    return source.startswith("https://") and len(source) <= 300


def _normalized_scene_plan(result: dict) -> list[dict] | None:
    """Validate the five-row production plan returned by a text provider."""
    raw = result.get("scene_plan")
    if not isinstance(raw, list) or len(raw) != 5:
        return None
    plan = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        dialogue = " ".join(str(item.get("dialogue") or "").split())
        action = " ".join(str(item.get("action") or "").split())
        end_frame = " ".join(str(item.get("end_frame") or "").split())
        if not (5 <= len(dialogue.split()) <= 22):
            return None
        if len(action.split()) < 5 or len(end_frame.split()) < 5:
            return None
        plan.append({
            "dialogue": dialogue,
            "action": action,
            "end_frame": end_frame,
        })
    return plan


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
        payload = response.json()
        items = payload if isinstance(payload, list) else payload.get("data", [])
        available = [
            item.get("id", "") for item in items
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


def _try_huggingface(prompt: str) -> dict | None:
    """Use Hugging Face's multi-provider router with live warm-model search."""
    if not HF_TOKEN:
        return None
    models: list[str] = []
    try:
        response = requests.get(
            HF_MODELS_URL,
            headers={"Authorization": f"Bearer {HF_TOKEN}"},
            params={
                "pipeline_tag": "text-generation",
                "inference": "warm",
                "sort": "trendingScore",
                "limit": 12,
            },
            timeout=(8, 20),
        )
        response.raise_for_status()
        ids = [
            item.get("id", "") for item in response.json()
            if isinstance(item, dict) and item.get("id")
        ]
        models = [f"{model}:fastest" for model in ids[:8]]
        if models:
            print(f"[ScriptGen] Hugging Face catalog: {len(models)} warm text models")
    except Exception as error:
        _log_provider_error("Hugging Face model discovery", error)
    if not models:
        # Router policy aliases choose the currently fastest backing provider.
        models = [
            "openai/gpt-oss-120b:fastest",
            "Qwen/Qwen3-4B-Thinking-2507:fastest",
        ]
    return _try_openai_chat_provider(
        "Hugging Face Router", HF_CHAT_URL, HF_TOKEN, prompt, models
    )


def _try_mistral(prompt: str) -> dict | None:
    if not MISTRAL_API_KEY:
        return None
    models = _discover_openai_models(
        "Mistral",
        MISTRAL_MODELS_URL,
        MISTRAL_API_KEY,
        ("mistral-small-latest", "ministral-8b-latest"),
    )
    return _try_openai_chat_provider(
        "Mistral", MISTRAL_URL, MISTRAL_API_KEY, prompt, models
    )


def _try_nvidia(prompt: str) -> dict | None:
    if not NVIDIA_API_KEY:
        return None
    models = _discover_openai_models(
        "NVIDIA NIM",
        NVIDIA_MODELS_URL,
        NVIDIA_API_KEY,
        ("openai/gpt-oss-20b", "meta/llama-3.3-70b-instruct"),
    )
    return _try_openai_chat_provider(
        "NVIDIA NIM", NVIDIA_URL, NVIDIA_API_KEY, prompt, models
    )


def _try_cloudflare(prompt: str) -> dict | None:
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ACCOUNT_ID:
        return None
    base = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{CLOUDFLARE_ACCOUNT_ID}/ai"
    )
    try:
        response = requests.get(
            f"{base}/models/search",
            headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
            params={
                "task": "Text Generation",
                "hide_experimental": "true",
                "include_deprecated": "false",
                "per_page": 50,
            },
            timeout=(8, 20),
        )
        response.raise_for_status()
        items = response.json().get("result", [])
        models = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model = item.get("name") or item.get("id") or item.get("model") or ""
            if model.startswith("@cf/"):
                models.append(model)
        models = models[:8]
        if not models:
            raise RuntimeError("Cloudflare returned no active text-generation models")
        print(f"[ScriptGen] Cloudflare catalog: {len(models)} active text models")
        return _try_openai_chat_provider(
            "Cloudflare Workers AI",
            f"{base}/v1/chat/completions",
            CLOUDFLARE_API_TOKEN,
            prompt,
            models,
        )
    except Exception as error:
        _log_provider_error("Cloudflare Workers AI", error)
        return None


def _try_cohere(prompt: str) -> dict | None:
    """Use Cohere's native v2 JSON chat API and live nondeprecated catalog."""
    if not COHERE_API_KEY:
        return None
    headers = {
        "Authorization": f"Bearer {COHERE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        catalog = requests.get(
            COHERE_MODELS_URL,
            headers=headers,
            params={"endpoint": "chat", "page_size": 1000},
            timeout=(8, 20),
        )
        catalog.raise_for_status()
        models = [
            item.get("name", "") for item in catalog.json().get("models", [])
            if isinstance(item, dict)
            and not item.get("is_deprecated", False)
            and "chat" in item.get("endpoints", [])
        ]
        models = _ordered_text_models(
            models, ("command-a-plus-05-2026", "command-a-03-2025")
        )
        print(f"[ScriptGen] Cohere catalog: {len(models)} active chat models")
        for model in models:
            for json_mode in (True, False):
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500,
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                response = requests.post(
                    COHERE_URL,
                    headers=headers,
                    json=payload,
                    timeout=(8, 25),
                )
                if response.status_code == 429:
                    print("[ScriptGen] Cohere rate-limited -> next provider")
                    return None
                if response.status_code in (400, 404, 422):
                    if json_mode:
                        continue
                    break
                if response.status_code in (401, 403, 498):
                    response.raise_for_status()
                response.raise_for_status()
                blocks = response.json()["message"]["content"]
                text = next(
                    block["text"] for block in blocks
                    if isinstance(block, dict) and block.get("type") == "text"
                )
                result = _parse_json(text)
                print(f"[ScriptGen] Script via Cohere ({model})")
                return result
        return None
    except Exception as error:
        _log_provider_error("Cohere", error)
        return None


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


def _try_ai_horde(prompt: str) -> dict | None:
    """Use AI Horde's free volunteer text queue as the final online fallback."""
    if not AI_HORDE_ENABLED:
        return None
    try:
        from modules.ai_horde import generate_text

        result = generate_text(prompt)
        if result:
            print("[ScriptGen] Script via AI Horde free community queue")
        return result
    except Exception as error:
        _log_provider_error("AI Horde", error)
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


# Spoken native-audio words for 50 seconds in five consecutive Meta scenes.
MIN_WORDS = 55
MAX_WORDS = 110


def _post_process_script(script: str) -> str:
    """Remove old out-of-story CTA; keep original dialogue punctuation intact."""
    cleaned = re.sub(
        r"\s*(?:Like and Subscribe for more|Subscribe for more|Like and subscribe)[.!?]*\s*$",
        "", str(script).strip(), flags=re.I,
    ).strip()
    return cleaned


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
        (_try_huggingface, "Hugging Face Router"),
        (_try_mistral, "Mistral"),
        (_try_nvidia, "NVIDIA NIM"),
        (_try_cloudflare, "Cloudflare Workers AI"),
        (_try_openrouter, "OpenRouter Free"),
        (_try_cerebras, "Cerebras"),
        (_try_cohere, "Cohere"),
        (_try_gemini, "Gemini"),
        (_try_nova, "Nova"),
        (_try_claude, "Claude"),
        (_try_amazon, "Amazon Bedrock"),
        (_try_ai_horde, "AI Horde"),
    ]
    niche_key = _detect_niche_key(niche)
    if niche_key == "kids_history":
        min_words, max_words = (50, 95)
    elif niche_key == "storytelling":
        min_words, max_words = (65, 110)
    else:
        min_words, max_words = (MIN_WORDS, MAX_WORDS)

    for fn, name in providers:
        result = fn(prompt)
        if not result:
            continue
        if not all(k in result for k in ("title", "script", "tags", "search_query")):
            continue

        if niche_key != "kids_history" and _reject_generic_title(result["title"], niche_key):
            print(f"[ScriptGen] {name}: generic or weak title rejected -> next provider")
            continue
        if not _valid_visual_packaging(result, niche_key):
            print(f"[ScriptGen] {name}: missing required factual source metadata -> next provider")
            continue

        scene_plan = _normalized_scene_plan(result)
        if scene_plan is None:
            print(f"[ScriptGen] {name}: invalid five-scene production plan -> next provider")
            continue
        result["scene_plan"] = scene_plan

        # The exact spoken script is derived from the validated rows, preventing
        # a provider from returning one story in `script` and different lines in
        # the production plan.
        result["script"] = _post_process_script(
            " ".join(scene["dialogue"] for scene in scene_plan)
        )

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
        if (
            (key != "kids_history" and _reject_generic_title(fallback["title"], key))
            or not _valid_visual_packaging(fallback, key)
        ):
            continue
        fallback["script"] = _post_process_script(fallback["script"])
        if reject_candidate is not None and reject_candidate(fallback):
            continue
        print("[ScriptGen] All providers failed -> unused fallback")
        return fallback

    raise ScriptGenerationError(
        "All AI providers and fallback prompts were exhausted without a unique script."
    )
