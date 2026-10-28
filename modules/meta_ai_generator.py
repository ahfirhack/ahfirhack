"""Automated Meta AI Create browser workflow for Channel 3.

This uses a Playwright browser session instead of a media API key. A person
signs into Meta once with ``bootstrap_meta_login`` and exports Playwright storage
state. GitHub-hosted Actions jobs restore that encrypted secret, inject the same
permanent Milo prompt into every request, render three video scenes, and download
every result.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

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
    META_SCENE_DURATION,
)


CHARACTER_BIBLE = """Milo is the permanent Epic History Kids guide: a curious
ten-year-old boy with warm medium-brown skin, large hazel eyes, soft rounded
features, and short dark-brown curls with one curl falling over his forehead.
He always wears the exact same teal explorer jacket with rolled sleeves, cream
shirt, golden-yellow scarf, navy trousers, coral-red sneakers, and a round
gold-and-turquoise time compass on his belt. He is kind, brave, expressive,
curious, and never carries a weapon. His face, age, proportions, hairstyle,
skin tone, clothing colors, compass, and shoes never change."""

STYLE_BIBLE = """Original premium 3D animated family-adventure look with
appealing rounded character design, expressive animation, cinematic lighting,
colorful historical environments, soft global illumination, polished
materials, gentle depth of field, and smooth feature-film-quality motion. The
look must be original and must not copy a studio, franchise, copyrighted
character, or existing film. Vertical 9:16 composition, kid-safe."""

CONTINUITY_BIBLE = """Keep Milo's identity, wardrobe, proportions, render
style, color palette, historical setting, camera direction, and screen position
identical. Continue naturally from the supplied prior final frame when one is
attached. No fades, dissolves, black frames, title cards, captions, readable
text, logos, dialogue, or lip-sync. Milo is a silent visual guide because one
locked narration voice is added later."""

NEGATIVE_PROMPT = """No character redesign, costume change, age change, face
change, hairstyle change, duplicate Milo, extra limbs or fingers, modern
objects, weapons, gore, frightening imagery, readable text, subtitles, logos,
black frames, blank frames, fades, dissolves, or camera resets."""


class MetaAIAutomationError(RuntimeError):
    """Meta AI could not complete an unattended browser operation."""


class MetaAILoginRequired(MetaAIAutomationError):
    """The persistent browser profile is not signed into Meta AI."""


class MetaAIVideoUnavailable(MetaAIAutomationError):
    """The signed-in Meta account is not eligible for video generation."""


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return clean[:48] or "episode"


def _save_manifest(manifest: dict, job_dir: Path) -> None:
    (job_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _split_narration(script: str, count: int) -> list[str]:
    """Split narration into balanced, chronological scene beats."""
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", script.strip())
        if sentence.strip()
    ]
    if not sentences:
        return [script.strip()] * count

    target = max(1, len(script.split()) // count)
    beats: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence_index, sentence in enumerate(sentences):
        sentence_words = len(sentence.split())
        remaining_beats = count - len(beats)
        remaining_sentences = len(sentences) - sentence_index
        if (
            current
            and current_words + sentence_words > target
            and remaining_beats > 1
            and remaining_sentences >= remaining_beats
        ):
            beats.append(" ".join(current))
            current = []
            current_words = 0
        current.append(sentence)
        current_words += sentence_words

    if current:
        beats.append(" ".join(current))
    while len(beats) < count:
        longest_index = max(range(len(beats)), key=lambda idx: len(beats[idx].split()))
        words = beats[longest_index].split()
        midpoint = max(1, len(words) // 2)
        beats[longest_index:longest_index + 1] = [
            " ".join(words[:midpoint]), " ".join(words[midpoint:])
        ]
    if len(beats) > count:
        beats[count - 1:] = [" ".join(beats[count - 1:])]
    return beats[:count]


def _scene_prompt(index: int, narration: str, topic: str) -> str:
    attachment = (
        "There is no reference attachment for this opening scene. Build Milo "
        "exactly from the permanent CHARACTER LOCK below."
        if index == 1
        else (
            "The attached image is the exact final frame of the previous scene. "
            "Begin with that same composition, Milo pose, lighting, and camera "
            "direction, then continue the action without a visual reset."
        )
    )
    ending = (
        "End with Milo in a clear moving pose while the camera travels "
        "forward-right, creating a clean continuation frame."
        if index < META_SCENE_COUNT
        else "Finish the historical discovery with a satisfying moving hero shot."
    )
    return " ".join(
        f"""Create a VIDEO, not a still image. Scene {index} of
        {META_SCENE_COUNT} for one continuous Epic History Kids episode about
        {topic}. Exactly {META_SCENE_DURATION} seconds, vertical 9:16, smooth
        natural motion, no embedded narration and no music. {attachment}
        CHARACTER LOCK: {CHARACTER_BIBLE} STYLE LOCK: {STYLE_BIBLE}
        CONTINUITY LOCK: {CONTINUITY_BIBLE} VISUAL STORY BEAT: {narration}
        ENDING HANDOFF: {ending} NEGATIVE REQUIREMENTS: {NEGATIVE_PROMPT}""".split()
    )


def _render_prompt_markdown(manifest: dict) -> str:
    lines = [
        f"# Meta AI automated render pack: {manifest['story']['title']}", "",
        "This pack is consumed automatically by the Playwright browser runner.",
        "Every scene receives the same permanent Milo character/style prompt.",
        "Scenes 2 and 3 also receive the prior video's final frame for visual",
        "continuity. All three requested outputs are videos.",
    ]
    for scene in manifest["scenes"]:
        lines.extend([
            "", f"## Scene {scene['index']} — `{scene['filename']}`", "", scene["prompt"]
        ])
    lines.append("")
    return "\n".join(lines)


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
        if manifest.get("status") in {"awaiting_meta_ai", "rendering", "ready"}:
            return manifest, manifest_path.parent
    return None


def create_job(channel: dict, story: dict) -> tuple[dict, Path]:
    fingerprint = hashlib.sha256(
        f"{story['title']}|{story['script']}".encode("utf-8")
    ).hexdigest()[:10]
    job_id = f"{_slug(story['title'])}-{fingerprint}"
    job_dir = Path(META_AI_JOBS_DIR) / channel["id"] / job_id
    for subdirectory in ("renders", "continuity", "debug"):
        (job_dir / subdirectory).mkdir(parents=True, exist_ok=True)

    beats = _split_narration(story["script"], META_SCENE_COUNT)
    scenes = []
    for offset, narration in enumerate(beats):
        index = offset + 1
        scenes.append({
            "index": index,
            "duration_seconds": META_SCENE_DURATION,
            "filename": f"scene_{index:02d}.mp4",
            "narration": narration,
            "prompt": _scene_prompt(index, narration, story["title"]),
        })

    manifest = {
        "job_id": job_id,
        "channel_id": channel["id"],
        "channel_name": channel["name"],
        "generator": "Meta AI Create through persistent Playwright Chromium",
        "status": "awaiting_meta_ai",
        "target_duration_seconds": META_SCENE_COUNT * META_SCENE_DURATION,
        "character_bible": CHARACTER_BIBLE,
        "style_bible": STYLE_BIBLE,
        "story": story,
        "scenes": scenes,
    }
    _save_manifest(manifest, job_dir)
    (job_dir / "PROMPTS.md").write_text(
        _render_prompt_markdown(manifest), encoding="utf-8"
    )
    (job_dir / "meta_prompts.txt").write_text(
        "\n\n".join(scene["prompt"] for scene in scenes) + "\n", encoding="utf-8"
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


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise MetaAIAutomationError(
            "Playwright is not installed. Run: pip install -r requirements.txt "
            "&& python -m playwright install chromium"
        ) from error
    return sync_playwright


def _launch_context(playwright, profile_dir: Path | None, *, headless: bool):
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
        state_path = _storage_state_path(required=True)
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


def _open_create_page(page) -> None:
    page.goto(META_AI_CREATE_URL, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(2_000)
    _dismiss_consent(page)


def _require_video_eligible_account(context, debug_path: Path) -> None:
    """Fail before rendering when Meta marks the account as Vibes-ineligible."""
    page = context.new_page()
    try:
        page.goto("https://meta.ai/vibes", wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(2_000)
        restriction = page.get_by_text(
            re.compile(
                r"teens? under 18 can['’]t use vibes|"
                r"must be 18 .*use vibes|"
                r"not eligible .*vibes|"
                r"meta ai isn['’]t available yet in your country|"
                r"vibes (?:isn['’]t|is not) available",
                re.I,
            )
        )
        if _visible_last(restriction) is not None:
            _take_debug_screenshot(page, debug_path)
            raise MetaAIVideoUnavailable(
                "Meta Vibes video generation is unavailable for this account "
                "or region. Export a session from a supported, eligible Meta "
                "account age 18 or older."
            )
    except MetaAIVideoUnavailable:
        raise
    except Exception:
        # The Create workflow remains the source of truth if the optional Vibes
        # eligibility page is unavailable or its layout changes.
        return
    finally:
        page.close()


def _find_prompt_editor(page, timeout_seconds: int = 30):
    selectors = [
        "textarea[placeholder*='Describe' i]", "textarea[placeholder*='Ask' i]",
        "textarea", "[contenteditable='true'][role='textbox']", "[contenteditable='true']",
    ]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for selector in selectors:
            candidate = _visible_last(page.locator(selector))
            if candidate is not None:
                return candidate
        page.wait_for_timeout(500)
    return None


def _require_logged_in_editor(page, debug_path: Path | None = None):
    editor = _find_prompt_editor(page)
    if editor is not None:
        return editor
    if debug_path is not None:
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(debug_path), full_page=True)
    raise MetaAILoginRequired(
        "Meta AI prompt editor was not available. Re-run `python main.py "
        "--meta-login`, update the META_AI_STORAGE_STATE_B64 GitHub secret, "
        "and then rerun the workflow."
    )


def _attach_image(page, image_path: Path) -> None:
    # Meta's landing page contains hidden file inputs for suggestion cards.
    # Always open the composer attachment dialog first so we do not upload the
    # continuation frame into an unrelated template such as "Victorian era".
    add_button = _visible_last(
        page.locator("[data-testid='composer-add-attachment-button']")
    )
    if add_button is None:
        add_button = _visible_last(
            page.get_by_role("button", name=re.compile(r"add attachment", re.I))
        )
    if add_button is None:
        raise MetaAIAutomationError("Meta AI composer attachment button was not found.")

    add_button.click()
    page.wait_for_timeout(750)
    inputs = page.locator("input[type='file']")
    file_input = inputs.last if inputs.count() else None
    if file_input is None:
        raise MetaAIAutomationError("Meta AI composer file input was not found.")
    file_input.set_input_files(str(image_path))
    page.wait_for_timeout(1_500)


def _media_sources(page, media_kind: str) -> list[str]:
    if media_kind == "video":
        script = """elements => elements.map(element => ({
            src: element.currentSrc || element.src || (element.querySelector('source') || {}).src || '',
            width: element.videoWidth || element.clientWidth || 0,
            height: element.videoHeight || element.clientHeight || 0,
            ready: element.readyState || 0
        })).filter(item => item.src && item.width >= 200 && item.height >= 200 && item.ready >= 2)
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
    try:
        return page.eval_on_selector_all(selector, script)
    except Exception:
        return []


