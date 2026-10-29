"""Free community AI fallbacks for scripts and Channel 3 motion scenes.

AI Horde is a volunteer-powered queue. Anonymous access uses the public key
``0000000000`` and receives the lowest priority. Prompts and anonymous images
must be treated as public, so this module must never receive secrets or private
source material.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
from pathlib import Path

import requests

from config import (
    AI_HORDE_API_KEY,
    AI_HORDE_IMAGE_MODEL,
    AI_HORDE_IMAGE_TIMEOUT_SECONDS,
    AI_HORDE_TEXT_MODEL,
    AI_HORDE_TEXT_TIMEOUT_SECONDS,
)


API_ROOT = "https://aihorde.net/api/v2"
CLIENT_AGENT = "ahfirhack-youtube:1.0:https://github.com/ahfirhack/ahfirhack"
SAFE_IMAGE_MODELS = (
    "stable_diffusion_2.1",
    "stable_diffusion",
    "DreamShaper XL",
    "Dreamshaper",
)
UNSAFE_MODEL_TERMS = (
    "nsfw",
    "uncensored",
    "hentai",
    "pony",
    "heretic",
    "aggressive",
)


class AIHordeError(RuntimeError):
    """AI Horde could not supply a usable generation."""


def _headers(*, authenticated: bool = False) -> dict[str, str]:
    headers = {"Client-Agent": CLIENT_AGENT}
    if authenticated:
        headers["apikey"] = AI_HORDE_API_KEY
    return headers


def _live_models(kind: str) -> list[dict]:
    response = requests.get(
        f"{API_ROOT}/status/models",
        params={"type": kind},
        headers=_headers(),
        timeout=(8, 30),
    )
    response.raise_for_status()
    payload = response.json()
    return [item for item in payload if isinstance(item, dict)]


def _choose_model(kind: str) -> str:
    configured = AI_HORDE_IMAGE_MODEL if kind == "image" else AI_HORDE_TEXT_MODEL
    if configured:
        return configured

    available = [
        model for model in _live_models(kind) if int(model.get("count") or 0) > 0
    ]
    if kind == "image":
        by_name = {str(model.get("name", "")): model for model in available}
        for name in SAFE_IMAGE_MODELS:
            if name in by_name:
                return name
        raise AIHordeError(
            "No known kid-safe Stable Diffusion model is currently served by AI Horde."
        )

    safe = [
        model
        for model in available
        if not any(
            term in str(model.get("name", "")).casefold()
            for term in UNSAFE_MODEL_TERMS + ("debug", "roleplay", "-rp-")
        )
    ]
    if not safe:
        raise AIHordeError("No suitable AI Horde text model is currently online.")

    def score(model: dict) -> tuple[int, int, int]:
        name = str(model.get("name", "")).casefold()
        if "qwen3.5" in name and "coder" not in name:
            preferred = 0
        elif "instruct" in name and "coder" not in name:
            preferred = 1
        elif any(term in name for term in ("qwen", "gemma")):
            preferred = 2
        else:
            preferred = 3
        return preferred, int(model.get("eta") or 0), -int(model.get("count") or 0)

    return str(min(safe, key=score)["name"])


def _submit(path: str, payload: dict) -> str:
    response = requests.post(
        f"{API_ROOT}/{path}",
        headers=_headers(authenticated=True),
        json=payload,
        timeout=(8, 30),
    )
    if response.status_code != 202:
        detail = response.text[:500]
        raise AIHordeError(
            f"AI Horde rejected the generation (HTTP {response.status_code}): {detail}"
        )
    request_id = str(response.json().get("id", ""))
    if not request_id:
        raise AIHordeError("AI Horde accepted the request without returning an ID.")
    return request_id


def _cancel(status_path: str, request_id: str) -> None:
    try:
        requests.delete(
            f"{API_ROOT}/{status_path}/{request_id}",
            headers=_headers(),
            timeout=(8, 20),
        )
    except requests.RequestException:
        pass


def _wait(status_path: str, request_id: str, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    latest: dict = {}
    try:
        while time.monotonic() < deadline:
            response = requests.get(
                f"{API_ROOT}/{status_path}/{request_id}",
                headers=_headers(),
                timeout=(8, 30),
            )
            response.raise_for_status()
            latest = response.json()
            if latest.get("faulted"):
                raise AIHordeError("AI Horde reported that the request faulted.")
            if latest.get("done"):
                return latest
            if latest.get("is_possible") is False:
                raise AIHordeError(
                    "No currently connected AI Horde worker can run this request."
                )
            wait_time = max(2, min(int(latest.get("wait_time") or 5), 10))
            time.sleep(wait_time)
    except Exception:
        _cancel(status_path, request_id)
        raise

    _cancel(status_path, request_id)
    position = latest.get("queue_position", "unknown")
    raise AIHordeError(
        f"AI Horde timed out after {timeout_seconds}s (queue position {position})."
    )


def generate_text(prompt: str) -> dict | None:
    """Generate one JSON script candidate through the free text queue."""
    model = _choose_model("text")
    print(f"[ScriptGen] AI Horde free queue model: {model}")
    request_id = _submit(
        "generate/text/async",
        {
            "prompt": prompt,
            "models": [model],
            "trusted_workers": True,
            "validated_backends": True,
            "slow_workers": True,
            "allow_downgrade": True,
            "params": {
                "n": 1,
                "max_context_length": 8192,
                "max_length": 700,
                "temperature": 0.7,
                "top_p": 0.9,
                "rep_pen": 1.08,
            },
        },
    )
    result = _wait(
        "generate/text/status",
        request_id,
        AI_HORDE_TEXT_TIMEOUT_SECONDS,
    )
    generations = result.get("generations") or []
    text = next(
        (
            str(item.get("text", "")).strip()
            for item in generations
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ),
        "",
    )
    if not text:
        raise AIHordeError("AI Horde returned no text generation.")

    fenced = text.strip()
    if fenced.startswith("```"):
        fenced = fenced.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = fenced.find("{"), fenced.rfind("}")
    if start < 0 or end <= start:
        raise AIHordeError("AI Horde did not return a JSON object.")
    parsed = json.loads(fenced[start : end + 1])
    return parsed if isinstance(parsed, dict) else None


def generate_image(prompt: str, target: Path, *, seed: str) -> Path:
    """Generate and download one public, kid-safe AI Horde image."""
    model = _choose_model("image")
    print(f"[FreeVideo/AIHorde] Image model: {model}")
    request_id = _submit(
        "generate/async",
        {
            "prompt": prompt,
            "models": [model],
            "nsfw": False,
            "censor_nsfw": True,
            "trusted_workers": True,
            "validated_backends": True,
            "slow_workers": True,
            "allow_downgrade": True,
            "r2": True,
            "shared": True,
            "params": {
                "n": 1,
                "width": 512,
                "height": 768,
                "steps": 24,
                "cfg_scale": 7,
                "sampler_name": "k_euler_a",
                "seed": seed,
            },
        },
    )
    result = _wait("generate/status", request_id, AI_HORDE_IMAGE_TIMEOUT_SECONDS)
    generations = result.get("generations") or []
    generation = next(
        (item for item in generations if isinstance(item, dict) and item.get("img")),
        None,
    )
    if generation is None or generation.get("censored"):
        raise AIHordeError("AI Horde returned no usable kid-safe image.")

    source = str(generation["img"])
    if source.startswith(("https://", "http://")):
        response = requests.get(source, timeout=(8, 120))
        response.raise_for_status()
        payload = response.content
    else:
        try:
            payload = base64.b64decode(source, validate=True)
        except (ValueError, TypeError) as error:
            raise AIHordeError("AI Horde returned an invalid image payload.") from error
    if len(payload) < 10_000:
        raise AIHordeError("AI Horde returned an empty or incomplete image.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def _audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _motion_clip(
    image: Path, audio: Path, target: Path, index: int, duration: int
) -> None:
    frames = duration * 30
    pans = (
        f"zoompan=z='min(1+0.00035*on,1.12)':x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':d={frames}:s=720x1280:fps=30",
        f"zoompan=z=1.10:x='(iw-iw/zoom)*on/{frames}':"
        f"y='ih/2-(ih/zoom/2)':d={frames}:s=720x1280:fps=30",
        f"zoompan=z=1.10:x='(iw-iw/zoom)*(1-on/{frames})':"
        f"y='ih/2-(ih/zoom/2)':d={frames}:s=720x1280:fps=30",
    )
    voice_duration = _audio_duration(audio)
    tempo = max(1.0, voice_duration / max(duration - 0.2, 1.0))
    filters = (
        "[0:v]scale=900:1600:force_original_aspect_ratio=increase,"
        f"crop=900:1600,{pans[(index - 1) % len(pans)]},"
        "eq=contrast=1.05:saturation=1.06,format=yuv420p[v];"
        f"[1:a]atempo={tempo:.5f},apad=pad_dur={duration},"
        f"atrim=duration={duration},asetpts=PTS-STARTPTS[a]"
    )
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(image),
            "-i",
            str(audio),
            "-filter_complex",
            filters,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            str(duration),
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0 or not target.is_file() or target.stat().st_size < 10_000:
        raise AIHordeError(f"Could not build free motion scene: {result.stderr[-500:]}")


def fallback_clip_paths(manifest: dict, job_dir: Path) -> list[str] | None:
    """Return completed fallback clips, or None if the set is incomplete."""
    paths = [
        job_dir / "free_renders" / scene["filename"] for scene in manifest["scenes"]
    ]
    if all(path.is_file() and path.stat().st_size >= 10_000 for path in paths):
        return [str(path) for path in paths]
    return None


def generate_motion_fallback(manifest: dict, job_dir: Path) -> list[str]:
    """Create three narrated motion scenes without a paid video service."""
    existing = fallback_clip_paths(manifest, job_dir)
    if existing:
        return existing

    from modules.voiceover import generate_voiceover

    output_dir = job_dir / "free_renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    topic = str(manifest["story"]["title"])
    character = str(manifest.get("character_bible", "Milo, a young history guide"))
    style = str(manifest.get("style_bible", "original 3D family animation"))
    job_seed = hashlib.sha256(str(manifest["job_id"]).encode()).hexdigest()[:12]

    for scene in manifest["scenes"]:
        index = int(scene["index"])
        clip = output_dir / scene["filename"]
        if clip.is_file() and clip.stat().st_size >= 10_000:
            continue
        image = output_dir / f"scene_{index:02d}.webp"
        audio = output_dir / f"scene_{index:02d}.mp3"
        prompt = " ".join(
            f"""Kid-safe vertical 9:16 cinematic still frame for an original
            premium 3D animated historical adventure about {topic}. {character}
            {style} Keep Milo's exact face, hair, clothing colors, compass, age,
            and proportions consistent across all scenes. Historical story beat:
            {scene["narration"]} Expressive natural pose, colorful accurate setting,
            cinematic lighting, polished materials, no text, no logo, no watermark.
            ### weapons, gore, frightening imagery, adult character, duplicate
            character, extra limbs, deformed hands, modern objects, readable text,
            caption, logo, watermark, black frame, blank background, nsfw""".split()
        )
        if not image.is_file() or image.stat().st_size < 10_000:
            print(f"[FreeVideo/AIHorde] Generating scene {index}/3 image")
            generate_image(prompt, image, seed=f"{job_seed}-{index}")
        if not audio.is_file() or audio.stat().st_size < 1_000:
            print(f"[FreeVideo/EdgeTTS] Generating scene {index}/3 Milo voice")
            generate_voiceover(
                str(scene["narration"]),
                str(audio),
                channel_id="channel_3",
                voice_provider="edge",
            )
        _motion_clip(
            image,
            audio,
            clip,
            index,
            int(scene.get("duration_seconds") or 10),
        )
        scene["fallback_rendered"] = True
        (job_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    clips = fallback_clip_paths(manifest, job_dir)
    if clips is None:
        raise AIHordeError("The free AI Horde motion fallback is incomplete.")
    manifest["generator"] = "AI Horde images + free Edge TTS motion fallback"
    manifest["render_backend"] = "ai_horde_motion"
    manifest["native_audio"] = True
    manifest["status"] = "ready"
    (job_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return clips
