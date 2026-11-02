"""Generate preview Shorts from five Meta scenes, without YouTube upload.

Single channel: python test_pipeline.py 2
All 4 channels (3 parallel browser windows): python test_pipeline.py --workers 3
Selection: python test_pipeline.py 1 2 3 --workers 3
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from config import CHANNELS
from modules.meta_ai_generator import (
    create_job, ensure_rendered_clips, find_active_job, _storage_state_path,
)
from modules.prompt_reserve import peek_prompt
from modules.video_assembler import assemble_meta_short


def test_channel(channel: dict, *, isolated_browser: bool = False) -> str:
    existing = find_active_job(channel["id"])
    if existing:
        manifest, directory = existing
    else:
        story = peek_prompt(channel["prompt_reserve_db"], channel["id"])
        if story is None:
            raise RuntimeError("No reserved story found for local preview")
        manifest, directory = create_job(channel, story)
    clips = ensure_rendered_clips(
        manifest, directory, isolated_browser=isolated_browser,
    )
    return assemble_meta_short(
        clip_paths=clips,
        output_filename=f"PREVIEW_{channel['id']}.mp4",
        continuity_dir=directory / "continuity",
        scene_seconds=10,
    )


def _preview_worker(channel: dict, *, isolated_browser: bool, assembly_lock) -> dict:
    try:
        # Keep all 3 browser generations independent. This is only a preview;
        # never reserve/consume uploads or talk to YouTube.
        existing = find_active_job(channel["id"])
        if existing:
            manifest, directory = existing
        else:
            story = peek_prompt(channel["prompt_reserve_db"], channel["id"])
            if story is None:
                raise RuntimeError("No reserved story found for local preview")
            manifest, directory = create_job(channel, story)
        clips = ensure_rendered_clips(
            manifest, directory, isolated_browser=isolated_browser,
        )
        # Limit 2K encoders to one at a time; video generation stays parallel.
        with assembly_lock:
            result = assemble_meta_short(
                clip_paths=clips,
                output_filename=f"PREVIEW_{channel['id']}.mp4",
                continuity_dir=directory / "continuity", scene_seconds=10,
            )
        return {"channel": channel["name"], "ok": True, "output": result}
    except Exception as error:
        return {"channel": channel["name"], "ok": False,
                "error": str(error)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Meta-only video preview: never uploads")
    parser.add_argument("channels", nargs="*", choices=("1", "2", "3", "4", "all"))
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3,
                        help="Maximum simultaneous browser windows; default 3")
    args = parser.parse_args(argv)
    wanted = set(args.channels)
    if not wanted or "all" in wanted:
        channels = CHANNELS
    else:
        channels = [ch for ch in CHANNELS if ch["id"] in
                    {f"channel_{value}" for value in wanted}]
    count = min(args.workers, len(channels))
    if count > 1:
        _storage_state_path(required=True)
    from threading import Lock
    assembly_lock = Lock()
    results = []
    with ThreadPoolExecutor(max_workers=count,
                            thread_name_prefix="meta-preview") as pool:
        pending = [pool.submit(_preview_worker, ch,
                               isolated_browser=count > 1,
                               assembly_lock=assembly_lock)
                   for ch in channels]
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            if result["ok"]:
                print(f"[Preview] {result['channel']} -> {result['output']}", flush=True)
            else:
                print(f"[Preview] FAIL {result['channel']}: {result['error']}", flush=True)
    return 0 if results and all(row["ok"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