def _submit_prompt(page, editor, prompt: str) -> None:
    editor.click()
    try:
        editor.fill(prompt)
    except Exception:
        editor.press("Control+A")
        editor.type(prompt, delay=1)

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


def _wait_for_media(page, media_kind: str, baseline: set[str]) -> str:
    deadline = time.monotonic() + META_AI_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        sources = _media_sources(page, media_kind)
        fresh = [source for source in sources if source not in baseline]
        if fresh:
            return fresh[-1]
        try:
            unavailable = page.get_by_text(
                re.compile(
                    rf"{re.escape(media_kind)} generation is not available|"
                    rf"cannot (?:create|generate) (?:a )?{re.escape(media_kind)}|"
                    rf"can't (?:create|generate) (?:a )?{re.escape(media_kind)}",
                    re.I,
                )
            )
            if _visible_last(unavailable) is not None:
                raise MetaAIVideoUnavailable(
                    f"Meta AI reports that {media_kind} generation is not "
                    "available for the signed-in account."
                )
            failure = page.get_by_text(
                re.compile(r"couldn't generate|unable to generate|try again|generation failed", re.I)
            )
            if _visible_last(failure) is not None:
                raise MetaAIAutomationError("Meta AI reported that media generation failed.")
        except MetaAIAutomationError:
            raise
        except Exception:
            pass
        page.wait_for_timeout(2_000)
    raise MetaAIAutomationError(
        f"Timed out after {META_AI_TIMEOUT_SECONDS}s waiting for Meta AI {media_kind}."
    )


