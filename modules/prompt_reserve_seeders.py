"""Deterministic offline prompt packs for non-kids channel reserves.

StoryFuse and Stoic Reset each receive 2,048 structurally unique prompts. The
technology true-crime reserve deliberately stays limited to the small set of
public-record prompts verified in ``script_generator``; manufacturing thousands
of unverified crime claims would undermine the channel's factual safeguards.
"""

from __future__ import annotations

import hashlib


SEED_VERSIONS = {
    "channel_1": "silicon-crime-public-record-v1",
    "channel_2": "storyfuse-retention-v1",
    "channel_4": "stoic-reset-practical-v2",
}

CTA = "Like and Subscribe for more."


def _fingerprint(channel_id: str, title: str, script: str) -> str:
    return hashlib.sha256(
        f"{SEED_VERSIONS[channel_id]}|{title}|{script}".encode("utf-8")
    ).hexdigest()


def _fit_script(parts: list[str], *, minimum: int, maximum: int) -> str:
    pads = [
        "Every new detail made the first warning harder to ignore.",
        "The deadline kept moving closer while the evidence changed shape.",
        "One small choice now carried a consequence no one expected.",
        "Nothing about the opening clue felt accidental anymore.",
    ]
    body = list(parts)
    pad_index = 0
    while len(" ".join(body + [CTA]).split()) < minimum:
        body.insert(-1 if body else 0, pads[pad_index % len(pads)])
        pad_index += 1
    script = " ".join(body + [CTA])
    if len(script.split()) > maximum:
        raise RuntimeError(
            f"Reserve script is too long ({len(script.split())}>{maximum}): {script}"
        )
    return script


STORY_PROTAGONISTS = [
    ("Mara", "paramedic", "young woman with a red raincoat and dark braid"),
    ("Elias", "night dispatcher", "young man with a charcoal jacket and round glasses"),
    ("Nina", "forensic accountant", "woman with a navy coat and silver-streaked hair"),
    ("Jonah", "train conductor", "man with a forest-green uniform and short beard"),
    ("Leila", "emergency engineer", "woman with a yellow field jacket and curly hair"),
    ("Adrian", "court translator", "man with a burgundy scarf and close-cropped hair"),
    ("Sofia", "museum archivist", "woman with a cream trench coat and black bob haircut"),
    ("Malik", "radio producer", "man with a blue hoodie and silver headphones"),
    ("Tessa", "investigative photographer", "woman with an olive jacket and copper curls"),
    ("Ravi", "systems technician", "man with a gray work shirt and messenger bag"),
    ("Camille", "public defender", "woman with a black blazer and gold hair clip"),
    ("Noah", "bridge inspector", "man with an orange safety coat and shaved head"),
    ("Imani", "hotel manager", "woman with a plum suit and long braids"),
    ("Theo", "air-traffic analyst", "man with a navy sweater and sandy hair"),
    ("Ava", "restoration artist", "woman with a teal cardigan and short curls"),
    ("Daniel", "hospital porter", "man with a maroon jacket and wavy dark hair"),
]

STORY_SETTINGS = [
    ("Night Train", "aboard the last night train", "rainy night train carriage"),
    ("Empty Hotel", "inside an empty coastal hotel", "empty coastal hotel corridor at night"),
    ("Flooded Tunnel", "beneath a flooded city tunnel", "flooded city tunnel under emergency lights"),
    ("Closed Museum", "inside a museum after closing", "dark museum archive after closing"),
    ("Radio Tower", "at an isolated radio tower", "isolated radio tower during a storm"),
    ("Silent Airport", "inside a silent airport terminal", "deserted airport terminal before dawn"),
    ("Mountain Clinic", "at a snowbound mountain clinic", "snowbound mountain clinic at night"),
    ("Old Courthouse", "beneath an old courthouse", "old courthouse records basement"),
]

