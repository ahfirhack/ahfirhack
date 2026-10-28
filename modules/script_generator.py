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
    niche_key = _detect_niche_key(niche)
    kids_history = niche_key == "kids_history"
    length_rule = (
        "50-65 words, written for a 30-second narration."
        if kids_history else (
            "70-80 words, written for a tightly paced 30-second story."
            if niche_key == "storytelling" else
            "80-90 words, written for a 30-40 second narration."
        )
    )
    json_length = (
        "50-65" if kids_history else
        ("70-80" if niche_key == "storytelling" else "80-90")
    )
    kids_rules = """
KIDS' HISTORY EPISODE RULES:
- Tell one accurate, chronological story with three clear visual beats.
- Use simple language for ages 7-12 and no graphic violence, fear, or adult themes.
- Milo is the recurring ten-year-old time-travel guide and the only speaker. Write the exact words Milo says; never add another narrator or character voice.
- Group the narration into three concrete visual beats, one for each ten-second animated scene.
- Never change Milo's appearance, clothing, age, or personality.
""" if kids_history else ""
    non_kids_rules = {
        "tech_crime": """
SILICON CRIME FILES — HIGH-STAKES TECH TRUE-CRIME RULES:
- Cover one specific, well-documented public case. Use verifiable names, dates, amounts, technical details, and outcomes from court records, regulator findings, company filings, public hearings, or established reporting.
- Never invent a leak, email, code fragment, quote, victim, allegation, or dollar figure. If a detail is uncertain, disputed, or unsupported, omit it and choose a better-documented case.
- State legal status precisely: alleged, charged, settled without admission, found liable, pleaded guilty, or convicted are not interchangeable. Do not imply guilt beyond the public record.
- Do not identify private individuals, expose personal data, glamorize offenders, give operational crime instructions, or turn victim harm into spectacle.
- 0:00-0:05 HOOK: Lead with the largest documented contradiction, consequence, dollar amount, or technical clue. No greeting and no background setup.
- 0:05-0:14 CASE: Name the company or public figure, the year, what was publicly claimed, and what investigators or evidence showed.
- 0:14-0:28 EVIDENCE: Deliver two fast micro-reveals—an official document, code detail, transaction, testimony, timeline conflict, or regulatory finding. Each reveal must raise the stakes.
- NEAR END PAYOFF: State the documented consequence or unresolved question, then loop naturally to the opening clue before the final CTA.
- Title: 5-10 words, under 60 characters, containing the specific company, product, person, amount, or technical contradiction. Never use generic titles such as "Big Tech Exposed", "Corporate Crime", or "Tech Scam Revealed".
- hook_overlay: 4-8 urgent words that communicate the case contradiction without unsupported clickbait.
- hook_accent: exactly one short, visually powerful documented element—prefer a dollar amount such as "$5 BILLION" or a technical clue such as "SEMICOLON". Do not invent it.
- evidence_label: a short public-record label such as "SEC COMPLAINT // 2018", "COURT EXHIBIT // 2022", or "PUBLIC HEARING // 2024". It must match the episode's real evidence.
- source_url: the direct HTTPS URL of the official public record supporting the episode. Prefer a court, regulator, or government source; never return a search page or social-media post.
- First visual query: real public evidence context where available—official filing, public hearing, dated corporate statement, court exhibit, or terminal evidence recreation. Never call a recreation a real leaked document.
""",
        "psychology": """
MINDSPARK SECRETS EPISODE RULES:
- Build the episode around one specific, scientifically grounded behavior mechanism or cognitive bias.
- Open with a relatable moment that makes viewers recognize themselves, then explain why it happens and end with one practical action.
- Do not diagnose viewers, promise medical results, or present weak pop-psychology claims as settled science.
- The title must create a curiosity gap around the exact behavior. Never use generic titles such as "Mind Tricks", "Mind Blown", or "Psychology Facts".
- Give the search query a concrete person, action, setting, and visible emotion that can support three polished visual beats.
""",
        "documentary": """
PAST UNSEALED EPISODE RULES:
- Center the episode on one real named artifact, site, person, document, invention, or event—not a generic ancient mystery.
- Separate verified evidence from uncertainty. Never invent discoveries, exaggerate scholarly claims, or use pseudo-history as fact.
- Structure three cinematic beats: the discovery, the strongest evidence, and the unresolved question or revealing conclusion.
- Put the specific proper noun or place in a curiosity-driven title. Never use "The Machine That Shouldn't Exist", "Lost City", or "Ancient Secrets" by themselves.
- Make the search query historically specific, visual, and filmable, including the subject, location or era, and an action or camera detail.
""",
        "storytelling": """
STORYFUSE HIGH-RETENTION FRAMEWORK — COMPRESS THIS INTO 30 SECONDS:
- 0:00-0:03 THE HOOK: Open on a jaw-dropping climax fragment, contradiction, impossible choice, or consequence. Withhold the explanation. No greetings or setup filler.
- 0:03-0:10 THE INCIDENT: Name one memorable main character, reveal the triggering event, and make the stakes immediately clear.
- 0:10-0:22 THE ESCALATION: Deliver two or three concrete micro-reveals. Each reveal must change the viewer's understanding, raise the cost, and arrive every 4-6 seconds.
- 0:22-0:28 THE CLIMAX: Pay off the central mystery with a sharp reveal, irreversible decision, or emotionally satisfying reversal.
- 0:28-0:30 THE LOOP/CTA: Write a punchy final line that naturally reframes the opening image, then end with "Like and Subscribe for more". Do not repeat the first sentence verbatim.
- Use one clear protagonist, one central conflict, active verbs, concrete sensory detail, and short spoken sentences. Every sentence must advance the story.
- Prefer original cinematic fiction about impossible choices, survival, loyalty, betrayal, sacrifice, mystery, or consequences. Never claim an invented story is true. Do not use real private people, graphic violence, cruelty, or exploitative tragedy.
- Title: 5-9 words that tease the central contradiction without spoiling the climax. Avoid vague templates such as "What Happened Next", "You Won't Believe This", or "The Neighbor Who Regretted Everything".
- The search query must depict the hook's exact character, action, setting, mood, lighting, and camera framing for visually coherent footage.
""",
        "educational": """
STOIC RESET EPISODE RULES:
- Start with one precise modern struggle such as overthinking a message, workplace criticism, envy, procrastination, or losing control in an argument.
- Explain one accurate Stoic principle, then give one small action the viewer can take today.
- Paraphrase ancient thinkers unless a quotation is verified. Never invent or misattribute a quote, and never make mental-health treatment claims.
- The title must pair a recognizable pain point with a clear emotional promise. Never use generic titles such as "Burnout Alert", "Stoic Motivation", or "The Secret to Not Caring".
- Use three visually distinct beats and a concrete search query showing a person taking an observable action in a modern setting.
""",
    }.get(niche_key, """
EPISODE QUALITY RULES:
- Cover one specific subject through three visually distinct beats and finish with one practical takeaway.
- Keep every factual claim supportable and avoid generic motivation or exaggerated promises.
""") if not kids_history else ""
    non_kids_global_rules = """
9. TITLE: Use 5-10 words and stay under 60 characters. Make it specific, natural, and curiosity-driven. No episode numbers, vague clickbait, all caps, or recycled title templates.
10. VISUAL PACING: Write three connected beats that can be illustrated cleanly without dead space. Each beat must add new information and maintain forward motion.
""" if not kids_history else ""
    non_kids_visual_rule = """
VISUAL SEQUENCE RULE: Also return visual_queries as exactly three concrete stock-footage searches in story order—hook, escalation, payoff. Each query must name a visible subject, action, setting, mood or lighting, and camera framing. For a story, repeat the protagonist's same visible traits in every query so the footage feels continuous.
""" if not kids_history else ""
    if niche_key == "tech_crime":
        non_kids_json_field = (
            ', "visual_queries": ["evidence hook shot", "investigation shot", "consequence shot"]'
            ', "hook_overlay": "four-to-eight word case contradiction"'
            ', "hook_accent": "one documented amount or technical clue"'
            ', "evidence_label": "named public record and year"'
            ', "source_url": "direct official HTTPS public-record URL"'
        )
    elif not kids_history:
        non_kids_json_field = (
            ', "visual_queries": ["hook shot", "escalation shot", "payoff shot"]'
        )
    else:
        non_kids_json_field = ""
    unique_focus = (
        "historical subject and angle"
        if kids_history else
        "subject, premise, and angle"
    )
    uniqueness_rule = (
        f"UNIQUE EPISODE SEED: {uniqueness_seed}. Use this seed to choose a fresh "
        f"{unique_focus}. Never mention the seed in the output."
        if uniqueness_seed else
        "Choose a fresh subject and angle that is unlikely to repeat an earlier episode."
    )
    return f"""You are a viral YouTube Shorts scriptwriter optimized for human-like VOICE narration.

Niche: {niche}
{kids_rules}
{non_kids_rules}
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
{non_kids_global_rules}

SEARCH QUERY RULE: The search_query must describe CLEAR VISUAL ACTION for stock footage.
GOOD: "person studying english book", "teacher writing on whiteboard", "student taking notes"
BAD: "success", "mystery", "hacks"
{non_kids_visual_rule}

Respond ONLY with valid JSON (no markdown, no backticks):
{{"title": "Searchable title under 60 chars", "script": "{json_length} word voice-ready script ending with Like and Subscribe for more", "tags": ["tag1","tag2","tag3","tag4","tag5"], "search_query": "specific visual description"{non_kids_json_field}}}"""


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
    """Require the beat metadata used to keep footage and narration aligned."""
    if niche_key == "kids_history":
        return True
    visual_queries = result.get("visual_queries")
    if (
        not isinstance(visual_queries, list)
        or len(visual_queries) != 3
        or any(not isinstance(query, str) or len(query.split()) < 4 for query in visual_queries)
    ):
        return False
    if niche_key != "tech_crime":
        return True
    hook_overlay = str(result.get("hook_overlay", "")).strip()
    hook_accent = str(result.get("hook_accent", "")).strip()
    evidence_label = str(result.get("evidence_label", "")).strip()
    source_url = str(result.get("source_url", "")).strip()
    return (
        4 <= len(hook_overlay.split()) <= 8
        and 1 <= len(hook_accent.split()) <= 4
        and 2 <= len(evidence_label.split()) <= 7
        and len(hook_overlay) <= 64
        and len(hook_accent) <= 32
        and len(evidence_label) <= 52
        and source_url.startswith("https://")
        and len(source_url) <= 300
    )


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
    if niche_key == "kids_history":
        min_words, max_words = (48, 70)
    elif niche_key == "storytelling":
        min_words, max_words = (68, 85)
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
            print(f"[ScriptGen] {name}: incomplete visual timing pack rejected -> next provider")
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