def _download_through_page(page, source: str) -> bytes:
    data_url = page.evaluate(
        """async source => {
            const response = await fetch(source, {credentials: 'include'});
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const blob = await response.blob();
            return await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        }""", source,
    )
    return base64.b64decode(data_url.split(",", 1)[1])


def _download_with_visible_control(page, target: Path) -> bool:
    candidates = [
        page.get_by_role("button", name=re.compile(r"download|save", re.I)),
        page.get_by_role("link", name=re.compile(r"download|save", re.I)),
        page.locator("a[download]"),
    ]
    for locator in candidates:
        control = _visible_last(locator)
        if control is None:
            continue
        try:
            with page.expect_download(timeout=15_000) as download_info:
                control.click()
            download_info.value.save_as(str(target))
            return target.is_file() and target.stat().st_size >= 10_000
        except Exception:
            continue
    return False


def _save_media_source(context, page, source: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: bytes | None = None
    if source.startswith(("http://", "https://")):
        try:
            response = context.request.get(source, timeout=120_000)
            if response.ok:
                payload = response.body()
        except Exception:
            payload = None
    if payload is None:
        try:
            payload = _download_through_page(page, source)
        except Exception:
            payload = None
    if payload:
        target.write_bytes(payload)
    elif not _download_with_visible_control(page, target):
        raise MetaAIAutomationError("Meta media could not be downloaded from the page.")
    if not target.is_file() or target.stat().st_size < 10_000:
        raise MetaAIAutomationError("Downloaded Meta media file was empty or incomplete.")


def _take_debug_screenshot(page, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        pass


def _generate_media(context, prompt: str, target: Path, media_kind: str,
                    attachment: Path | None, debug_path: Path) -> None:
    page = context.new_page()
    try:
        _open_create_page(page)
        editor = _require_logged_in_editor(page, debug_path)
        if attachment is not None:
            _attach_image(page, attachment)
            editor = _require_logged_in_editor(page, debug_path)
        baseline = set(_media_sources(page, media_kind))
        _submit_prompt(page, editor, prompt)
        source = _wait_for_media(page, media_kind, baseline)
        _save_media_source(context, page, source, target)
    except Exception:
        _take_debug_screenshot(page, debug_path)
        raise
    finally:
        page.close()


def _extract_last_frame(video_path: Path, frame_path: Path) -> None:
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.15", "-i", str(video_path),
         "-frames:v", "1", "-q:v", "2", str(frame_path)],
        capture_output=True, text=True, timeout=120,
    )
    if completed.returncode != 0 or not frame_path.is_file():
        raise MetaAIAutomationError("Could not extract the Meta scene continuation frame.")