STORY_SCENARIOS = [
    ("Call From Tomorrow", "The call came from tomorrow", "a phone displaying tomorrow's date", "a second call repeated words not yet spoken", "the caller was using a recorder hidden in the room", "played the warning backward and found the safe exit", "TOMORROW", "glowing phone with impossible future timestamp"),
    ("Letter With Her Signature", "The warning carried a familiar signature", "a sealed letter signed in their own handwriting", "the ink was fresh but the paper was decades old", "the message described a decision happening that night", "followed the final line and reached the missing witness", "HER SIGNATURE", "sealed letter with matching handwritten signature"),
    ("Camera Saw Them Twice", "The camera recorded the impossible", "security footage showing them in two places", "each replay revealed another figure moving closer", "the second figure was copying their route to trigger an alarm", "changed direction and trapped the watcher on camera", "TWO VERSIONS", "security monitor showing same person twice"),
    ("Ticket to a Closed Station", "The ticket named a nonexistent station", "a train ticket printed for a demolished station", "the platform clock began counting backward", "the old route concealed an emergency passage", "used the forgotten passage before the main exit failed", "CLOSED STATION", "vintage train ticket to abandoned station"),
    ("Voicemail After the Funeral", "A voicemail arrived from a silent number", "a voicemail recorded after its owner disappeared", "background bells matched the place around them", "the message was scheduled to expose a hidden handoff", "followed the bells and recovered the evidence", "ONE LAST MESSAGE", "phone voicemail waveform beside old photograph"),
    ("Key With No Door", "The key opened nothing anyone could see", "a brass key with coordinates instead of teeth", "the coordinates pointed beneath the floor", "the key was a map for a mechanical lock", "aligned the markings and opened the sealed compartment", "NO VISIBLE DOOR", "brass key engraved with map coordinates"),
    ("Elevator Missing a Floor", "The elevator stopped between every listed floor", "an elevator panel showing an unmarked level", "the security log erased the same minute nightly", "the missing level held the building's emergency controls", "restored the controls before the blackout reached the street", "UNMARKED FLOOR", "elevator panel with hidden glowing button"),
    ("Photo Taken Next Week", "The photograph showed next week", "a printed photograph dated one week ahead", "a reflected clock revealed an exact deadline", "the scene was a warning staged by someone inside", "changed one object and exposed who arranged it", "NEXT WEEK", "future-dated photograph under forensic light"),
    ("Map That Changed Overnight", "The map redrew itself before sunrise", "a paper map with a new route in wet ink", "the route avoided every working camera", "the detour marked where a witness had hidden proof", "took the visible road while sending help through the hidden one", "NEW ROUTE", "paper city map changing under red light"),
    ("Alarm Only One Person Heard", "The alarm sounded for only one person", "an emergency tone hidden inside ordinary music", "the pattern matched a building access code", "someone had embedded a warning without stopping the broadcast", "entered the code and prevented the locked-room trap", "HIDDEN FREQUENCY", "audio waveform revealing secret alarm pattern"),
    ("Clock That Lost Nine Minutes", "Nine minutes vanished from every clock", "a stopped watch matching the missing interval", "camera timestamps jumped across the same gap", "the missing minutes concealed a deliberate system reset", "reconstructed the gap from reflections in the footage", "NINE MINUTES", "stopped watch beside corrupted timestamps"),
    ("Room With Two Shadows", "The room held one person and two shadows", "a lamp casting an impossible second silhouette", "the extra shadow moved before the person did", "a hidden projector was signaling the next target", "blocked the beam and reversed the signal", "SECOND SHADOW", "empty room with two conflicting shadows"),
    ("Receipt for an Unmade Purchase", "The receipt listed something never bought", "a receipt printed before the store opened", "its item codes spelled a location", "the transaction was a distress message from an employee", "decoded the location and reached them first", "IMPOSSIBLE RECEIPT", "future-dated receipt with coded item numbers"),
    ("Door Locked From Both Sides", "The locked door had two different keys", "a door secured from both sides without damage", "dust showed one lock had turned by itself", "a timed mechanism created the impossible scene", "stopped the timer and revealed the staged disappearance", "TWO LOCKS", "double-locked door under forensic flashlight"),
    ("Broadcast From an Empty Studio", "The live broadcast came from an empty room", "a radio transmission with no visible speaker", "the pauses matched lights across the skyline", "the signal was guiding rescuers to a trapped crew", "answered with the tower lights and opened their route", "EMPTY STUDIO", "empty radio studio with live signal meters"),
    ("Name Erased From Every Record", "By midnight one name had disappeared", "a personnel file erased across every system", "one paper copy retained a pressure mark", "the erasure protected a witness rather than hiding a suspect", "followed the impression and preserved the witness's choice", "ERASED NAME", "redacted personnel file with hidden indentation"),
]


