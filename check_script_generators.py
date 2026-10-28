"""Fail-fast health check for the live AI script-generator chain.

The normal pipeline discovers each provider's active models at runtime. This
check exercises that same path and validates one upload-ready result for every
non-Meta channel without writing dedup state or uploading a video.
"""

from __future__ import annotations

import datetime as dt

from config import CHANNELS
from modules.script_generator import (
    ScriptGenerationError,
    _detect_niche_key,
    _reject_generic_title,
    _valid_visual_packaging,
    generate_script,
)


CHANNEL_IDS = {"channel_1", "channel_2", "channel_4"}


def main() -> None:
    seed_date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    failures: list[str] = []
    for channel in CHANNELS:
        if channel["id"] not in CHANNEL_IDS:
            continue
        try:
            result = generate_script(
                channel["niche"],
                allow_fallback=False,
                uniqueness_seed=f"health-{channel['id']}-{seed_date}",
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
        except (ScriptGenerationError, KeyError, RuntimeError) as error:
            failures.append(f"{channel['id']}: {error}")
            print(f"[Health] {channel['id']} FAILED: {error}")

    if failures:
        raise SystemExit("AI script health check failed: " + " | ".join(failures))
    print("[Health] Live model discovery and script validation passed for channels 1, 2, and 4")


if __name__ == "__main__":
    main()