def collect_rendered_clips(manifest: dict, job_dir: Path) -> list[str]:
    renders_dir = job_dir / "renders"
    expected = [renders_dir / scene["filename"] for scene in manifest["scenes"]]
    missing = [path.name for path in expected if not path.is_file() or path.stat().st_size < 10_000]
    if missing:
        raise MetaAIAutomationError("Meta AI renders are incomplete: " + ", ".join(missing))
    manifest["status"] = "ready"
    _save_manifest(manifest, job_dir)
    return [str(path) for path in expected]


def ensure_rendered_clips(manifest: dict, job_dir: Path) -> list[str]:
    """Render every missing scene in Meta AI and return ordered clip paths."""
    renders_dir = job_dir / "renders"
    if all(
        (renders_dir / scene["filename"]).is_file()
        and (renders_dir / scene["filename"]).stat().st_size >= 10_000
        for scene in manifest["scenes"]
    ):
        return collect_rendered_clips(manifest, job_dir)

    profile_dir = _profile_dir()
    state_path = _storage_state_path(required=profile_dir is None)
    sync_playwright = _load_playwright()
    manifest["status"] = "rendering"
    _save_manifest(manifest, job_dir)

    with sync_playwright() as playwright:
        context, browser = _launch_context(playwright, profile_dir, headless=META_AI_HEADLESS)
        try:
            _require_video_eligible_account(
                context, job_dir / "debug" / "video-eligibility.png"
            )
            prior_frame: Path | None = None
            for scene in manifest["scenes"]:
                target = renders_dir / scene["filename"]
                frame_target = job_dir / "continuity" / f"scene_{scene['index']:02d}_last.jpg"
                if target.is_file() and target.stat().st_size >= 10_000:
                    if not frame_target.is_file():
                        _extract_last_frame(target, frame_target)
                    prior_frame = frame_target
                    continue

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
                        _generate_media(
                            context, scene["prompt"], target, "video", attachment,
                            job_dir / "debug" / f"scene_{scene['index']:02d}.png",
                        )
                        _extract_last_frame(target, frame_target)
                        prior_frame = frame_target
                        scene["rendered"] = True
                        _save_manifest(manifest, job_dir)
                        last_error = None
                        break
                    except MetaAILoginRequired:
                        raise
                    except MetaAIVideoUnavailable:
                        raise
                    except Exception as error:
                        last_error = error
                        print(f"[MetaAI] Scene {scene['index']} failed: {type(error).__name__}")
                        time.sleep(min(attempt * 10, 30))
                if last_error is not None:
                    raise MetaAIAutomationError(
                        f"Scene {scene['index']} failed after {META_AI_MAX_RETRIES} attempts: {last_error}"
                    ) from last_error
        finally:
            if state_path is not None:
                context.storage_state(path=str(state_path))
            context.close()
            if browser is not None:
                browser.close()
    return collect_rendered_clips(manifest, job_dir)


def bootstrap_meta_login() -> None:
    """Open the dedicated persistent profile for the one-time interactive login."""
    profile_dir = _profile_dir(required=True)
    sync_playwright = _load_playwright()
    with sync_playwright() as playwright:
        context, browser = _launch_context(playwright, profile_dir, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            _open_create_page(page)
            print("[MetaAI] Complete the Meta login in the opened browser window.")
            input("[MetaAI] When the Create prompt box is visible, press Enter here: ")
            _require_logged_in_editor(page)
            print(f"[MetaAI] Login verified. Persistent profile: {profile_dir}")
            state_path = Path(
                META_AI_STORAGE_STATE_FILE or "meta_ai_storage_state.json"
            ).expanduser().resolve()
            state_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(state_path))
            print(f"[MetaAI] Exported GitHub-hosted runner session: {state_path}")
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
