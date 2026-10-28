"""Transactional SQLite reserves of unique prompts for every channel.

AI providers remain the primary prompt source. This reserve is used only when
every configured provider fails. A row is reserved before rendering and is
deleted only after YouTube confirms a successful upload.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

# GitHub Actions invokes this file directly. Add the repository root before
# importing sibling modules so both ``python modules/prompt_reserve.py`` and
# ``python -m modules.prompt_reserve`` behave identically.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.prompt_reserve_seeders import SEED_VERSIONS, build_channel_prompts

KIDS_SEED_VERSION = "kids-history-v1"
STALE_RESERVATION_HOURS = 6

# subject, historical setting, concise kid-safe fact
TOPICS = [
    ("Ancient Egyptian farming", "the Nile Valley", "Annual Nile floods left rich soil where farmers grew wheat, barley, vegetables, and flax."),
    ("Egyptian hieroglyphs", "ancient Egypt", "Scribes combined sound signs and picture symbols on monuments, pottery, and papyrus."),
    ("The Great Pyramid", "Giza around 2600 BCE", "Skilled crews moved and fitted enormous stone blocks to build Pharaoh Khufu's pyramid."),
    ("Mesopotamian cuneiform", "ancient Mesopotamia", "Scribes pressed wedge-shaped marks into damp clay tablets and dried them for storage."),
    ("The wheel in Mesopotamia", "Mesopotamia", "Early wheels helped potters shape clay before wheeled carts carried heavy loads."),
    ("Babylonian astronomy", "ancient Babylon", "Observers recorded the Moon, planets, and eclipses on clay tablets across many generations."),
    ("Indus Valley city drains", "Mohenjo-daro", "Builders connected brick houses to covered street drains in a carefully planned city."),
    ("Harappan weights", "the Indus Valley", "Merchants used carefully sized stone weights to measure goods consistently during trade."),
    ("Shang bronze casting", "Shang dynasty China", "Craft workers used piece-mold casting to create detailed bronze vessels for ceremonies."),
    ("Chinese oracle bones", "Shang dynasty China", "Questions were carved on turtle shells or animal bones before heat formed interpreted cracks."),
    ("Great Wall signal towers", "Ming dynasty China", "Guards relayed warnings between watchtowers using smoke by day and fire after dark."),
    ("Ancient Chinese paper", "Han dynasty China", "Paper makers pulped plant fibers, spread them on screens, and dried thin writing sheets."),
    ("The Silk Roads", "ancient Eurasia", "Networks of traders carried silk, glass, spices, stories, and inventions between distant regions."),
    ("Phoenician sailing", "the ancient Mediterranean", "Phoenician crews navigated sturdy trading ships between ports across the Mediterranean."),
    ("Phoenician alphabet", "the eastern Mediterranean", "A compact set of consonant signs made everyday writing easier for many traders."),
    ("Minoan palaces", "Bronze Age Crete", "Large palace centers contained workshops, storage rooms, courtyards, and colorful wall paintings."),
    ("Greek theater", "classical Athens", "Actors performed tragedies and comedies in open-air theaters with carefully designed acoustics."),
    ("The Antikythera mechanism", "the ancient Greek world", "Interlocking bronze gears modeled cycles of the Sun, Moon, and eclipses."),
    ("Ancient Olympic games", "Olympia in ancient Greece", "Athletes from Greek city-states competed in running, wrestling, and other events."),
    ("Roman roads", "the Roman Empire", "Surveyors and builders layered stone and gravel to create durable routes between cities."),
    ("Roman aqueducts", "the Roman world", "Gravity carried fresh water along gently sloping channels into towns and cities."),
    ("Roman concrete", "ancient Rome", "Builders mixed lime, water, stone, and volcanic material to make long-lasting structures."),
    ("Pompeii's shops", "Pompeii before 79 CE", "Excavated counters, ovens, jars, and signs reveal details of Roman daily business."),
    ("Carthaginian harbors", "ancient Carthage", "Protected commercial and naval harbors helped connect Carthage with Mediterranean trade."),
    ("Persian Royal Road", "the Achaemenid Empire", "Royal messengers used stations and fresh horses to carry information across great distances."),
    ("Qanat water tunnels", "ancient Persia", "Gently sloping underground tunnels moved groundwater to farms while limiting evaporation."),
    ("Nubian pyramids", "the kingdom of Kush", "Kushite rulers built steep-sided pyramids near royal centers along the Nile."),
    ("Aksumite stone stelae", "the kingdom of Aksum", "Tall carved stone monuments marked important tombs and displayed skilled engineering."),
    ("Swahili coast trade", "medieval East Africa", "Coastal towns exchanged gold, ivory, ceramics, cloth, and ideas across the Indian Ocean."),
    ("Great Zimbabwe", "southern Africa", "Builders fitted granite blocks without mortar to create impressive walls and enclosures."),
    ("Maya calendars", "the ancient Maya world", "Maya timekeepers tracked repeating ritual and solar cycles with several linked calendars."),
    ("Maya raised roads", "ancient Maya cities", "Elevated stone causeways connected buildings and settlements across wet lowlands."),
    ("Aztec chinampas", "the Valley of Mexico", "Farmers built productive raised plots in shallow lake areas using mud and plant material."),
    ("Inca suspension bridges", "the Andes", "Communities twisted plant fibers into strong cables and regularly rebuilt mountain bridges."),
    ("Inca quipu records", "the Inca Empire", "Officials tied colored cords and knots to organize numerical information."),
    ("Inca mountain roads", "the Andes", "A vast road network linked valleys, deserts, high passes, storehouses, and relay stations."),
    ("Polynesian wayfinding", "the Pacific Ocean", "Navigators read stars, swells, winds, clouds, and birds to find distant islands."),
    ("Viking longships", "the early medieval North Atlantic", "Flexible clinker-built hulls and shallow drafts let crews cross seas and enter rivers."),
    ("Medieval watermills", "medieval Europe", "Flowing water turned wheels that powered machinery for grinding grain and other work."),
    ("Gothic cathedrals", "medieval Europe", "Pointed arches, ribbed vaults, and flying buttresses supported tall walls and windows."),
    ("Castle spiral stairs", "a medieval stone castle", "Narrow turning staircases fit inside towers and connected defensible floors."),
    ("Illuminated manuscripts", "a medieval scriptorium", "Scribes and artists made books by hand with ink, pigments, and gold leaf."),
    ("Gutenberg's printing press", "Mainz around 1450", "Movable metal type, oil-based ink, and a press made repeated pages faster."),
    ("Leonardo's notebooks", "Renaissance Italy", "Leonardo filled pages with observations, diagrams, questions, and designs across many subjects."),
    ("Brunelleschi's dome", "Renaissance Florence", "Builders used interlocking brick patterns and clever lifting machines to span the cathedral."),
    ("Ottoman tile making", "the Ottoman Empire", "Artists arranged glazed tiles into durable geometric and floral designs."),
    ("Mughal gardens", "the Mughal Empire", "Designers used water channels, paths, shade, and symmetry to organize formal gardens."),
    ("Angkor's reservoirs", "the Khmer Empire", "Large reservoirs and channels helped manage water around fields and temple cities."),
    ("Borobudur", "ninth-century Java", "Builders shaped a hill-sized Buddhist monument with terraces, reliefs, and many stone stupas."),
    ("The magnetic compass", "medieval China", "Magnetized needles gave travelers a dependable direction even when landmarks were hidden."),
    ("Arab astrolabes", "the medieval Islamic world", "Astronomers used carefully marked instruments to measure star positions and solve practical problems."),
    ("Baghdad's paper makers", "the Abbasid era", "Paper workshops helped books, records, and scholarship circulate through growing cities."),
    ("Al-Jazari's water machines", "Mesopotamia around 1200", "Ingenious gears, floats, valves, and water power drove clocks and lifting devices."),
    ("Ibn al-Haytham's optics", "Cairo around 1000", "Experiments with light and dark rooms helped explain how vision works."),
    ("Zheng He's treasure voyages", "Ming dynasty China", "Large fleets crossed the Indian Ocean and visited ports from Southeast Asia to East Africa."),
    ("The caravel", "fifteenth-century Portugal", "A light sailing ship combined maneuverability with rigs suited to changing winds."),
    ("Mercator's map projection", "sixteenth-century Europe", "A new projection kept compass directions straight, helping sailors plot courses."),
    ("The marine chronometer", "eighteenth-century Britain", "An accurate sea clock helped navigators calculate longitude far from land."),
    ("The microscope", "seventeenth-century Europe", "Improved lenses revealed tiny structures that human eyes could not see alone."),
    ("The telescope", "early seventeenth-century Europe", "Lens makers and astronomers used tubes with lenses to magnify distant objects."),
    ("Newton's prism experiment", "seventeenth-century England", "Sunlight passing through glass separated into a spectrum of colors."),
    ("The steam engine", "eighteenth-century Britain", "Engineers improved machines that turned steam pressure into useful mechanical motion."),
    ("The spinning jenny", "eighteenth-century England", "One worker could spin several threads at once using a hand-powered machine."),
    ("The hot-air balloon", "France in 1783", "Heated air lifted a lightweight balloon and carried people above the ground."),
    ("The telegraph", "the nineteenth century", "Electrical signals sent coded messages through wires much faster than physical mail."),
    ("Morse code", "the telegraph era", "Short and long signal patterns represented letters for rapid communication."),
    ("The bicycle", "nineteenth-century Europe", "Pedals, chains, equal wheels, and pneumatic tires gradually created a practical ride."),
    ("Early photography", "the nineteenth century", "Light-sensitive materials captured images after carefully controlled exposures."),
    ("The phonograph", "the nineteenth-century United States", "A vibrating needle traced sound into a surface and played it back."),
    ("The incandescent lamp", "the late nineteenth century", "Inventors tested filaments and sealed bulbs to make practical electric lighting."),
    ("The first subway", "London in 1863", "Steam trains initially carried passengers through tunnels beneath crowded streets."),
    ("The Wright Flyer", "Kitty Hawk in 1903", "Careful experiments with wings and controls led to a powered, controlled airplane flight."),
    ("Ada Lovelace's algorithm", "Victorian Britain", "Her notes described ordered steps for a planned mechanical calculating engine."),
    ("Babbage's Difference Engine", "nineteenth-century Britain", "Precision gears were designed to calculate and print mathematical tables automatically."),
    ("George Washington Carver's laboratory", "the early twentieth-century United States", "Carver researched crops and taught practical methods that supported farmers."),
    ("Marie Curie's laboratory", "Paris around 1900", "Careful measurements helped reveal new radioactive elements and properties of matter."),
    ("Katherine Johnson's calculations", "the early space age", "Precise mathematics helped plan spacecraft paths and safe returns to Earth."),
    ("The first programmable computer", "the 1940s", "Early electronic machines used instructions and data to perform long calculations."),
    ("The first transatlantic cable", "the Atlantic Ocean in 1866", "A durable undersea cable allowed rapid messages between Europe and North America."),
    ("The Panama Canal locks", "Panama in the early twentieth century", "Lock chambers raise and lower ships across the high interior route."),
]

LENSES = [
    "clever design", "daily life", "hidden clues", "tools and materials",
    "messages", "maps and routes", "building methods", "science at work",
    "teamwork", "a child's view", "the workshop", "the first step",
    "the hardest problem", "a surprising detail", "trade and travel",
    "water and weather", "measurement", "patterns", "the discovery",
    "what changed next", "an everyday object", "the people behind it",
    "evidence archaeologists use", "its lasting legacy", "how it worked",
    "a mystery to solve", "the journey", "one important choice",
    "the landscape", "the sound of the past", "color and light",
    "a question for historians",
]


def _build_prompt(topic: tuple[str, str, str], lens: str) -> dict:
    subject, setting, fact = topic
    script = (
        f"What if you could investigate {subject} through {lens}? "
        f"Milo travels to {setting} to explore {subject}. {fact} "
        f"Watching closely, he studies {lens} and one detail people often miss. "
        "Which clue would you investigate first? Like and Subscribe for more."
    )
    while len(script.split()) < 48:
        script = script.replace(
            "Which clue",
            "The past leaves clues in ordinary places. Which clue",
            1,
        )
    if len(script.split()) > 75:
        script = script.replace("Watching closely, ", "")
    title = f"{subject}: {lens.title()}"
    if len(title) > 78:
        title = title[:78].rsplit(" ", 1)[0]
    fingerprint = hashlib.sha256(
        f"{KIDS_SEED_VERSION}|{subject}|{lens}".encode("utf-8")
    ).hexdigest()
    return {
        "fingerprint": fingerprint,
        "title": title,
        "script": script,
        "tags": ["historyforkids", "kidshistory", "educationalshorts"],
        "search_query": f"{subject} {setting} {lens} 3D animation",
    }


def _seed_version(channel_id: str) -> str:
    if channel_id == "channel_3":
        return KIDS_SEED_VERSION
    try:
        return SEED_VERSIONS[channel_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported prompt-reserve channel: {channel_id}") from exc


def _seed_prompts(channel_id: str) -> list[dict]:
    if channel_id != "channel_3":
        return build_channel_prompts(channel_id)
    return [_build_prompt(topic, lens) for topic in TOPICS for lens in LENSES]


def _migrate_prompt_columns(connection: sqlite3.Connection) -> None:
    existing = {
        row[1] for row in connection.execute("PRAGMA table_info(prompts)").fetchall()
    }
    additions = {
        "visual_queries_json": "TEXT NOT NULL DEFAULT '[]'",
        "hook_overlay": "TEXT NOT NULL DEFAULT ''",
        "hook_accent": "TEXT NOT NULL DEFAULT ''",
        "evidence_label": "TEXT NOT NULL DEFAULT ''",
        "source_url": "TEXT NOT NULL DEFAULT ''",
    }
    for name, declaration in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE prompts ADD COLUMN {name} {declaration}")


def initialize_prompt_database(
    path: str | Path, channel_id: str = "channel_3"
) -> int:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=DELETE;
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                channel_id TEXT NOT NULL DEFAULT 'channel_3',
                title TEXT NOT NULL,
                script TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                search_query TEXT NOT NULL,
                visual_queries_json TEXT NOT NULL DEFAULT '[]',
                hook_overlay TEXT NOT NULL DEFAULT '',
                hook_accent TEXT NOT NULL DEFAULT '',
                evidence_label TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'available'
                    CHECK(status IN ('available', 'reserved')),
                reserved_by TEXT,
                reserved_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_prompts_status_id
                ON prompts(status, id);
            """
        )
        _migrate_prompt_columns(connection)
        expected_version = _seed_version(channel_id)

        stored_channel = connection.execute(
            "SELECT value FROM metadata WHERE key='channel_id'"
        ).fetchone()
        if stored_channel is None:
            populated_channels = {
                row[0] for row in connection.execute(
                    "SELECT DISTINCT channel_id FROM prompts"
                ).fetchall()
            }
            if populated_channels and populated_channels != {channel_id}:
                raise RuntimeError(
                    f"{db_path} contains {sorted(populated_channels)}, not {channel_id}"
                )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES ('channel_id', ?)",
                (channel_id,),
            )
        elif stored_channel[0] != channel_id:
            raise RuntimeError(
                f"{db_path} belongs to {stored_channel[0]}, not {channel_id}"
            )

        seeded = connection.execute(
            "SELECT value FROM metadata WHERE key='seed_version'"
        ).fetchone()
        if seeded is None:
            prompts = _seed_prompts(channel_id)
            if channel_id in {"channel_1", "channel_2", "channel_3", "channel_4"} and len(prompts) < 2001:
                raise RuntimeError("Prompt reserve seed must contain more than 2,000 rows.")
            if not prompts:
                raise RuntimeError(f"Prompt reserve for {channel_id} is empty.")
            rows = [(
                prompt["fingerprint"],
                channel_id,
                prompt["title"],
                prompt["script"],
                json.dumps(prompt["tags"], separators=(",", ":")),
                prompt["search_query"],
                json.dumps(prompt.get("visual_queries", []), separators=(",", ":")),
                prompt.get("hook_overlay", ""),
                prompt.get("hook_accent", ""),
                prompt.get("evidence_label", ""),
                prompt.get("source_url", ""),
            ) for prompt in prompts]
            connection.executemany(
                """INSERT OR IGNORE INTO prompts
                   (fingerprint, channel_id, title, script, tags_json, search_query,
                    visual_queries_json, hook_overlay, hook_accent,
                    evidence_label, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES ('seed_version', ?)",
                (expected_version,),
            )
            connection.commit()
        elif seeded[0] != expected_version:
            raise RuntimeError(
                f"{db_path} uses seed {seeded[0]}, expected {expected_version}"
            )
        connection.commit()
        return int(connection.execute(
            "SELECT COUNT(*) FROM prompts WHERE channel_id=?", (channel_id,)
        ).fetchone()[0])
    finally:
        connection.close()


def reserve_prompt(
    path: str | Path, reservation_id: str, channel_id: str = "channel_3"
) -> dict | None:
    initialize_prompt_database(path, channel_id)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        stale_before = (
            dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(hours=STALE_RESERVATION_HOURS)
        ).isoformat()
        connection.execute(
            """UPDATE prompts SET status='available', reserved_by=NULL, reserved_at=NULL
               WHERE status='reserved' AND reserved_at < ?""",
            (stale_before,),
        )
        row = connection.execute(
            """SELECT * FROM prompts
               WHERE channel_id=? AND status='available' ORDER BY id LIMIT 1""",
            (channel_id,),
        ).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return None
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        connection.execute(
            """UPDATE prompts SET status='reserved', reserved_by=?, reserved_at=?
               WHERE id=? AND status='available'""",
            (reservation_id, now, row["id"]),
        )
        connection.execute("COMMIT")
        return {
            "title": row["title"],
            "script": row["script"],
            "tags": json.loads(row["tags_json"]),
            "search_query": row["search_query"],
            "visual_queries": json.loads(row["visual_queries_json"]),
            "hook_overlay": row["hook_overlay"],
            "hook_accent": row["hook_accent"],
            "evidence_label": row["evidence_label"],
            "source_url": row["source_url"],
            "_reserve_prompt_id": row["id"],
            "_prompt_source": "sqlite_reserve",
        }
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def consume_prompt(path: str | Path, prompt_id: int) -> None:
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.execute(
            "DELETE FROM prompts WHERE id=? AND status='reserved'", (prompt_id,)
        )
        connection.commit()
    finally:
        connection.close()


def available_prompt_count(path: str | Path, channel_id: str = "channel_3") -> int:
    initialize_prompt_database(path, channel_id)
    connection = sqlite3.connect(path, timeout=30)
    try:
        return int(connection.execute(
            "SELECT COUNT(*) FROM prompts WHERE channel_id=? AND status='available'",
            (channel_id,),
        ).fetchone()[0])
    finally:
        connection.close()


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "prompt_reserve.sqlite3")
    target_channel = sys.argv[2] if len(sys.argv) > 2 else "channel_3"
    total = initialize_prompt_database(target, target_channel)
    print(f"Initialized {target} for {target_channel} with {total} unique prompts")
