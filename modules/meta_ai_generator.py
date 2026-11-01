"""Meta Create / Meta Vibes studio: generate five original 10-second video scenes per channel.
Frames hand off via the actual rendered last frame (PNG) and visual checks.
Audio is generated inside Meta video; no other image, video or TTS provider.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .meta_clip_download import (MetaClipDownloadError, save_generated_clip, visible_download_control_count)

from config import (
    META_AI_BROWSER_CHANNEL,
    META_AI_CHROME_PROFILE_DIR,
    META_AI_CREATE_URL,
    META_AI_HEADLESS,
    META_AI_JOBS_DIR,
    META_AI_MAX_RETRIES,
    META_AI_STORAGE_STATE_FILE,
    META_AI_TIMEOUT_SECONDS,
    META_SCENE_COUNT,
    META_MAX_HANDOFF_DELTA,
    VIDEO_WIDTH, VIDEO_HEIGHT,
    META_SCENE_DURATION,
)


# Channel-specific look/character/voice locks repeat VERBATIM in every scene.
CHANNEL_LOCKS = {
    "channel_1": {
        "speaker": "the on-camera documentary presenter",
        "voice_id": "SCF-PRESENTER-01",
        "character": "An original adult documentary presenter with short dark hair, charcoal field jacket, neutral shirt, and the same face, build, wardrobe, posture and gestures across all five scenes. All people depicted in alleged crimes are unnamed illustrative actors, not claims of authentic footage or exact likenesses.",
        "style": "Photorealistic cinematic investigative documentary reenactment, grounded public-record details, realistic tech settings, high contrast, natural human motion, sharp professional cinematography. No defamatory inventions, fake evidence, or fabricated quotes.",
        "voice": "The presenter is the only speaker, always with the exact same adult American English voice, accent, pitch, timbre and recording ambience. All sound is synchronized IN-SCENE, never a detached voiceover. Other people are silent; their lips stay closed while the presenter speaks.",
        "role": "investigative documentary with one on-camera presenter",
    },
    "channel_2": {
        "speaker": "the original lead actor",
        "voice_id": "STORYFUSE-LEAD-01",
        "character": "The same original human lead actor from the episode's opening story, identical face, eye color, hairstyle, age, costume and accessories. Derive the identity and costume from the FULL STORY CONTEXT, lock that depiction across every scene. Other actors maintain distinct stable faces and costumes.",
        "style": "Photorealistic cinematic short film with natural human anatomy and physical acting, tense grounded suspense, expressive reaction shots, film lighting, realistic environments and a single continuous camera path. Never change location without a visible on-screen transition in the action.",
        "voice": "One lead actor speaks the exact scene line in their own stable realistic voice, synchronized on camera as scene dialogue; never a floating narrator. Any other actor is silent while that actor speaks: no mimicking, no simultaneous words or lip movement. Maintain individual voice identity for anyone who ever speaks.",
        "role": "cinematic live-action story with original real-looking actors",
    },
    "channel_3": {
        "speaker": "Milo",
        "voice_id": "MILO-01",
        "character": "Milo is a ten-year-old boy with warm medium-brown skin, large hazel eyes, soft rounded features, short dark-brown curls with one curl falling over his forehead. He wears the exact same teal explorer jacket with rolled sleeves, cream shirt, golden-yellow scarf, navy trousers, coral-red sneakers and round gold-and-turquoise time compass on his belt. Never change his design or outfit unless shown physically on camera.",
        "style": "Original premium polished 3D animated family history adventure with gentle depth of field, cinematic lighting, beautiful historical environments, soft materials and child-friendly motion. Do not copy another studio's characters or franchise.",
        "voice": "Milo is the only speaker, always with the same warm bright childlike American English voice and exact pitch, timbre, accent, pacing and recording quality; his lips naturally synchronize. All other characters remain silent and do not imitate his words. Native in-scene voice and ambience only.",
        "role": "kid-safe continuous 3D animated historical adventure",
    },
    "channel_4": {
        "speaker": "the on-camera lead actor",
        "voice_id": "STOIC-LEAD-01",
        "character": "The same original adult human lead (early thirties, short dark hair, medium skin tone, simple navy jacket and neutral shirt), with stable facial proportions, age, outfit and hairstyle in every scene. No anonymous strangers replace the lead.",
        "style": "Photorealistic grounded cinematic drama of modern life and practical Stoic decisions; soft natural light, tactile real spaces, subtle emotional acting, restrained tasteful camera movement, no disembodied text graphics.",
        "voice": "The lead actor is the only speaker, with the same calm measured adult American English voice in every scene; spoken words come from their on-screen mouth with natural synchronized lip movement, not external narration. Other characters remain completely silent with closed mouths while the lead talks.",
        "role": "cinematic human-centered practical philosophy story",
    },
}

CONTINUITY_LOCK = (
    "All five clips are consecutive pieces of ONE uninterrupted event. Maintain "
    "the identical faces, outfit, location, time of day, lighting, camera axis, "
    "camera motion, object positions, props and ambient sound. For scenes 2–5 the "
    "ATTACHED PNG IS THE ACTUAL FINAL FRAME OF THE PREVIOUS VIDEO, not a "
    "general inspiration. The exact same frame must be the first frame of "
    "this clip; continue moving from it immediately. No scene restart, "
    "jump cut, flash, black frame, blank frame, wipe, fade, transition, "
    "silent lead-in, silent tail, logo, captions, end screen or music montage. "
    "All spoken audio must be generated by Meta inside the video."
)

NEGATIVE_LOCK = (
    "Never swap identities or wardrobes; no second identical actor, wrong "
    "mouth movement, multiple voices saying the same line, detached voiceover, "
    "third-party footage, still-image slideshows, subtitle text, intertitles, "
    "closed captions, speech bubbles, title cards, watermarks, logos or any "
    "readable on-screen words. Keep every sign, screen, ticket and document "
    "outside the shot or strongly defocused so the model cannot invent "
    "gibberish writing. Never add a fade, black frame, frozen frame, silence, "
    "audio cut, scene restart or transition. Do not add a separate voiceover: "
    "the visible character must speak while Meta generates the video and its "
    "synchronized native audio together."
)

# The final master is 1440x2560, but scaling a 720p source does not create real
# 1080p detail. Enforce the user's minimum on the Meta export itself as well as
# the final assembly. Current Vibes accounts that top out at 720p therefore fail
# closed instead of publishing a misleading upscale.
MIN_META_SOURCE_WIDTH = 1080
MIN_META_SOURCE_HEIGHT = 1920
META_PROMPT_SCHEMA_VERSION = 3
MAX_META_ACCOUNT_SLOTS = 5

_EPISODE_PREFIXES = {
    "channel_1": "SCF",
    "channel_2": "STF",
    "channel_3": "EHK",
    "channel_4": "STR",
}

_ACCOUNT_FAILURE_LOCK = threading.Lock()
_UNAVAILABLE_ACCOUNT_STATES: set[str] = set()

class MetaAIAutomationError(RuntimeError):
    """Meta AI could not complete an unattended browser operation."""


class MetaAILoginRequired(MetaAIAutomationError):
    """The persistent browser profile is not signed into Meta AI."""


class MetaAIEditorUnavailable(MetaAIAutomationError):
    """No supported editor was detected on either allowed Meta surface."""


class MetaAIVideoUnavailable(MetaAIAutomationError):
    """The signed-in Meta account is not eligible for video generation."""


class MetaAIQualityUnavailable(MetaAIVideoUnavailable):
    """Meta video generation exists, but not at the required source quality."""


class MetaAITransientError(MetaAIAutomationError):
    """Meta reported a temporary service failure that should be retried."""


class MetaAIDownloadPending(MetaAIAutomationError):
    """A scene rendered on Meta, but export failed; do not generate it again."""


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return clean[:48] or "episode"


def _save_manifest(manifest: dict, job_dir: Path) -> None:
    (job_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _split_narration(script: str, count: int) -> list[str]:
    """Divide dialogue into semantic, chronological lines of about ten seconds.

    Prefer complete sentence boundaries. Older SQLite-reserve stories do not
    have a structured scene plan, so this keeps those stories usable without
    cutting a sentence merely to make every scene have the same word count.
    """
    # End-card calls-to-action disrupt continuous story, so omit them from
    # on-screen scene speech (the original upload story is unchanged).
    script = re.sub(r"\s*(?:Like and Subscribe for more|Subscribe for more|Like and subscribe)[.!?]*\s*$", "", script.strip(), flags=re.I)
    words = script.split()
    if len(words) < count * 5:
        raise MetaAIAutomationError(
            f"Story has only {len(words)} words; needs at least {count * 5} for {count} coherent scenes."
        )
    # Match the scene speech time budget; all five scenes must be plausible to
    # speak at natural pace rather than rushing two actors over one another.
    if len(words) > 125:
        raise MetaAIAutomationError(
            f"Story is {len(words)} words; cap is 125 words for a 50-second video."
        )
    sentences = [
        match.group(0).strip()
        for match in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", script)
        if match.group(0).strip()
    ]
    if len(sentences) >= count:
        beats = []
        cursor = 0
        for scene_index in range(count):
            groups_left = count - scene_index
            sentences_left = len(sentences) - cursor
            if groups_left == 1:
                take = sentences_left
            else:
                max_take = sentences_left - (groups_left - 1)
                remaining_words = sum(
                    len(sentence.split()) for sentence in sentences[cursor:]
                )
                target = remaining_words / groups_left
                take = 1
                current = len(sentences[cursor].split())
                while take < max_take:
                    next_total = current + len(sentences[cursor + take].split())
                    if abs(next_total - target) > abs(current - target):
                        break
                    current = next_total
                    take += 1
            beats.append(" ".join(sentences[cursor:cursor + take]))
            cursor += take
        if all(5 <= len(beat.split()) <= 25 for beat in beats):
            return beats

    # Last-resort compatibility for legacy stories with too few or unusually
    # long sentences. New AI stories are required to supply scene_plan instead.
    div, rem = divmod(len(words), count)
    beats, offset = [], 0
    for index in range(count):
        size = div + (1 if index < rem else 0)
        beats.append(" ".join(words[offset:offset + size]))
        offset += size
    return beats


def _story_scene_plan(story: dict, count: int) -> list[dict]:
    """Return five validated dialogue/action/end-frame rows.

    New text generators provide these rows directly. Existing prompt-reserve
    records are upgraded deterministically from their chronological script.
    """
    raw_plan = story.get("scene_plan")
    if isinstance(raw_plan, list) and len(raw_plan) == count:
        normalized = []
        for item in raw_plan:
            if not isinstance(item, dict):
                normalized = []
                break
            dialogue = " ".join(str(item.get("dialogue") or "").split())
            action = " ".join(str(item.get("action") or "").split())
            end_frame = " ".join(str(item.get("end_frame") or "").split())
            if not (5 <= len(dialogue.split()) <= 25 and action and end_frame):
                normalized = []
                break
            normalized.append({
                "dialogue": dialogue,
                "action": action,
                "end_frame": end_frame,
            })
        if len(normalized) == count:
            return normalized

    beats = _split_narration(story["script"], count)
    return [
        {
            "dialogue": beat,
            "action": (
                "Physically dramatize this chronological plot beat with the "
                "locked lead visible and acting naturally"
            ),
            "end_frame": (
                "Hold the lead, the active story object and the unchanged "
                "environment in a clear moving composition"
            ),
        }
        for beat in beats
    ]


def _episode_code(story: dict, channel: dict) -> str:
    fingerprint = hashlib.sha256(
        f"{story.get('title', '')}|{story.get('script', '')}".encode("utf-8")
    ).hexdigest()[:6].upper()
    return f"{_EPISODE_PREFIXES[channel['id']]}-{fingerprint}"


def _scene_prompt(index: int, narration: str, story: dict, channel: dict, *,
                  scene_plan: dict | None = None,
                  episode_code: str | None = None) -> str:
    """Build a timecoded production contract for one exact Meta scene."""
    locks = CHANNEL_LOCKS[channel["id"]]
    plan = scene_plan or {
        "action": "Show this chronological plot beat through visible physical action",
        "end_frame": "Keep the lead and active story object clearly framed",
    }
    episode_code = episode_code or _episode_code(story, channel)
    clip_code = f"{episode_code}-C{index}"
    prior_code = "none" if index == 1 else f"{episode_code}-C{index - 1}"
    next_code = "none" if index == META_SCENE_COUNT else f"{episode_code}-C{index + 1}"
    start = (index - 1) * META_SCENE_DURATION
    end = index * META_SCENE_DURATION
    frame_letter = chr(ord("A") + index - 1)
    reference = (
        "No prior image for scene 1. Treat the written character bible below "
        "as the source of truth and establish the reusable identity immediately."
        if index == 1 else
        "The attached PNG is the actual final frame of the previous Meta video. "
        "Reproduce it as frame zero before continuing the same movement."
    )
    final_action = (
        "Preserve active motion for the next clip; do not resolve the episode yet."
        if index < META_SCENE_COUNT else
        "Complete the final payoff in action, then stop without an outro or fade."
    )
    stitch = (
        f"prior source=none; establish the opening composition immediately. "
        f"next source={next_code} must begin on this clip's exact final image "
        "with unbroken ambience, score, camera direction and character motion."
        if index == 1 else
        (
            f"prior source={prior_code}; reproduce that source as this clip's "
            "identical first image. next source=none; preserve continuity through "
            "the final payoff without an outro."
            if index == META_SCENE_COUNT else
            f"prior source={prior_code}; next source={next_code}. Reproduce the "
            "prior source as this clip's identical first image, then make this "
            "clip's final image the next source with unbroken ambience, score, "
            "camera direction and character motion."
        )
    )
    location = " ".join(str(story.get("search_query") or story["title"]).split())
    return "\n".join((
        f"EPISODE {episode_code} — {story['title']} | SCENE {index}/{META_SCENE_COUNT} | "
        f"ABSOLUTE EPISODE TIME {start:02d}–{end:02d}s.",
        "META AI VIDEO GENERATION ONLY.",
        f"EXACT REFERENCE-IMAGE CHARACTER LOCK: {reference}",
        f"CHARACTER BIBLE / DO NOT REDESIGN: {locks['character']}",
        f"FIXED VOICE ID / DO NOT REGENERATE VOICE IDENTITY: "
        f"{locks['speaker']}={locks['voice_id']}. {locks['voice']}",
        f"PRODUCTION: Exactly {META_SCENE_DURATION}.00 seconds, vertical 9:16, "
        "true source resolution 1080x1920 minimum (1440x2560 preferred), stable "
        "24-or-30-fps motion, synchronized Meta-native dialogue, ambience and a "
        "subtle continuous original score beneath speech. No separate voiceover, "
        "external audio, captions, title card, intro, outro or transition.",
        f"VISUAL STYLE LOCK: {locks['style']}",
        f"LOCATION / STORY-STATE LOCK: {location}. Keep identical layout, prop state, "
        "scale, time of day, lighting, camera axis and audio bed across all five clips.",
        f"FULL EPISODE CONTEXT — FOR ACTION/IDENTITY ONLY, DO NOT SPEAK IN FULL: "
        f"{story['script']}",
        f"SPEAKING CAST FOR THIS CLIP: {locks['speaker']} [{locks['voice_id']}] says "
        f"EXACTLY: “{narration}” Do not improvise, paraphrase or add words. "
        "These words are audio only; never display them as text.",
        "10-SECOND STORYBOARD:",
        f"0.00–1.50s: Immediate first-frame hook/continuation from {prior_code}; "
        "show the identity-locked lead and active story object with no logo animation.",
        f"1.50–7.50s: Animate precisely: {plan['action']}.",
        "7.50–9.75s: Let the locked lead react naturally while the camera gently "
        "moves toward the unresolved focus; preserve physical and audio continuity.",
        f"9.75–10.00s: LOCK LAST FRAME {frame_letter}: {plan['end_frame']}. {final_action}",
        f"STITCH REQUIREMENT: {stitch}",
        f"CONTINUITY CONTRACT: {CONTINUITY_LOCK}",
        f"NEGATIVE REQUIREMENTS: {NEGATIVE_LOCK}",
        "RENDER NOTES: no readable text is necessary. Avoid text-bearing props. "
        "Save the ending frame as a PNG reference for the next clip.",
        f"CLIP ID: {clip_code}",
    ))


def _render_prompt_markdown(manifest: dict) -> str:
    lines = [
        f"# Meta AI original video: {manifest['story']['title']}", "",
        f"Channel: {manifest['channel_name']} — {META_SCENE_COUNT} × {META_SCENE_DURATION}s = 50s", "",
        "Source: only Meta AI video and embedded native scene audio.",
        "The final frame PNG of every clip is the first-frame reference for the next.",
        "All scenes are in a single continuous story with one stable speaking voice.",
    ]
    for scene in manifest["scenes"]:
        lines.extend(["", f"## Scene {scene['index']} — `{scene['filename']}`", "", scene["prompt"]])
    return "\n".join(lines) + "\n"


def find_active_job(channel_id: str) -> tuple[dict, Path] | None:
    channel_dir = Path(META_AI_JOBS_DIR) / channel_id
    if not channel_dir.exists():
        return None
    manifests = sorted(
        channel_dir.glob("*/manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (manifest.get("status") in {"awaiting_meta_ai", "rendering", "ready"}
                and len(manifest.get("scenes", [])) == META_SCENE_COUNT
                and manifest.get("render_backend") in (None, "meta_ai")
                and manifest.get("schema_version") == META_PROMPT_SCHEMA_VERSION):
            return manifest, manifest_path.parent
    return None


def create_job(channel: dict, story: dict) -> tuple[dict, Path]:
    fingerprint = hashlib.sha256(
        f"{story['title']}|{story['script']}".encode("utf-8")
    ).hexdigest()[:10]
    job_id = (
        f"{_slug(story['title'])}-v{META_PROMPT_SCHEMA_VERSION}-{fingerprint}"
    )
    job_dir = Path(META_AI_JOBS_DIR) / channel["id"] / job_id
    for subdirectory in ("renders", "continuity", "debug"):
        (job_dir / subdirectory).mkdir(parents=True, exist_ok=True)

    scene_plan = _story_scene_plan(story, META_SCENE_COUNT)
    episode_code = _episode_code(story, channel)
    scenes = []
    for offset, plan in enumerate(scene_plan):
        index = offset + 1
        narration = plan["dialogue"]
        scenes.append({
            "index": index,
            "duration_seconds": META_SCENE_DURATION,
            "filename": f"scene_{index:02d}.mp4",
            "narration": narration,
            "action": plan["action"],
            "end_frame": plan["end_frame"],
            "clip_id": f"{episode_code}-C{index}",
            "prompt": _scene_prompt(
                index, narration, story, channel,
                scene_plan=plan, episode_code=episode_code,
            ),
        })

    manifest = {
        "job_id": job_id,
        "channel_id": channel["id"],
        "channel_name": channel["name"],
        "generator": "Meta AI Create through Playwright, Meta-only",
        "schema_version": META_PROMPT_SCHEMA_VERSION,
        "episode_code": episode_code,
        "render_backend": "meta_ai",
        "status": "awaiting_meta_ai",
        "target_duration_seconds": META_SCENE_COUNT * META_SCENE_DURATION,
        "channel_locks": CHANNEL_LOCKS[channel["id"]],
        "native_audio": True,
        "story": story,
        "scenes": scenes,
    }
    _save_manifest(manifest, job_dir)
    (job_dir / "PROMPTS.md").write_text(
        _render_prompt_markdown(manifest), encoding="utf-8"
    )
    (job_dir / "meta_prompts.txt").write_text(
        "\n\f\n".join(scene["prompt"] for scene in scenes) + "\n", encoding="utf-8"
    )
    return manifest, job_dir


def _profile_dir(*, required: bool = False) -> Path | None:
    if not META_AI_CHROME_PROFILE_DIR.strip():
        if required:
            raise MetaAIAutomationError(
                "META_AI_CHROME_PROFILE_DIR is required for the one-time Meta "
                "login bootstrap. Set it to a local writable directory."
            )
        return None
    path = Path(META_AI_CHROME_PROFILE_DIR).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _storage_state_path(*, required: bool = False) -> Path | None:
    if not META_AI_STORAGE_STATE_FILE.strip():
        if required:
            raise MetaAIAutomationError(
                "META_AI_STORAGE_STATE_FILE is required on a GitHub-hosted "
                "runner. Restore it from the META_AI_STORAGE_STATE_B64 secret."
            )
        return None
    path = Path(META_AI_STORAGE_STATE_FILE).expanduser().resolve()
    if required and not path.is_file():
        raise MetaAIAutomationError(f"Meta AI storage-state file is missing: {path}")
    return path


def _storage_state_slots(*, required: bool = False) -> list[tuple[int, Path]]:
    """Return configured Meta sessions in primary-to-fallback order.

    META_AI_STORAGE_STATE_FILES is a comma-separated list whose positions are
    account slots 1–5. Missing optional files are skipped without renumbering.
    The original single-file variable remains the backwards-compatible primary.
    """
    configured = os.getenv("META_AI_STORAGE_STATE_FILES", "").strip()
    if configured:
        raw_paths = [part.strip() for part in configured.split(",")]
    else:
        primary = META_AI_STORAGE_STATE_FILE.strip()
        raw_paths = [primary]
        if primary:
            primary_path = Path(primary).expanduser()
            raw_paths.extend(
                str(primary_path.with_name(
                    f"{primary_path.stem}_{slot}{primary_path.suffix}"
                ))
                for slot in range(2, MAX_META_ACCOUNT_SLOTS + 1)
            )
    slots = []
    seen = set()
    for index, raw_path in enumerate(
        raw_paths[:MAX_META_ACCOUNT_SLOTS], start=1,
    ):
        if not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        slots.append((index, path))
    if required and not slots:
        raise MetaAIAutomationError(
            "No Meta AI account session file is available. Configure the "
            "primary META_AI_STORAGE_STATE_FILE or the ordered "
            "META_AI_STORAGE_STATE_FILES list."
        )
    return slots


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise MetaAIAutomationError(
            "Playwright is not installed. Run: pip install -r requirements.txt "
            "&& python -m playwright install chromium"
        ) from error
    return sync_playwright


def _launch_context(playwright, profile_dir: Path | None, *, headless: bool,
                    storage_state_path: Path | None = None):
    launch_kwargs = {
        "headless": headless,
        "args": ["--disable-dev-shm-usage"],
    }
    if META_AI_BROWSER_CHANNEL.strip():
        launch_kwargs["channel"] = META_AI_BROWSER_CHANNEL.strip()

    context_kwargs = {
        "accept_downloads": True,
        "viewport": {"width": 1440, "height": 1100},
    }
    if profile_dir is not None:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            **launch_kwargs,
            **context_kwargs,
        )
        browser = None
    else:
        state_path = storage_state_path or _storage_state_path(required=True)
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            storage_state=str(state_path),
            **context_kwargs,
        )
    context.set_default_timeout(30_000)
    return context, browser


def _visible_last(locator):
    for index in range(locator.count() - 1, -1, -1):
        candidate = locator.nth(index)
        try:
            if candidate.is_visible():
                return candidate
        except Exception:
            continue
    return None


def _visible_last_in_content(locator):
    """Ignore matching text in Meta's chat-history sidebar."""
    for index in range(locator.count() - 1, -1, -1):
        candidate = locator.nth(index)
        try:
            if not candidate.is_visible():
                continue
            bounds = candidate.bounding_box()
            if bounds is None or bounds.get("x", 0) >= 260:
                return candidate
        except Exception:
            continue
    return None