def _storyfuse_prompts() -> list[dict]:
    prompts: list[dict] = []
    for name, role, appearance in STORY_PROTAGONISTS:
        for setting_title, setting_phrase, setting_visual in STORY_SETTINGS:
            for (
                scenario_title, overlay, object_phrase, escalation, reveal,
                decision, accent, object_visual,
            ) in STORY_SCENARIOS:
                title = f"{name}'s {scenario_title} — {setting_title}"
                script = _fit_script([
                    f"{overlay}, and {name} had seconds to decide whether it was real.",
                    f"{name}, a {role}, found {object_phrase} {setting_phrase}.",
                    f"Then {escalation}.",
                    f"The next clue revealed {reveal}.",
                    f"Instead of running, {name} {decision}.",
                    "The opening warning had become the only way out.",
                ], minimum=70, maximum=85)
                record = {
                    "title": title,
                    "script": script,
                    "tags": ["storyfuse", "shortstory", "plottwist", "mystery", "suspense"],
                    "search_query": f"{appearance} {object_visual} {setting_visual} cinematic",
                    "visual_queries": [
                        f"{appearance} discovers {object_visual} in {setting_visual} dramatic close up",
                        f"{appearance} follows urgent clue through {setting_visual} handheld suspense shot",
                        f"{appearance} makes final decision in {setting_visual} cinematic wide shot",
                    ],
                    "hook_overlay": overlay.upper(),
                    "hook_accent": accent,
                }
                record["fingerprint"] = _fingerprint("channel_2", title, script)
                prompts.append(record)
    return prompts


STOIC_STRUGGLES = [
    ("Harsh Message", "ONE MESSAGE HIJACKED YOUR DAY", "professional reading harsh phone message", "another person's wording"),
    ("Public Criticism", "THE ROOM HEARD YOUR MISTAKE", "professional facing criticism in meeting", "the room's first reaction"),
    ("Ignored Reply", "THE SILENCE FEELS PERSONAL", "person checking unanswered message", "when someone replies"),
    ("Missed Promotion", "THE PROMOTION WENT ELSEWHERE", "employee watching colleague receive promotion", "the decision already made"),
    ("Broken Promise", "THE PROMISE DID NOT SURVIVE", "person holding cancelled calendar note", "another person's consistency"),
    ("Sudden Rejection", "THE ANSWER WAS SIMPLY NO", "person reading rejection email", "the answer already received"),
    ("Office Rumor", "THE RUMOR MOVED FASTER", "employee overhearing office rumor", "what others repeat"),
    ("Lost Opportunity", "THE DOOR CLOSED WITHOUT WARNING", "person outside closed office door", "the opportunity that passed"),
    ("Jealous Comparison", "THEIR SUCCESS SHRANK YOURS", "person comparing career updates online", "another person's progress"),
    ("Unfair Blame", "THE BLAME LANDED ON YOU", "worker receiving unfair blame", "someone else's accusation"),
    ("Last-Minute Change", "THE PLAN CHANGED AT MIDNIGHT", "person seeing sudden schedule change", "the change already announced"),
    ("Failed Project", "MONTHS OF WORK JUST FAILED", "professional viewing failed project dashboard", "the result already recorded"),
    ("Difficult Customer", "THE ANGER ARRIVED AT YOU", "worker facing angry customer", "the customer's emotional state"),
    ("Family Pressure", "THEIR EXPECTATION BECAME YOUR WEIGHT", "person reading demanding family message", "the expectations of relatives"),
    ("Online Insult", "A STRANGER DEFINED YOU", "person seeing hostile online comment", "a stranger's opinion"),
    ("Unexpected Delay", "THE WAIT DESTROYED YOUR PLAN", "traveler facing delayed departure board", "the delay itself"),
]

STOIC_PRINCIPLES = [
    ("Control", "Dichotomy of Control", "separate what depends on your choices from what does not"),
    ("Judgment", "Examine the Judgment", "distinguish the event from the story your mind added"),
    ("Reserve", "Use the Reserve Clause", "act fully while remembering outcomes are never entirely yours"),
    ("Obstacle", "Work With the Obstacle", "turn the obstruction into material for your next good action"),
    ("Impermanence", "Remember Impermanence", "view the pressure as temporary rather than permanent"),
    ("Role", "Choose Your Role", "respond according to the character and duty you want to embody"),
    ("Perspective", "Take the Wider View", "shrink the moment by placing it inside a longer timeline"),
    ("Preparation", "Rehearse the Setback", "prepare a calm response before the feared event arrives"),
]

