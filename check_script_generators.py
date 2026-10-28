"""Fail-fast health check for the live AI script-generator chain.

The normal pipeline discovers each provider's active models at runtime. This
check exercises that same path and validates one upload-ready result for every
non-Meta channel without writing dedup state or uploading a video.
"""

from __future__ import annotations

import datetime as dt
import os
import time

from config import CHANNELS
from modules.script_generator import (
    ScriptGenerationError,
    _detect_niche_key,
    _reject_generic_title,
    _valid_visual_packaging,
    generate_script,
)


CHANNEL_IDS = ("channel_1", "channel_2", "channel_4")


def _selected_channel_ids(today: dt.date) -> set[str]:
    requested = os.getenv("HEALTH_CHANNEL", "rotating").strip().lower()
    if requested in {"all", "1,2,4"}:
        return set(CHANNEL_IDS)
    if requested in {"1", "2", "4"}:
        return {f"channel_{requested}"}
    # Scheduled checks rotate to respect free-provider request/token limits.
    return {CHANNEL_IDS[today.toordinal() % len(CHANNEL_IDS)]}


def main() -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    seed_date = today.isoformat()
    selected = _selected_channel_ids(today)
    print(f"[Health] Selected: {', '.join(sorted(selected))}")
    failures: list[str] = []
    for channel in CHANNELS:
        if channel["id"] not in selected:
            continue
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                result = generate_script(
                    channel["niche"],
                    allow_fallback=False,
                    uniqueness_seed=(
                        f"health-{channel['id']}-{seed_date}-{attempt}"
                    ),
                )
                niche_key = _detect_niche_key(channel["niche"])
                if _reject_generic_title(result["title"], niche_key):
                    raise RuntimeError("weak or generic title escaped validation")
                if not _valid_visual_packaging(result, niche_key):
                    raise RuntimeError("visual/hook packaging is incomplete")
                print(
                    f"[Health] {channel['id']} OK: "
                    f"{len(result['script'].split())} words, "
                    f"{len(result['visual_queries'])} visual beats"
                )
                last_error = None
                break
            except (ScriptGenerationError, KeyError, RuntimeError) as error:
                last_error = error
                print(f"[Health] {channel['id']} attempt {attempt}/3 failed: {error}")
                if attempt < 3:
                    time.sleep(20)
        if last_error is not None:
            failures.append(f"{channel['id']}: {last_error}")

    if failures:
        raise SystemExit("AI script health check failed: " + " | ".join(failures))
    print("[Health] Live model discovery and strict script validation passed")


if __name__ == "__main__":
    main()