def _dismiss_consent(page) -> None:
    for label in (r"accept all", r"allow all", r"accept optional cookies"):
        try:
            button = _visible_last(page.get_by_role("button", name=re.compile(label, re.I)))
            if button is not None:
                button.click(timeout=2_000)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


def _is_meta_create_url(url: str) -> bool:
    """Recognize the Meta AI Create route (for router URL validation)."""
    try:
        parsed = urlsplit(url)
    except (ValueError, TypeError):
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"meta.ai", "www.meta.ai"}
        and (parsed.path == "/create" or parsed.path.startswith("/create/"))
    )


# Only Meta-owned video creation surfaces are allowed; no stock-video,
# image-animation service, public Vibes clips, or unrelated Meta chat surface.
_META_SURFACE_URLS = {
    "studio": "https://vibes.ai/",  # Meta's dedicated Vibes web studio (2026)
    "create": "https://meta.ai/create",
    "vibes": "https://meta.ai/vibes",  # legacy Meta AI Vibes deep-link
}
_META_EDITOR_SELECTORS = (
    "[data-testid*='composer' i] [contenteditable='true']",
    "[data-testid*='prompt' i] [contenteditable='true']",
    "[data-testid*='composer' i] textarea",
    "textarea[placeholder*='video' i]",
    "textarea[placeholder*='describe' i]",
    "textarea[placeholder*='imagine' i]",
    "textarea[placeholder*='ask' i]",
    "[role='textbox'][contenteditable='true']",
    "[contenteditable='plaintext-only']",
    "[contenteditable='true']",
    "textarea",
    "[role='textbox']",
)


