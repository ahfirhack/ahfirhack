"""Resume an existing Meta-only scene with a clip downloaded from the user's own Meta account.

Does not generate video, connect to Meta, or upload to YouTube.
No third-party media. The selected file must be the same scene previously generated.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from config import META_AI_JOBS_DIR
from modules.meta_ai_generator import _validate_meta_clip


def recover(channel: int, downloaded_file: Path, *, jobs_root: Path | None = None) -> Path:
    if channel not in (1, 2, 3, 4):
        raise ValueError("Channel must be 1–4")
    if not downloaded_file.is_file():
        raise FileNotFoundError(f"Downloaded Meta video not found: {downloaded_file}")
    root = jobs_root or Path(META_AI_JOBS_DIR)
    channel_path = root / f"channel_{channel}"
    candidates = sorted(channel_path.glob("*/debug/scene_*_download_pending.json"))
    if not candidates:
        raise RuntimeError(
            "No pending scene download for this channel. Do not overwrite a completed scene."
        )
    if len(candidates) > 1:
        options = "\n".join(f"  {marker.parent.parent}" for marker in candidates)
        raise RuntimeError(
            "Multiple pending scenes found for this channel. Identify the correct Meta scene "
            "before importing; no file was changed.\n" + options
        )
    marker = candidates[0]
    job = marker.parent.parent
    manifest_path = job / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("channel_id") != f"channel_{channel}" or manifest.get("render_backend") != "meta_ai":
        raise RuntimeError("This is not the requested Meta-only job")
    scene_index = int(marker.stem.split("_")[1])
    scene = next((item for item in manifest.get("scenes", []) if int(item["index"]) == scene_index), None)
    if scene is None:
        raise RuntimeError("Pending scene is not listed in the job manifest")

    # Validate the source *before* touching any render or state file.
    _validate_meta_clip(downloaded_file)
    renders = job / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    target = renders / scene["filename"]
    if target.exists():
        raise RuntimeError(f"A clip already exists at {target}; refusing to overwrite it")
    tmp = target.with_name(target.name + ".importing")
    try:
        shutil.copyfile(downloaded_file, tmp)
        _validate_meta_clip(tmp)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    # The existing pipeline clears this marker only after validating the
    # imported clip and extracting its last frame, ensuring handoff quality.
    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import one previously generated Meta scene into the paused video job."
    )
    parser.add_argument("--channel", type=int, required=True, choices=(1, 2, 3, 4))
    parser.add_argument("--file", type=Path, required=True,
                        help="Local video saved manually from the same Meta scene")
    args = parser.parse_args()
    try:
        target = recover(args.channel, args.file.expanduser())
    except Exception as err:
        print(f"[Recovery] Cannot import: {err}", file=sys.stderr)
        return 1
    print(f"[Recovery] Valid scene imported to: {target}")
    print("[Recovery] The generation-pending marker is preserved until the original "
          "pipeline revalidates the scene. Run python test_pipeline.py "
          f"{args.channel} --workers 1 next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
