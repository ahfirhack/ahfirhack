"""Automated Meta AI Create browser workflow for Channel 3.

This uses a dedicated persistent Chromium profile instead of a media API key.
A person signs into Meta once with ``bootstrap_meta_login``. Scheduled
self-hosted GitHub Actions runs then reuse that profile, create a permanent Milo
reference image when needed, render three scenes, and download every result.
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
    META_AI_CHARACTER_IMAGE,
    META_AI_CHROME_PROFILE_DIR,
    META_AI_CREATE_URL,
    META_AI_HEADLESS,
    META_AI_JOBS_DIR,
    META_AI_MAX_RETRIES,
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
        "The attached image is the permanent Milo character reference."
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


def _character_prompt() -> str:
    return " ".join(
        f"""Create one IMAGE, not a video. {CHARACTER_BIBLE} {STYLE_BIBLE}
        Show one single full-body Milo in a neutral three-quarter pose on a
        clean light background. Keep his complete body visible. No character
        sheet, multiple views, text, props, scenery, or other characters.""".split()
    )


def _render_prompt_markdown(manifest: dict) -> str:
    lines = [
        f"# Meta AI automated render pack: {manifest['story']['title']}", "",
        "This pack is consumed automatically by the Playwright browser runner.",
        "The first run creates a permanent Milo reference. Each later scene",
        "receives the prior scene's final frame for visual continuity.", "",
        "## Character reference", "", _character_prompt(),
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
    (job_dir / "milo_reference_prompt.txt").write_text(
        _character_prompt() + "\n", encoding="utf-8"
    )
    return manifest, job_dir


def _profile_dir() -> Path:
    if not META_AI_CHROME_PROFILE_DIR.strip():
        raise MetaAIAutomationError(
            "META_AI_CHROME_PROFILE_DIR is required. Set it to an absolute, "
            "persistent directory on the self-hosted runner."
        )
    path = Path(META_AI_CHROME_PROFILE_DIR).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _character_image_path(profile_dir: Path) -> Path:
    if META_AI_CHARACTER_IMAGE.strip():
        path = Path(META_AI_CHARACTER_IMAGE).expanduser().resolve()
    else:
        path = profile_dir.parent / "meta_ai_state" / "milo-reference.png"
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _launch_context(playwright, profile_dir: Path, *, headless: bool):
    kwargs = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "accept_downloads": True,
        "viewport": {"width": 1440, "height": 1100},
        "args": ["--disable-dev-shm-usage"],
    }
    if META_AI_BROWSER_CHANNEL.strip():
        kwargs["channel"] = META_AI_BROWSER_CHANNEL.strip()
    context = playwright.chromium.launch_persistent_context(**kwargs)
    context.set_default_timeout(30_000)
    return context


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
        "Meta AI prompt editor was not available. Run `python main.py "
        "--meta-login` once on the self-hosted runner, complete the Meta login, "
        "and then rerun the workflow."
    )


def _attach_image(page, image_path: Path) -> None:
    inputs = page.locator("input[type='file']")
    file_input = inputs.last if inputs.count() else None
    if file_input is None:
        for name in (r"add", r"upload", r"attach", r"photo"):
            try:
                button = _visible_last(page.get_by_role("button", name=re.compile(name, re.I)))
                if button is not None:
                    button.click()
                    page.wait_for_timeout(750)
                    inputs = page.locator("input[type='file']")
                    file_input = inputs.last if inputs.count() else None
                    if file_input is not None:
                        break
            except Exception:
                continue
    if file_input is None:
        raise MetaAIAutomationError("Meta AI image-upload control was not found.")
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
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        for name in (r"create", r"generate", r"send", r"submit"):
            try:
                button = _visible_last(page.get_by_role("button", name=re.compile(name, re.I)))
                if button is not None and button.is_enabled():
                    button.click()
                    return
            except Exception:
                continue
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


def _ensure_character_reference(context, profile_dir: Path, job_dir: Path) -> Path:
    character_path = _character_image_path(profile_dir)
    if character_path.is_file() and character_path.stat().st_size >= 10_000:
        return character_path
    print(f"[MetaAI] Creating permanent Milo reference -> {character_path}")
    _generate_media(
        context, _character_prompt(), character_path, "image", None,
        job_dir / "debug" / "character-reference.png",
    )
    return character_path


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
    sync_playwright = _load_playwright()
    manifest["status"] = "rendering"
    _save_manifest(manifest, job_dir)

    with sync_playwright() as playwright:
        context = _launch_context(playwright, profile_dir, headless=META_AI_HEADLESS)
        try:
            character_path = _ensure_character_reference(context, profile_dir, job_dir)
            prior_frame: Path | None = None
            for scene in manifest["scenes"]:
                target = renders_dir / scene["filename"]
                frame_target = job_dir / "continuity" / f"scene_{scene['index']:02d}_last.jpg"
                if target.is_file() and target.stat().st_size >= 10_000:
                    if not frame_target.is_file():
                        _extract_last_frame(target, frame_target)
                    prior_frame = frame_target
                    continue

                attachment = prior_frame or character_path
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
                    except Exception as error:
                        last_error = error
                        print(f"[MetaAI] Scene {scene['index']} failed: {type(error).__name__}")
                        time.sleep(min(attempt * 10, 30))
                if last_error is not None:
                    raise MetaAIAutomationError(
                        f"Scene {scene['index']} failed after {META_AI_MAX_RETRIES} attempts: {last_error}"
                    ) from last_error
        finally:
            context.close()
    return collect_rendered_clips(manifest, job_dir)


def bootstrap_meta_login() -> None:
    """Open the dedicated persistent profile for the one-time interactive login."""
    profile_dir = _profile_dir()
    sync_playwright = _load_playwright()
    with sync_playwright() as playwright:
        context = _launch_context(playwright, profile_dir, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            _open_create_page(page)
            print("[MetaAI] Complete the Meta login in the opened browser window.")
            input("[MetaAI] When the Create prompt box is visible, press Enter here: ")
            _require_logged_in_editor(page)
            print(f"[MetaAI] Login verified. Persistent profile: {profile_dir}")
        finally:
            context.close()


def mark_job_complete(job_dir: Path, video_id: str) -> None:
    manifest_path = job_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "uploaded"
    manifest["youtube_video_id"] = video_id
    _save_manifest(manifest, job_dir)