def _meta_surface_order() -> list[str]:
    # Meta Create is the only production default.  Vibes Studio currently
    # exports short, silent 720p clips and must never become an automatic
    # fallback for channels that require native audio and true 1080p sources.
    # The other Meta-owned surfaces remain available only when a developer
    # explicitly opts into them for diagnostics with META_AI_SURFACES.
    raw = os.getenv("META_AI_SURFACES", "create")
    values = [part.strip().lower() for part in raw.split(",")]
    order = list(dict.fromkeys(value for value in values if value))
    unknown = [value for value in order if value not in _META_SURFACE_URLS]
    if unknown or not order:
        raise MetaAIAutomationError(
            "META_AI_SURFACES must be a comma-separated ordering of "
            "'studio', 'create', and/or 'vibes'."
        )
    return order


def _meta_hostname(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return parts.scheme == "https" and parts.hostname in {"meta.ai", "www.meta.ai", "vibes.ai", "www.vibes.ai"}
    except (ValueError, TypeError):
        return False


def _safe_page_location(page) -> dict:
    """Save only top-level route information, never auth query params/tokens."""
    try:
        url = urlsplit(page.url)
        top = (url.path or "/").split("/")[1]
        if top not in {"", "create", "vibes", "login", "signin", "sign-in", "auth", "accounts", "checkpoint", "project", "projects", "studio", "workspace"}:
            top = "other"
        return {"site": url.hostname or "unknown", "route": "/" + top}
    except Exception:
        return {"site": "unknown", "route": "unknown"}


def _looks_like_auth_gate(page) -> bool:
    try:
        parts = urlsplit(page.url)
        if (parts.hostname in {"facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com"}
                and any(token in parts.path.lower() for token in ("login", "checkpoint", "challenge"))):
            return True
        if parts.hostname in {"meta.ai", "www.meta.ai", "vibes.ai", "www.vibes.ai"} and any(
            token in parts.path.lower() for token in ("/login", "/auth", "/sign-in", "/signin", "/checkpoint")
        ):
            return True
        for label in (r"^(?:log in|login|sign in)$", r"^continue with (?:facebook|instagram|meta)$"):
            control = _visible_last(page.get_by_role("button", name=re.compile(label, re.I)))
            if control is not None:
                return True
    except Exception:
        pass
    return False


def _valid_prompt_editor(candidate) -> bool:
    try:
        if not candidate.is_visible() or not candidate.is_enabled():
            return False
        # Avoid filling unrelated login, search, navigation and history fields.
        for attribute in ("placeholder", "aria-label", "name", "type"):
            value = (candidate.get_attribute(attribute) or "").lower()
            if any(word in value for word in ("search", "password", "email", "username", "comment", "caption")):
                return False
        # If the UI has a visible sidebar search box, prefer main content.
        bounds = candidate.bounding_box()
        if bounds and bounds.get("width", 0) < 100:
            return False
        return True
    except Exception:
        return False


def _find_prompt_editor(page, timeout_seconds: int = 15):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        frames = [page]
        try:
            frames += [frame for frame in page.frames if frame != page.main_frame]
        except Exception:
            pass
        for frame in frames:
            for selector in _META_EDITOR_SELECTORS:
                try:
                    locator = frame.locator(selector)
                    for index in range(locator.count() - 1, -1, -1):
                        candidate = locator.nth(index)
                        if _valid_prompt_editor(candidate):
                            return candidate
                except Exception:
                    continue
        try:
            page.wait_for_timeout(500)
        except Exception:
            break
    return None


def _select_video_mode(page) -> bool:
    """Select an explicit Video tab/button when Meta presents one; never select Image."""
    patterns = (
        re.compile(r"^video$", re.I),
        re.compile(r"^(?:text|frame|image)[\s-]*to[\s-]*video$", re.I),
        re.compile(r"^create video$", re.I),
    )
    for role in ("tab", "radio", "button", "menuitem"):
        for pattern in patterns:
            try:
                control = _visible_last(page.get_by_role(role, name=pattern))
                if control is None:
                    continue
                aria_selected = (control.get_attribute("aria-selected") or "").lower()
                aria_pressed = (control.get_attribute("aria-pressed") or "").lower()
                if aria_selected == "true" or aria_pressed == "true":
                    return True
                control.click(timeout=3_000)
                page.wait_for_timeout(600)
                return True
            except Exception:
                continue
    return False


def _open_vibes_composer(page) -> bool:
    """The Vibes landing/feed can require opening a creation dialog first."""
    patterns = (
        re.compile(r"^(?:create a vibe|make a vibe|create video|generate video)$", re.I),
        re.compile(r"^create$", re.I),
    )
    for pattern in patterns:
        for role in ("button", "link"):
            try:
                entry = _visible_last(page.get_by_role(role, name=pattern))
                if entry is not None:
                    entry.click(timeout=4_000)
                    page.wait_for_timeout(900)
                    return True
            except Exception:
                continue
    return False


def _open_home_video_creator(page, surface: str) -> bool:
    """Safely recover from a Meta deep-link redirect to the homepage.

    Meta may route /create or /vibes back to /. A normal Meta chat composer is
    NOT sufficient. Only select controls explicitly labeled as VIDEO creation,
    or follow a Vibes navigation link and open its creation composer. This is
    still a best-effort UI fallback, never an eligibility bypass.
    """
    explicit_video = re.compile(
        r"^(?:create (?:a )?video|generate (?:a )?video|make (?:a )?video|"
        r"create (?:a )?vibe|make (?:a )?vibe|new video)$", re.I
    )
    for role in ("button", "link", "menuitem"):
        try:
            control = _visible_last(page.get_by_role(role, name=explicit_video))
            if control is not None:
                control.click(timeout=4_000)
                page.wait_for_timeout(1_000)
                return True
        except Exception:
            continue

    # For Vibes, the homepage often presents a navigation item before the
    # actual Create a Vibe button. Never mistake a generic homepage chat input
    # for a video composer.
    if surface == "vibes":
        for role in ("link", "button", "tab"):
            try:
                control = _visible_last(page.get_by_role(role, name=re.compile(r"^vibes$", re.I)))
                if control is None:
                    continue
                control.click(timeout=4_000)
                page.wait_for_timeout(900)
                if _open_vibes_composer(page):
                    return True
                # Navigation alone isn't proof that video generation is active.
                break
            except Exception:
                continue
    return False


def _open_studio_composer(page) -> bool:
    """Best-effort navigation within Meta's dedicated Vibes studio.

    The studio may open a landing page or a projects dashboard. Do not fill
    unrelated chat/search boxes or submit any prompt during this probe.
    """
    patterns = (
        re.compile(r"^(?:get started|start creating|start creation|open studio|try now)$", re.I),
        # The 2026 projects dashboard labels its primary entry point "Create
        # new". Keep the older project labels because Meta rolls UI variants
        # out independently by account and region.
        re.compile(
            r"^(?:create new|create new project|new project|create project|"
            r"start new project|new creation)$",
            re.I,
        ),
        re.compile(r"^(?:create video|generate video|text to video|frame to video)$", re.I),
    )
    clicked = False
    # Projects -> Create new -> creation type -> editor can require several
    # distinct clicks. Each control remains explicit and video-specific; this
    # never treats the projects search field as a prompt editor.
    for _ in range(5):
        # On a studio editor we need not click anything to prove it is ready.
        if _find_prompt_editor(page, timeout_seconds=0.3) is not None:
            return True
        step = False
        for pattern in patterns:
            for role in ("button", "link", "menuitem"):
                try:
                    control = _visible_last(page.get_by_role(role, name=pattern))
                    if control is not None and control.is_enabled():
                        control.click(timeout=4_000)
                        page.wait_for_timeout(750)
                        clicked = True
                        step = True
                        break
                except Exception:
                    continue
            if step:
                break
        if not step:
            break
        if _looks_like_auth_gate(page):
            raise MetaAILoginRequired(
                "Vibes Studio opened a sign-in screen. Sign into https://vibes.ai/ "
                "in your regular Chrome window, then re-import the session."
            )
    return clicked


def _video_eligibility_problem(page) -> str | None:
    """Return a fixed, privacy-safe reason for a visible Meta eligibility gate."""
    checks = (
        (
            re.compile(
                r"teens? under 18 (?:can(?:not|'t|’t)|can no longer) use vibes|"
                r"you(?:'|’)?ll be able to use vibes (?:again )?when you turn 18",
                re.I,
            ),
            "The signed-in Meta account is marked under 18 and cannot use Vibes.",
        ),
        (
            re.compile(
                r"vibes (?:is|are) not available for (?:this|your) account|"
                r"you are not eligible to use vibes",
                re.I,
            ),
            "Meta reports that Vibes is unavailable for the signed-in account.",
        ),
    )
    for pattern, reason in checks:
        try:
            if _visible_last_in_content(page.get_by_text(pattern)) is not None:
                return reason
        except Exception:
            continue
    return None


def _open_meta_surface(page, surface: str) -> None:
    if surface not in _META_SURFACE_URLS:
        raise MetaAIAutomationError("Unrecognized Meta AI creation surface")
    if surface == "create":
        url = META_AI_CREATE_URL
        if not _is_meta_create_url(url):
            raise MetaAIAutomationError("META_AI_CREATE_URL must point to https://meta.ai/create")
    else:
        url = _META_SURFACE_URLS[surface]
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(1_500)
    _dismiss_consent(page)
    # Never follow links to unrelated sites or silently treat normal chat as video.
    resolved = urlsplit(page.url)
    if resolved.hostname not in {
        "meta.ai", "www.meta.ai", "vibes.ai", "www.vibes.ai",
        "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    }:
        raise MetaAIAutomationError("Meta redirected to an unsupported website")
    if _looks_like_auth_gate(page):
        raise MetaAILoginRequired(
            "Meta opened a login/verification page rather than a video editor. "
            "Import your currently signed-in Chrome session, then re-run diagnostics."
        )
    eligibility_problem = _video_eligibility_problem(page)
    if eligibility_problem:
        raise MetaAIVideoUnavailable(eligibility_problem)

    if surface == "studio":
        if resolved.hostname not in {"vibes.ai", "www.vibes.ai"}:
            raise MetaAIEditorUnavailable(
                "Vibes Studio redirected away from vibes.ai. Sign in to "
                "https://vibes.ai/ manually in Chrome, then re-import its session."
            )
        _open_studio_composer(page)
        _select_video_mode(page)
        if _looks_like_auth_gate(page):
            raise MetaAILoginRequired(
                "Vibes Studio requires login. Visit https://vibes.ai/ in regular "
                "Chrome and import that session with --from-open-chrome."
            )
        if urlsplit(page.url).hostname not in {"vibes.ai", "www.vibes.ai"}:
            raise MetaAIEditorUnavailable("Vibes Studio exited the vibes.ai domain")
        return

    # The previous code rejected / immediately, before examining whether the
    # Meta homepage had moved video creation behind a prominent button.
    if resolved.hostname in {"meta.ai", "www.meta.ai"} and resolved.path in {"", "/"}:
        video_entry_opened = _open_home_video_creator(page, surface)
        video_mode_selected = _select_video_mode(page)
        if not (video_entry_opened or video_mode_selected):
            raise MetaAIEditorUnavailable(
                "Meta sent the Create/Vibes deep-link to its homepage. "
                "No explicit Video/Create-a-Vibe control was visible there. "
                "Check the page in your signed-in Chrome browser; a generic "
                "chat input cannot be used as a video editor."
            )
        # If video creation launched a modal on '/', it is now okay to probe
        # for its editor. Actual video generation remains guarded separately.
        return

    if resolved.hostname in {"meta.ai", "www.meta.ai"} and not any(
        resolved.path == route or resolved.path.startswith(route + "/")
        for route in ("/create", "/vibes", "/login", "/auth", "/sign-in")
    ):
        raise MetaAIEditorUnavailable("Meta opened a non-video route instead of Create/Vibes")
    if surface == "vibes" or resolved.path.startswith("/vibes"):
        _open_vibes_composer(page)
    _select_video_mode(page)


def _open_create_page(page) -> None:
    """Legacy login entry point, retained for backwards compatibility."""
    _open_meta_surface(page, "create")


def _save_surface_diagnostic(page, debug_path: Path, surface: str) -> dict:
    info = {"surface": surface, **_safe_page_location(page),
            "auth_gate_visible": _looks_like_auth_gate(page)}
    filename = debug_path.with_name(debug_path.stem + "_" + surface + ".png")
    _take_debug_screenshot(page, filename)
    info["screenshot"] = str(filename)
    return info


def _acquire_meta_editor(context, debug_path: Path):
    """Try Create then Vibes (or caller order), before claiming login failure.

    Never submits a prompt or downloads anything during discovery.
    """
    diagnostics = []
    for surface in _meta_surface_order():
        page = context.new_page()
        try:
            print(f"[MetaAI] Checking {surface.capitalize()} editor (no prompt submitted yet)")
            _open_meta_surface(page, surface)
            editor = _find_prompt_editor(page, timeout_seconds=12)
            if editor is not None:
                print(f"[MetaAI] {surface.capitalize()} editor found; using this Meta surface")
                return page, editor, surface
            diagnostics.append(_save_surface_diagnostic(page, debug_path, surface))
            print(f"[MetaAI] {surface.capitalize()}: editor unavailable; checking next Meta surface")
        except Exception as error:
            # Include auth_gate_visible even for navigation exceptions so a
            # genuine login gate is never mislabeled as an unknown UI failure.
            diagnostic = _save_surface_diagnostic(page, debug_path, surface)
            diagnostic["problem"] = type(error).__name__
            diagnostics.append(diagnostic)
        finally:
            # A successfully returned page is reused by the generator.
            if len(diagnostics) and diagnostics[-1].get("surface") == surface:
                try:
                    page.close()
                except Exception:
                    pass
    report_path = debug_path.with_name(debug_path.stem + "_editor_check.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"results": diagnostics}, indent=2), encoding="utf-8")
    reasons = ", ".join(f"{entry['surface']}={entry.get('site','unknown')}:{entry.get('route','/')}"
                       for entry in diagnostics)
    print(f"[MetaAI] Local editor diagnostics: {report_path}")
    if diagnostics and all(
        item.get("auth_gate_visible") is True or item.get("problem") == "MetaAILoginRequired"
        for item in diagnostics
    ):
        raise MetaAILoginRequired(
            f"Meta login is required on all checked creation surfaces ({reasons}). "
            "Sign in at https://vibes.ai/ using the exact Chrome profile "
            "you are importing, run python switch_meta_account.py "
            "--from-open-chrome, then run python diagnose_meta.py."
        )
    if any(item.get("problem") == "MetaAIVideoUnavailable" for item in diagnostics):
        raise MetaAIVideoUnavailable(
            f"The signed-in account is ineligible on at least one Meta video "
            f"surface and no usable editor was found on the others ({reasons}). "
            "Review the local eligibility screenshot; this account restriction "
            "cannot be bypassed by the automation."
        )
    raise MetaAIEditorUnavailable(
        f"No video prompt editor found on selected Meta surfaces ({reasons}). "
        "Your saved session may be signed out or the current Meta UI may "
        f"differ. Run python diagnose_meta.py and review {report_path.name} "
        "and local screenshots. Do not share your session JSON."
    )


def _require_logged_in_editor(page, debug_path: Path | None = None):
    """Legacy standalone editor probe for the one-time login flow."""
    editor = _find_prompt_editor(page, timeout_seconds=15)
    if editor is None:
        if debug_path is not None:
            _take_debug_screenshot(page, debug_path)
        error_cls = MetaAILoginRequired if _looks_like_auth_gate(page) else MetaAIAutomationError
        raise error_cls("Meta editor not detected on this page; use python diagnose_meta.py")
    return editor


def diagnose_meta_surfaces() -> None:
    """Non-generating auth/UI check; safe to run before spending generation quota."""
    state = _storage_state_path()
    if state is None or not state.is_file():
        print("[MetaAI Check] No saved session JSON. Import from signed-in Chrome first.")
    else:
        try:
            content = json.loads(state.read_text(encoding="utf-8"))
            cookies = content.get("cookies", [])
            active = [c for c in cookies if isinstance(c, dict) and
                      (c.get("expires", -1) in (None, -1, 0) or
                       float(c.get("expires", 0)) > time.time())]
            def count(domain):
                return sum(1 for c in active if str(c.get("domain", "")).lstrip(".").lower().endswith(domain))
            print(f"[MetaAI Check] Saved-session cookies (counts only): "
                  f"vibes.ai={count('vibes.ai')}, meta.ai={count('meta.ai')}, "
                  f"facebook.com={count('facebook.com')}")
            if count('vibes.ai') == 0:
                print("[MetaAI Check] No Vibes Studio cookie in the import. "
                      "Open https://vibes.ai/ in signed-in Chrome and re-import the session.")
        except (OSError, ValueError, TypeError, AttributeError):
            print("[MetaAI Check] Session unreadable; re-import using switch_meta_account.py")
    sync_playwright = _load_playwright()
    with sync_playwright() as playwright:
        profile_dir = _profile_dir()
        context, browser = _launch_context(playwright, profile_dir, headless=False)
        try:
            for surface in _meta_surface_order():
                page = context.new_page()
                try:
                    _open_meta_surface(page, surface)
                    editor = _find_prompt_editor(page, timeout_seconds=6)
                    diag = _save_surface_diagnostic(
                        page, Path("meta_ai_diagnostics") / "ui_probe.png", surface)
                    print(f"[MetaAI Check] {surface}: site={diag['site']} "
                          f"route={diag['route']} editor={'YES' if editor is not None else 'NO'} "
                          f"login_prompt={'YES' if diag['auth_gate_visible'] else 'NO'} "
                          f"screenshot={diag['screenshot']}")
                except Exception as error:
                    # Even rejected/redirected pages need a screenshot: the old
                    # script discarded precisely the most useful diagnostics.
                    diag = _save_surface_diagnostic(
                        page, Path("meta_ai_diagnostics") / "ui_probe.png", surface)
                    print(f"[MetaAI Check] {surface}: {type(error).__name__}; "
                          f"site={diag['site']} route={diag['route']} "
                          f"login_prompt={'YES' if diag['auth_gate_visible'] else 'NO'} "
                          f"screenshot={diag['screenshot']}")
                finally:
                    page.close()
        finally:
            context.close()
            if browser is not None:
                browser.close()


def _attach_image(page, image_path: Path) -> None:
    """Upload the previous Meta video's last frame to a Meta composer.

    This never downloads/generates an image from an outside website.
    If a Meta surface lacks reference-image upload, fail rather than fake continuity.
    """
    start_frame_controls = [
        page.get_by_role("button", name=re.compile(
            r"^(?:start frame|first frame|add start frame|upload start frame|"
            r"upload frame|add frame|add reference image|select start frame)$", re.I)),
        page.get_by_label(re.compile(
            r"^(?:start frame|first frame|add start frame|upload start frame|"
            r"upload frame|add reference image|select start frame)$", re.I)),
    ]

    def visible_control(locators):
        for locator in locators:
            candidate = _visible_last(locator)
            if candidate is not None:
                return candidate
        return None

    # Vibes Studio's projects editor initially collapses its two frame slots
    # behind a "Start, end frame" button. Expand it before looking for the
    # concrete "Add start frame" upload action.
    action = visible_control(start_frame_controls)
    if action is None:
        expanders = [
            page.get_by_role("button", name=re.compile(
                r"^start(?:\s*(?:,|&|and)\s*)end frame$", re.I)),
            page.get_by_title(re.compile(r"^start\s*(?:&|and)\s*end frame$", re.I)),
        ]
        expander = visible_control(expanders)
        if expander is not None:
            try:
                expander.click(timeout=3_000)
                page.wait_for_timeout(500)
            except Exception:
                pass
            action = visible_control(start_frame_controls)

    # Older Meta Create variants expose one generic attachment action instead
    # of a dedicated start-frame slot. Retain only image/reference-specific
    # fallbacks; never attach through an unrelated project/media picker.
    if action is None:
        controls = [
            page.locator("[data-testid='composer-add-attachment-button']"),
            page.get_by_role("button", name=re.compile(
                r"^(?:add attachment|attach|upload|upload image|add image|add media|reference image)$",
                re.I,
            )),
            page.get_by_label(re.compile(
                r"add attachment|upload image|reference image|start frame", re.I
            )),
        ]
        action = visible_control(controls)

    if action is None:
        raise MetaAIAutomationError(
            "This Meta AI video composer has no usable reference-image control. "
            "Cannot continue the story using the previous scene's final frame."
        )

    def set_revealed_file_input() -> bool:
        inputs = page.locator("input[type='file']")
        for index in range(inputs.count() - 1, -1, -1):
            candidate = inputs.nth(index)
            accept = (candidate.get_attribute("accept") or "").lower()
            if accept and not any(token in accept for token in ("image", ".png", "*/*")):
                continue
            try:
                candidate.set_input_files(str(image_path), timeout=5_000)
                page.wait_for_timeout(900)
                return True
            except Exception:
                continue
        return False

    def upload_through_studio_picker() -> bool:
        """Finish Vibes Studio's nested project-media picker workflow."""
        try:
            action.click(timeout=3_000)
            page.wait_for_timeout(350)
            picker = _visible_last(
                page.get_by_role("button", name=re.compile(r"^upload$", re.I))
            )
            if picker is None:
                return False
            picker.click(timeout=3_000)
            page.wait_for_timeout(350)
            if not set_revealed_file_input():
                return False

            # The nested upload dialog needs an explicit confirmation after its
            # file input is populated. Scope this to the last dialog so the
            # underlying media picker's Upload button is not clicked again.
            dialogs = page.get_by_role("dialog")
            if dialogs.count() < 1:
                return False
            confirm = dialogs.last.get_by_role(
                "button", name=re.compile(r"^upload$", re.I)
            )
            confirm.click(timeout=5_000)

            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    uploading = _visible_last(page.get_by_text(
                        re.compile(r"^uploading\s+\d+\s+images?$", re.I)
                    ))
                    upload_dialog = _visible_last(page.get_by_text(
                        re.compile(r"^upload images$", re.I)
                    ))
                    uploaded = _visible_last(page.get_by_text(
                        re.compile(r"^media uploaded$", re.I)
                    ))
                    if uploaded is not None and uploading is None and upload_dialog is None:
                        break
                except Exception:
                    pass
                page.wait_for_timeout(500)

            thumbnail = page.get_by_alt_text(image_path.name, exact=True).last
            thumbnail.wait_for(state="visible", timeout=30_000)
            thumbnail.click(timeout=5_000)
            add = page.get_by_role(
                "button", name=re.compile(r"^add to video$", re.I)
            ).last
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not add.is_enabled():
                page.wait_for_timeout(200)
            add.click(timeout=5_000)
            page.wait_for_timeout(900)
            return True
        except Exception:
            return False

    try:
        hostname = urlsplit(page.url).hostname
    except Exception:
        hostname = None
    if hostname in {"vibes.ai", "www.vibes.ai"}:
        if upload_through_studio_picker():
            return
        raise MetaAIAutomationError(
            "Vibes Studio could not attach the previous scene as its start frame."
        )

    # A real browser file chooser is preferred. Some Meta variants instead
    # reveal a hidden input, which is handled immediately afterward.
    try:
        with page.expect_file_chooser(timeout=4_000) as chooser_info:
            action.click(timeout=3_000)
        chooser_info.value.set_files(str(image_path))
        page.wait_for_timeout(900)
        return
    except Exception:
        if set_revealed_file_input():
            return
    raise MetaAIAutomationError("Meta AI reference-image upload input was not found.")


def _media_sources(page, media_kind: str) -> list[str]:
    if media_kind == "video":
        script = """elements => elements.map(element => ({
            src: element.currentSrc || element.src || (element.querySelector('source') || {}).src || '',
            width: element.videoWidth || element.clientWidth || 0,
            height: element.videoHeight || element.clientHeight || 0
        })).filter(item => item.src && item.width >= 200 && item.height >= 200)
        .map(item => item.src)"""
        selector = "video"
    else:
        script = """elements => elements.map(element => ({
            src: element.currentSrc || element.src || '',
            width: element.naturalWidth || 0,
            height: element.naturalHeight || 0
        })).filter(item => item.src && item.width >= 384 && item.height >= 384)
        .map(item => item.src)"""
        selector = "img"
    sources = []
    frames = [page]
    try:
        frames += [frame for frame in page.frames if frame != page.main_frame]
    except Exception:
        pass
    for frame in frames:
        try:
            sources.extend(frame.eval_on_selector_all(selector, script))
        except Exception:
            continue
    return list(dict.fromkeys(sources))


def _submit_prompt(page, editor, prompt: str) -> None:
    editor.click()
    try:
        editor.fill(prompt)
    except Exception:
        editor.press("Control+A")
        editor.type(prompt, delay=1)

    # On the dedicated Vibes Studio, the submit button is commonly Generate.
    # Do not click broad Generate buttons on meta.ai (which may be preset cards).
    if urlsplit(page.url).hostname in {"vibes.ai", "www.vibes.ai"}:
        for pattern in (re.compile(r"^(?:generate|generate video|create video)$", re.I),):
            try:
                action = _visible_last(page.get_by_role("button", name=pattern))
                if action is not None and action.is_enabled():
                    action.click(timeout=5_000)
                    return
            except Exception:
                continue
        raise MetaAIEditorUnavailable(
            "Vibes Studio prompt was found but a Generate Video control was not. "
            "See local diagnostic screenshot; do not submit to a chat field."
        )

    # Use the exact composer control. Broad labels such as "create" or
    # "generate" also match Meta's preset cards and can open a template modal
    # without ever submitting the typed prompt.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        button = _visible_last(page.locator("[data-testid='composer-send-button']"))
        if button is None:
            button = _visible_last(
                page.get_by_role("button", name=re.compile(r"^send$", re.I))
            )
        try:
            if button is not None and button.is_enabled():
                button.click()
                return
        except Exception:
            pass
        page.wait_for_timeout(500)
    editor.press("Enter")


def _select_highest_studio_quality(page) -> int | None:
    """Choose Vibes Studio's highest visible source-resolution option.

    Meta rolls out different maximums by account, so prefer the largest numeric
    option rather than hard-coding one label. A Studio editor without 1080p
    fails before generation; it must not silently spend a render at 480p.
    Non-Studio Meta surfaces are validated from the downloaded file instead.
    """
    try:
        hostname = urlsplit(page.url).hostname
    except Exception:
        hostname = None
    if hostname not in {"vibes.ai", "www.vibes.ai"}:
        return None

    advanced = _visible_last(
        page.get_by_title(re.compile(r"^advanced settings$", re.I))
    )
    if advanced is None:
        raise MetaAIEditorUnavailable(
            "Vibes Studio did not expose its video quality settings; refusing "
            "to generate a clip whose source resolution cannot be controlled."
        )
    advanced.click(timeout=5_000)
    page.wait_for_timeout(350)

    choices: list[tuple[int, object]] = []
    controls = page.get_by_role(
        "button", name=re.compile(r"^\s*\d{3,4}p\s*$", re.I)
    )
    for index in range(controls.count()):
        candidate = controls.nth(index)
        try:
            if not candidate.is_visible() or not candidate.is_enabled():
                continue
            label = (candidate.inner_text() or candidate.get_attribute("aria-label") or "").strip()
            match = re.fullmatch(r"(\d{3,4})p", label, re.I)
            if match:
                choices.append((int(match.group(1)), candidate))
        except Exception:
            continue
    if not choices:
        raise MetaAIEditorUnavailable(
            "Vibes Studio quality settings opened, but no numeric video "
            "resolution option was available."
        )
    resolution, control = max(choices, key=lambda item: item[0])
    if resolution < 1080:
        raise MetaAIQualityUnavailable(
            f"Vibes Studio's highest available source quality is {resolution}p; "
            "at least 1080p source quality is required. Upscaling a lower "
            "quality export is not accepted as genuine 1080p."
        )
    control.click(timeout=5_000)
    page.wait_for_timeout(250)
    # Studio's settings panel is not dismissed by Escape in every rollout.
    # Toggle the same explicit control closed so it cannot intercept the
    # subsequent prompt-editor click.
    try:
        closer = _visible_last(
            page.get_by_title(re.compile(r"^advanced settings$", re.I))
        )
        if closer is None:
            closer = _visible_last(
                page.get_by_role("button", name=re.compile(r"^advanced$", re.I))
            )
        if closer is None:
            raise RuntimeError("Advanced settings toggle disappeared")
        # The open settings card overlaps the toggle's hit-test area in the
        # current Studio DOM even though the toggle remains visible. This is a
        # normal click on that known control; force only bypasses the overlay's
        # incorrect pointer interception.
        closer.click(timeout=3_000, force=True)
        page.wait_for_timeout(250)
    except Exception:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
    print(f"[MetaAI] Source quality set to highest available option: {resolution}p")
    return resolution


def _generation_limit_keys(page, media_kind: str) -> set[str]:
    """Identify exact visible limit-result labels, including Meta's sidebar.

    Generic sidebar text is normally ignored because it can describe an old
    conversation. Meta can replace one sidebar entry with another while keeping
    the visible count unchanged, so compare the conversation link paths rather
    than only the number of labels.
    """
    try:
        matches = page.get_by_text(
            re.compile(
                rf"^{re.escape(media_kind)} generation limit reached$", re.I
            )
        )
        keys = set()
        for index in range(matches.count()):
            candidate = matches.nth(index)
            if not candidate.is_visible():
                continue
            route = candidate.evaluate("""
                element => {
                    const link = element.closest('a[href]');
                    if (!link) return null;
                    try { return new URL(link.href).pathname; }
                    catch (_) { return link.getAttribute('href'); }
                }
            """)
            keys.add(f"route:{route}" if route else f"visible:{index}")
        return keys
    except Exception:
        return set()


def _generation_limit_count(page, media_kind: str) -> int:
    """Compatibility/count helper used by diagnostics and tests."""
    return len(_generation_limit_keys(page, media_kind))


def _conversation_routes(page) -> list[str]:
    """Return Meta prompt routes in sidebar order without exposing titles."""
    routes = []
    try:
        links = page.locator("[data-testid='conversation-item'] a[href]")
        for index in range(links.count()):
            href = links.nth(index).get_attribute("href") or ""
            parsed = urlsplit(href)
            if parsed.hostname not in {None, "meta.ai", "www.meta.ai"}:
                continue
            route = parsed.path
            if route.startswith("/prompt/") and route not in routes:
                routes.append(route)
    except Exception:
        pass
    return routes


def _wait_for_media(page, media_kind: str, baseline: set[str],
                    baseline_downloads: int | None = None,
                    baseline_limits: set[str] | None = None,
                    baseline_conversations: set[str] | None = None) -> str:
    deadline = time.monotonic() + META_AI_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        sources = _media_sources(page, media_kind)
        fresh = [source for source in sources if source not in baseline]
        if fresh:
            return fresh[-1]
        # Some completed Vibes Studio projects expose only a Download button,
        # not a direct <video src>. The subsequent exporter uses the browser UI.
        if (baseline_downloads is not None and
                visible_download_control_count(page) > baseline_downloads):
            return ""
        if (baseline_limits is not None and
                _generation_limit_keys(page, media_kind) - baseline_limits):
            raise MetaAIVideoUnavailable(
                f"Meta AI's daily {media_kind} generation limit has been "
                "reached for the signed-in account; no scene was created."
            )
        # Meta's 2026 Create page sometimes submits the request into a new
        # sidebar conversation but returns the main view to /create. Follow
        # that newly created route so its generation result/error and media
        # elements become observable by this same wait loop.
        if baseline_conversations is not None:
            new_routes = [
                route for route in _conversation_routes(page)
                if route not in baseline_conversations
            ]
            if new_routes:
                route = new_routes[0]
                if urlsplit(page.url).path != route:
                    page.goto(
                        f"https://meta.ai{route}",
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                    page.wait_for_timeout(800)
                baseline_conversations = None
                continue
        try:
            unavailable = page.get_by_text(
                re.compile(
                    rf"{re.escape(media_kind)} generation is not available|"
                    rf"cannot (?:create|generate) (?:a )?{re.escape(media_kind)}|"
                    rf"can't (?:create|generate) (?:a )?{re.escape(media_kind)}",
                    re.I,
                )
            )
            if _visible_last_in_content(unavailable) is not None:
                raise MetaAIVideoUnavailable(
                    f"Meta AI reports that {media_kind} generation is not "
                    "available for the signed-in account."
                )
            quota = page.get_by_text(
                re.compile(
                    rf"{re.escape(media_kind)} generation limit|"
                    r"reached your limit|upgrade to do more|wait until tomorrow",
                    re.I,
                )
            )
            if _visible_last_in_content(quota) is not None:
                raise MetaAIVideoUnavailable(
                    f"Meta AI's daily {media_kind} generation limit has been "
                    "reached for the signed-in account; no scene was created."
                )
            transient = page.get_by_text(
                re.compile(
                    r"temporarily unavailable|temporary service|"
                    r"try again in a little while|try again later|"
                    r"something went wrong",
                    re.I,
                )
            )
            if _visible_last_in_content(transient) is not None:
                raise MetaAITransientError(
                    "Meta AI reported a temporary generation service failure."
                )
            failure = page.get_by_text(
                re.compile(r"couldn't generate|unable to generate|try again|generation failed", re.I)
            )
            if _visible_last_in_content(failure) is not None:
                raise MetaAIAutomationError("Meta AI reported that media generation failed.")
        except MetaAIAutomationError:
            raise
        except Exception:
            pass
        page.wait_for_timeout(2_000)
    raise MetaAIAutomationError(
        f"Meta AI Create/Vibes Studio did not return a new {media_kind} within "
        f"{META_AI_TIMEOUT_SECONDS}s. Confirm the chosen Meta page is in VIDEO "
        "generation mode for this account. No outside provider was used. "
        "See the saved scene debug screenshot."
    )


def _save_media_source(context, page, source: str, target: Path,
                       debug_path: Path | None = None,
                       fresh_sources=None) -> None:
    """Save the completed Meta clip via Download/Export, then media src fallback.

    File validity (10s / native audio / portrait) is checked before a target
    appears in the channel's renders directory. A rendered but failed download
    must NOT cause the generator to resubmit the same prompt automatically.
    """
    diagnostic_path = (
        debug_path.with_name(debug_path.stem + "_download.json")
        if debug_path is not None else None
    )
    try:
        save_generated_clip(
            context, page, source, target, _validate_meta_clip,
            diagnostic_path=diagnostic_path, source_supplier=fresh_sources,
        )
    except MetaClipDownloadError as error:
        # The video has ALREADY been generated on Meta. Keep a durable local
        # marker so the next 6-hour run cannot accidentally spend another
        # generation just to encounter the same failed export.
        if debug_path is not None:
            marker = debug_path.with_name(debug_path.stem + "_download_pending.json")
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({
                "status": "rendered_but_download_pending",
                "note": "Remove this marker only to authorize a fresh generation attempt.",
            }, indent=2), encoding="utf-8")
        raise MetaAIDownloadPending(str(error)) from error


def _take_debug_screenshot(page, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        pass


def _generate_media(context, prompt: str, target: Path, media_kind: str,
                    attachment: Path | None, debug_path: Path, *,
                    project_page=None, keep_project_open: bool = False):
    """Generate one scene, optionally reusing the same Meta project page.

    Keeping all five scenes in one Studio project gives Meta the strongest
    available character/style context. The prior final-frame upload remains the
    hard visual handoff; Studio clears that input after each generation.
    """
    page = project_page
    owns_page = page is None
    completed = False
    try:
        if media_kind != "video":
            raise MetaAIAutomationError("Only Meta AI VIDEO generation is allowed")
        if page is None:
            page, editor, surface = _acquire_meta_editor(context, debug_path)
        else:
            editor = _require_logged_in_editor(page, debug_path)
            host = urlsplit(page.url).hostname
            surface = "studio" if host in {"vibes.ai", "www.vibes.ai"} else "create"
        print(f"[MetaAI] Rendering on Meta {surface.capitalize()} (native video and audio only)")
        if attachment is not None:
            _attach_image(page, attachment)
            editor = _require_logged_in_editor(page, debug_path)
        _select_highest_studio_quality(page)
        # Changing resolution re-renders the Studio composer in some UI
        # versions; do not keep using the locator captured before that change.
        editor = _require_logged_in_editor(page, debug_path)
        baseline = set(_media_sources(page, media_kind))
        baseline_downloads = visible_download_control_count(page)
        baseline_limits = _generation_limit_keys(page, media_kind)
        baseline_conversations = set(_conversation_routes(page))
        _submit_prompt(page, editor, prompt)
        source = _wait_for_media(
            page, media_kind, baseline, baseline_downloads, baseline_limits,
            baseline_conversations,
        )
        print("[MetaAI] Video generated; saving completed clip from Meta browser")
        _save_media_source(context, page, source, target, debug_path,
                           lambda: [src for src in _media_sources(page, media_kind)
                                    if src not in baseline])
        print(f"[MetaAI] Clip saved and validated: {target}")
        completed = True
        return page if keep_project_open else None
    except Exception:
        if page is not None:
            _take_debug_screenshot(page, debug_path)
        raise
    finally:
        if page is not None and owns_page and (not keep_project_open or not completed):
            page.close()


def _probe_video(path: Path) -> dict:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=index,codec_type,width,height,duration", "-of", "json", str(path)
    ], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise MetaAIAutomationError("FFprobe cannot read the generated Meta video")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MetaAIAutomationError("Invalid metadata in generated Meta video") from error


def _validate_meta_clip(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 10_000:
        raise MetaAIAutomationError(f"Meta did not return a real video: {path.name}")
    info = _probe_video(path)
    streams = info.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise MetaAIAutomationError(f"{path.name} missing video or Meta-native audio; no fallback")
    seconds = float(info.get("format", {}).get("duration") or 0)
    audio_seconds = float(audio.get("duration") or seconds)
    if not 9.9 <= seconds <= 10.6 or audio_seconds < 9.8:
        raise MetaAIAutomationError(
            f"{path.name} video={seconds:.2f}s, audio={audio_seconds:.2f}s; "
            "required is one complete 10s native-audio Meta video"
        )
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if not width or not height or (width / height) > 0.75:
        raise MetaAIAutomationError(f"{path.name} must be 9:16-ish portrait, got {width}x{height}")
    if width < MIN_META_SOURCE_WIDTH or height < MIN_META_SOURCE_HEIGHT:
        raise MetaAIAutomationError(
            f"{path.name} source resolution {width}x{height} is below the "
            f"required {MIN_META_SOURCE_WIDTH}x{MIN_META_SOURCE_HEIGHT} Meta source quality"
        )


def _normalized_frames_filter() -> str:
    # The precise same visual normalization is used for handoff and assembly.
    return (f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},setsar=1,fps=30,trim=duration=10,"
            "setpts=PTS-STARTPTS")


def _extract_last_frame(video_path: Path, frame_path: Path) -> None:
    """Save the ACTUAL last frame of the first 10 seconds, not -0.15s."""
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
        "-map", "0:v:0", "-an", "-vf", _normalized_frames_filter(),
        "-c:v", "png", "-update", "1", str(frame_path)
    ], capture_output=True, text=True, timeout=180)
    if completed.returncode != 0 or not frame_path.is_file() or frame_path.stat().st_size < 1000:
        raise MetaAIAutomationError("Cannot extract the exact Meta scene final frame")


def _check_scene_handoff(previous_last: Path, new_scene: Path) -> None:
    """Detect a major scene reset before a video could be published.

    An actual image reference is mandatory AND the first frame must roughly
    resemble it. Pixel-exact first frame is enforced later by FFmpeg assembly.
    This guard rejects obvious resets; it is NOT a semantic continuity proof.
    """
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError as error:
        raise MetaAIAutomationError("Pillow required for scene handoff QA") from error
    first = new_scene.parent.parent / "continuity" / f"{new_scene.stem}_first.png"
    first.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(new_scene),
        "-map", "0:v:0", "-an", "-vf", _normalized_frames_filter(),
        "-frames:v", "1", str(first)
    ], capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not first.is_file():
        raise MetaAIAutomationError("Cannot inspect the next scene's first frame")
    with Image.open(previous_last) as previous_img, Image.open(first) as first_img:
        thumb_size = (180, 320)
        a = previous_img.convert("RGB").resize(thumb_size)
        b = first_img.convert("RGB").resize(thumb_size)
        delta = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / (3 * 255)
    if delta > META_MAX_HANDOFF_DELTA:
        raise MetaAIAutomationError(
            f"Scene visibly reset instead of using previous final frame "
            f"(mean pixel difference {delta:.3f} > {META_MAX_HANDOFF_DELTA:.3f}); regenerate"
        )