STOIC_ACTIONS = [
    ("Two Columns", "draw two columns labeled control and not control, then sort each fact", "writing two columns in notebook", "the next decision becomes smaller and clearer"),
    ("Delay Reply", "wait ten measured breaths before typing a response", "placing phone face down and breathing slowly", "the reply serves your values instead of the first emotion"),
    ("Facts Only", "rewrite the event using only facts a camera could record", "crossing emotional labels from written note", "the mind loses the exaggeration that fed the pressure"),
    ("Next Action", "name the smallest useful action available in the next five minutes", "circling one next action on paper", "motion replaces helpless rehearsal"),
    ("Role Sentence", "finish the sentence, the person I choose to be now will", "writing a role sentence on card", "identity guides the response before emotion does"),
    ("Worst Case", "write the realistic worst case and one prepared response", "writing contingency plan at desk", "uncertainty becomes a plan rather than a fog"),
    ("View Above", "picture the room from far above and reduce the argument to its true size", "looking over city from quiet window", "the moment stops pretending to be your whole life"),
    ("One Hour", "ask whether this deserves the next hour of attention", "setting one-hour timer beside phone", "attention returns to work that belongs to you"),
    ("Name the Cost", "write what an impulsive reaction would cost tomorrow", "listing consequences beside draft reply", "tomorrow's values interrupt today's impulse"),
    ("Speak Slowly", "lower your pace and answer with one sentence fewer", "speaking calmly in tense meeting", "restraint keeps the conflict from choosing your words"),
    ("Private Standard", "judge the response by your standard rather than the audience's applause", "reviewing personal principles card", "character replaces reputation as the scoreboard"),
    ("Physical Reset", "unclench your hands, lower your shoulders, and take one slow breath", "relaxing hands before responding", "the body stops sending the mind an emergency signal"),
    ("Remove Assumption", "cross out every claim about what the other person secretly intended", "removing assumptions from journal page", "the real problem becomes smaller than the imagined one"),
    ("Accept Then Act", "say this has happened, then identify what remains possible", "turning page from problem to action", "acceptance clears space for effective action"),
    ("Quiet Rehearsal", "practice the calm sentence aloud before entering the room", "rehearsing calm response before meeting", "preparation gives composure somewhere to stand"),
    ("Evening Review", "review the response tonight without praise or punishment, only correction", "writing evening reflection under warm lamp", "the mistake becomes training instead of identity"),
]


def _stoic_prompts() -> list[dict]:
    prompts: list[dict] = []
    for struggle, overlay, struggle_visual, outside in STOIC_STRUGGLES:
        for principle_short, principle_title, principle_text in STOIC_PRINCIPLES:
            for action_short, instruction, action_visual, payoff in STOIC_ACTIONS:
                title = f"{struggle}? Try {action_short} ({principle_short})"
                script = _fit_script([
                    f"{overlay.title()}, and your first reaction wants control immediately.",
                    f"Stoic practice begins when you {principle_text}.",
                    f"Right now, {instruction}.",
                    f"You cannot command {outside}, but you can choose the quality of your next response.",
                    f"When you do, {payoff}.",
                    "Pressure can remain without writing your character.",
                ], minimum=80, maximum=90)
                record = {
                    "title": title,
                    "script": script,
                    "tags": ["stoicism", "stoicreset", "selfcontrol", "resilience", "mindset"],
                    "search_query": f"{struggle_visual} then {action_visual} cinematic",
                    "visual_queries": [
                        f"{struggle_visual} tense modern setting cinematic close up",
                        f"person {action_visual} deliberate movement medium shot",
                        "same person calm composed posture warm sunrise wide shot",
                    ],
                    "hook_overlay": overlay,
                    "hook_accent": principle_title.upper(),
                }
                record["fingerprint"] = _fingerprint("channel_4", title, script)
                prompts.append(record)
    return prompts


def build_channel_prompts(channel_id: str) -> list[dict]:
    if channel_id == "channel_1":
        # Lazily import the canonical, officially sourced case packs.
        from modules.script_generator import FALLBACK_SCRIPTS

        prompts = []
        for source in FALLBACK_SCRIPTS["tech_crime"]:
            record = dict(source)
            record["fingerprint"] = _fingerprint(
                channel_id, record["title"], record["script"]
            )
            prompts.append(record)
        return prompts
    if channel_id == "channel_2":
        return _storyfuse_prompts()
    if channel_id == "channel_4":
        return _stoic_prompts()
    raise ValueError(f"No non-kids reserve seeder for {channel_id}")
