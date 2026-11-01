"""Optional AI Horde TEXT-only story/prompt generation.

AI Horde is a volunteer-powered queue. Anonymous access uses the public key
``0000000000`` and receives the lowest priority. Prompts
must be treated as public, so this module must never receive secrets or private
source material.
"""

from __future__ import annotations

import json
import time

import requests

from config import (
    AI_HORDE_API_KEY,
    AI_HORDE_TEXT_MODEL,
    AI_HORDE_TEXT_TIMEOUT_SECONDS,
)


API_ROOT = "https://aihorde.net/api/v2"
CLIENT_AGENT = "ahfirhack-youtube:1.0:https://github.com/ahfirhack/ahfirhack"
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
    if kind != "text":
        raise AIHordeError("Only text prompt generation is permitted; no AI Horde media")
    configured = AI_HORDE_TEXT_MODEL
    if configured:
        return configured

    available = [
        model for model in _live_models(kind) if int(model.get("count") or 0) > 0
    ]
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