def collect_rendered_clips(manifest: dict, job_dir: Path) -> list[str]:
    if len(manifest.get("scenes", [])) != META_SCENE_COUNT:
        raise MetaAIAutomationError("Expected exactly five 10-second scenes")
    expected = [job_dir / "renders" / scene["filename"] for scene in manifest["scenes"]]
    for clip in expected:
        _validate_meta_clip(clip)
    manifest["status"] = "ready"
    manifest["render_backend"] = "meta_ai"
    _save_manifest(manifest, job_dir)
    return [str(path) for path in expected]


def _ensure_meta_rendered_clips(
    manifest: dict, job_dir: Path, *, isolated_browser: bool = False,
    storage_state_path: Path | None = None, account_slot: int = 1,
) -> list[str]:
    """Render in one isolated Playwright browser per concurrent channel.

    The shared Meta login is an INPUT snapshot. A parallel worker never
    overwrites that snapshot or locks a normal/persistent Chrome profile.
    """
    renders_dir = job_dir / "renders"
    if len(manifest.get("scenes", [])) != META_SCENE_COUNT:
        raise MetaAIAutomationError("This is not a new five-scene Meta AI job")
    all_cached = all(
        (renders_dir / scene["filename"]).is_file()
        and (renders_dir / scene["filename"]).stat().st_size >= 10_000
        for scene in manifest["scenes"]
    )
    # A resumed job must pass the *same* native-audio and continuity checks;
    # do not bypass QA simply because five files happen to exist.
    if all_cached:
        prior_frame = None
        for scene in manifest["scenes"]:
            cached = renders_dir / scene["filename"]
            frame = job_dir / "continuity" / f"scene_{scene['index']:02d}_last.png"
            try:
                _validate_meta_clip(cached)
                if prior_frame is not None:
                    _check_scene_handoff(prior_frame, cached)
                _extract_last_frame(cached, frame)
                prior_frame = frame
            except MetaAIAutomationError as error:
                print(f"[MetaAI] Invalid cached scene {scene['index']}: {error}; retrying from scene")
                for after in manifest["scenes"][scene["index"] - 1:]:
                    (renders_dir / after["filename"]).unlink(missing_ok=True)
                break
        else:
            return collect_rendered_clips(manifest, job_dir)

    # Parallel Chrome windows must NOT share a persistent user_data_dir.
    # Import a saved, signed-in session into a separate, private browser context
    # for each channel instead. This leaves normal Chrome untouched.
    profile_dir = None if isolated_browser else _profile_dir()
    state_path = (
        storage_state_path or _storage_state_path(required=True)
        if profile_dir is None else None
    )
    sync_playwright = _load_playwright()
    manifest["status"] = "rendering"
    _save_manifest(manifest, job_dir)

    with sync_playwright() as playwright:
        context, browser = _launch_context(
            playwright, profile_dir, headless=META_AI_HEADLESS,
            storage_state_path=state_path,
        )
        successful_render = False
        project_page = None
        try:
            # Meta AI Create and Vibes are the ONLY allowed generators.
            prior_frame: Path | None = None
            for scene in manifest["scenes"]:
                target = renders_dir / scene["filename"]
                frame_target = job_dir / "continuity" / f"scene_{scene['index']:02d}_last.png"
                pending_export = job_dir / "debug" / f"scene_{scene['index']:02d}_download_pending.json"
                if target.is_file() and target.stat().st_size >= 10_000:
                    try:
                        _validate_meta_clip(target)
                        if prior_frame is not None:
                            _check_scene_handoff(prior_frame, target)
                        _extract_last_frame(target, frame_target)
                        prior_frame = frame_target
                        pending_export.unlink(missing_ok=True)
                        continue
                    except MetaAIAutomationError as invalid:
                        print(f"[MetaAI] Discarding invalid cached {target.name}: {invalid}")
                        target.unlink(missing_ok=True)
                        frame_target.unlink(missing_ok=True)
                        # Later cached scenes were built from this invalid frame.
                        for downstream in manifest["scenes"][scene["index"]:]:
                            (renders_dir / downstream["filename"]).unlink(missing_ok=True)

                if pending_export.exists():
                    raise MetaAIDownloadPending(
                        f"Scene {scene['index']} was already generated on Meta but the "
                        f"download failed. Check the job's debug screenshots and "
                        f"{pending_export.name}. Add a valid downloaded clip to the "
                        "renders folder, or remove the marker to authorize regeneration."
                    )

                # Scene 1 is generated directly from the permanent prompt.
                # Later scenes receive only the preceding video's final frame.
                attachment = prior_frame
                last_error: Exception | None = None
                for attempt in range(1, META_AI_MAX_RETRIES + 1):
                    try:
                        print(
                            f"[MetaAI] Rendering scene {scene['index']}/{len(manifest['scenes'])} "
                            f"(attempt {attempt}/{META_AI_MAX_RETRIES})"
                        )
                        project_page = _generate_media(
                            context, scene["prompt"], target, "video", attachment,
                            job_dir / "debug" / f"scene_{scene['index']:02d}.png",
                            project_page=project_page, keep_project_open=True,
                        )
                        _validate_meta_clip(target)
                        if prior_frame is not None:
                            _check_scene_handoff(prior_frame, target)
                        _extract_last_frame(target, frame_target)
                        prior_frame = frame_target
                        successful_render = True
                        scene["rendered"] = True
                        scene["meta_account_slot"] = account_slot
                        pending_export.unlink(missing_ok=True)
                        _save_manifest(manifest, job_dir)
                        last_error = None
                        break
                    except (MetaAILoginRequired, MetaAIEditorUnavailable, MetaAIDownloadPending):
                        # No editor/login is not a transient generation failure.
                        # Do not spend four retries and do not overwrite imported login.
                        target.unlink(missing_ok=True)
                        raise
                    except MetaAIVideoUnavailable:
                        target.unlink(missing_ok=True)
                        raise
                    except MetaAITransientError as error:
                        target.unlink(missing_ok=True)
                        last_error = error
                        if project_page is not None:
                            try:
                                project_page.close()
                            except Exception:
                                pass
                            project_page = None
                        if attempt < META_AI_MAX_RETRIES:
                            delay = min(attempt * 60, 180)
                            print(
                                f"[MetaAI] Scene {scene['index']} hit a temporary "
                                f"Meta service failure; retrying in {delay}s"
                            )
                            time.sleep(delay)
                    except Exception as error:
                        target.unlink(missing_ok=True)
                        last_error = error
                        if project_page is not None:
                            try:
                                project_page.close()
                            except Exception:
                                pass
                            project_page = None
                        print(f"[MetaAI] Scene {scene['index']} failed: {type(error).__name__}")
                        if attempt < META_AI_MAX_RETRIES:
                            time.sleep(min(attempt * 10, 30))
                if last_error is not None:
                    raise MetaAIAutomationError(
                        f"Scene {scene['index']} failed after {META_AI_MAX_RETRIES} attempts: {last_error}"
                    ) from last_error
        finally:
            # Preserve the imported Chrome session verbatim on a failed editor
            # check. On real success, refresh it atomically including IndexedDB.
            # A parallel channel must never overwrite the single shared
            # storage-state file: other workers may still be reading it.
            if state_path is not None and successful_render and not isolated_browser:
                pending = state_path.with_name(state_path.name + ".pending")
                try:
                    try:
                        context.storage_state(path=str(pending), indexed_db=True)
                    except TypeError:
                        context.storage_state(path=str(pending))
                    pending.replace(state_path)
                finally:
                    pending.unlink(missing_ok=True)
            if project_page is not None:
                try:
                    project_page.close()
                except Exception:
                    pass
            context.close()
            if browser is not None:
                browser.close()
    return collect_rendered_clips(manifest, job_dir)


def ensure_rendered_clips(
    manifest: dict, job_dir: Path, *, isolated_browser: bool = False,
) -> list[str]:
    """Render through up to five isolated Meta sessions in ordered failover."""
    if manifest.get("render_backend") not in (None, "meta_ai"):
        raise MetaAIAutomationError("Non-Meta render backend is prohibited")
    # A deliberately configured persistent local profile is a single-account
    # interactive mode. Scheduled/parallel operation always uses state files.
    if not isolated_browser and _profile_dir() is not None:
        return _ensure_meta_rendered_clips(
            manifest, job_dir, isolated_browser=False,
        )

    slots = _storage_state_slots(required=True)
    errors = []
    for position, (slot, state_path) in enumerate(slots):
        state_key = str(state_path)
        with _ACCOUNT_FAILURE_LOCK:
            unavailable = state_key in _UNAVAILABLE_ACCOUNT_STATES
        if unavailable and position < len(slots) - 1:
            print(f"[MetaAI] Skipping unavailable account {slot}; trying next account")
            continue
        print(f"[MetaAI] Using Meta account {slot}/{max(number for number, _ in slots)}")
        try:
            return _ensure_meta_rendered_clips(
                manifest, job_dir, isolated_browser=isolated_browser,
                storage_state_path=state_path, account_slot=slot,
            )
        except MetaAIDownloadPending:
            # The video already exists remotely. Another account would generate
            # a duplicate and spend quota, so manual recovery remains mandatory.
            raise
        except MetaAIAutomationError as error:
            errors.append(f"account {slot}={type(error).__name__}")
            if isinstance(error, (
                MetaAILoginRequired,
                MetaAIEditorUnavailable,
                MetaAIVideoUnavailable,
            )):
                with _ACCOUNT_FAILURE_LOCK:
                    _UNAVAILABLE_ACCOUNT_STATES.add(state_key)
            if position < len(slots) - 1:
                print(
                    f"[MetaAI] Account {slot} failed with {type(error).__name__}; "
                    "continuing with the next configured account"
                )
                continue
            print("[MetaAI] All configured Meta accounts failed (" +
                  ", ".join(errors) + ")")
            raise
    raise MetaAIAutomationError(
        "All configured Meta account sessions are currently unavailable."
    )


def bootstrap_meta_login() -> None:
    """Interactive bootstrap; accept either a working Create or Vibes editor."""
    profile_dir = _profile_dir(required=True)
    sync_playwright = _load_playwright()
    with sync_playwright() as playwright:
        context, browser = _launch_context(playwright, profile_dir, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(_META_SURFACE_URLS[_meta_surface_order()[0]], wait_until="domcontentloaded")
            print("[MetaAI] Complete your login in the browser window.")
            for attempt in range(1, 4):
                choice = input(
                    "[MetaAI] When Meta Create or Vibes Studio video editor works, "
                    "press Enter to verify (q to cancel): "
                ).strip().lower()
                if choice in {"q", "quit", "cancel"}:
                    raise MetaAILoginRequired("Login cancelled; existing session unchanged.")
                try:
                    verification_page, editor, source = _acquire_meta_editor(
                        context, profile_dir.parent / "meta_ai_debug_login.png")
                    verification_page.close()
                    break
                except MetaAIAutomationError as error:
                    print(f"[MetaAI] Verification {attempt}/3: {error}")
                    if attempt == 3:
                        raise
            state_path = Path(
                META_AI_STORAGE_STATE_FILE or "meta_ai_storage_state.json"
            ).expanduser().resolve()
            state_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                context.storage_state(path=str(state_path), indexed_db=True)
            except TypeError:
                context.storage_state(path=str(state_path))
            print(f"[MetaAI] {source.capitalize()} editor verified; session saved locally.")
        finally:
            context.close()
            if browser is not None:
                browser.close()


def mark_job_complete(job_dir: Path, video_id: str) -> None:
    manifest_path = job_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "uploaded"
    manifest["youtube_video_id"] = video_id
    _save_manifest(manifest, job_dir)
