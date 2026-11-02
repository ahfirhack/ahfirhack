"""Manual, isolated GitHub Actions Meta video smoke test.

One scene: generate -> browser download -> validate MP4. Five scenes: also
exercise the previous-frame handoffs and FFmpeg Short assembly.

No YouTube import/upload, third-party media, stock images or TTS. This script
never reads or mutates existing production video jobs or prompt queues when the
workflow supplies its separate META_AI_JOBS_DIR.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import CHANNELS, META_AI_JOBS_DIR
from modules.meta_ai_generator import (
    MetaAIAutomationError,
    MetaAIDownloadPending,
    _check_scene_handoff,
    _extract_last_frame,
    _generate_media,
    _launch_context,
    _load_playwright,
    _storage_state_path,
    _storage_state_slots,
    _validate_meta_clip,
    create_job,
)
from modules.video_assembler import assemble_meta_short

# A synthetic browser-render scenario: no third-party script writer/API key required.
STORY = (
    "At midnight Mara found a train ticket dated tomorrow. "
    "The platform was empty except for a man watching the station clock. "
    "She heard a train approaching, although the tracks beneath her were silent. "
    "On the ticket, her own handwriting warned her not to board. "
    "The stranger showed an identical ticket and pointed behind her. "
    "Mara turned and watched the clock run backward. "
    "A younger version of herself stepped out of the shadows. "
    "The stranger whispered that only one of them could take the last train. "
    "Mara tore both tickets in half, and the platform lights came back on."
)


def _video_metadata(path: Path) -> dict:
    """Minimal read-only FFprobe metadata, compatible with earlier downloader patches."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    info = json.loads(result.stdout)
    video = next((item for item in info.get("streams", [])
                  if item.get("codec_type") == "video"), None)
    return {
        "readable": bool(video),
        "duration_seconds": round(float(info.get("format", {}).get("duration") or 0), 3),
        "video_width": int(video.get("width") or 0) if video else 0,
        "video_height": int(video.get("height") or 0) if video else 0,
        "audio_track": any(item.get("codec_type") == "audio" for item in info.get("streams", [])),
    }


def _write_status(artifact_root: Path, report: dict) -> None:
    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "result.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    completed = len([s for s in report.get("scenes", []) if s.get("status") == "passed"])
    lines = [
        "# Meta AI GitHub Actions smoke test", "",
        f"- Result: **{report['result'].upper()}**",
        f"- Scenes validated: **{completed}/{report['requested_scenes']}**",
        "- Media source: **Meta AI only**",
        "- YouTube upload: **disabled**", "",
    ]
    if report.get("failure"):
        fail = report["failure"]
        lines.extend([
            f"- Failed stage: **{fail['stage']}**",
            f"- Error type: **{fail['type']}**",
            f"- Next step: {fail['hint']}", "",
        ])
    if report.get("assembled_video"):
        lines.append("- Final 50-second MP4: saved as a workflow artifact")
    (artifact_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _failure_hint(error_type: str) -> str:
    """Fixed messages only: don't copy secret-bearing browser errors to artifacts."""
    return {
        "MetaAIDownloadPending": "Meta rendered the clip but download/validation failed. Inspect diagnostics/scene_XX_download.json; do not regenerate automatically.",
        "MetaAILoginRequired": "The GitHub-hosted browser needs a valid Meta login. Refresh META_AI_STORAGE_STATE_B64 from your signed-in Chrome profile.",
        "MetaAIEditorUnavailable": "The Meta Create editor was not detected in the GitHub-hosted browser. Check the editor diagnostics and the account session.",
        "MetaAIVideoUnavailable": "Video generation or account quota is unavailable for this Meta session.",
        "MetaAIQualityUnavailable": "This Meta account does not offer the required native 720p source generation.",
        "MetaAIAutomationError": "Meta generation/validation failed. Check the run logs and safe diagnostics.",
        "FileNotFoundError": "Required browser session, ffmpeg, or project file is missing.",
    }.get(error_type, "Check the failed stage and safe diagnostic JSON; no automatic retry was performed.")


def _copy_safe_diagnostics(job_dir: Path | None, artifacts: Path) -> None:
    if job_dir is None:
        return
    debug_dir = job_dir / "debug"
    if not debug_dir.is_dir():
        return
    dest = artifacts / "diagnostics"

    # Only fixed labels emitted by the checked-in downloader are safe to upload.
    action_labels = {"download", "export", "more", "invalid-download", "download-click-failed", "export-click-failed", "more-click-failed"}
    method_labels = {"browser-download", "media-source", "download", "unknown"}
    reason_labels = {
        "empty_or_nonvideo_response", "missing_native_audio_or_video_track",
        "clip_duration_not_10_seconds", "not_portrait_video",
        "source_resolution_below_720p", "invalid_video_container",
        "not_a_video_file", "validation_rejected", "browser_download_save_failed",
        "file_write_error", "http_media_fetch_failed", "browser_media_fetch_failed",
    }

    def allow(value: object, allowed: set[str]) -> str:
        return value if isinstance(value, str) and value in allowed else "unclassified"

    def plain_label(value: object) -> str:
        # Safe for structured route/type fields only; never arbitrary error text.
        return value[:75] if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,75}", value) else "unclassified"

    for pattern in ("scene_*_download.json", "scene_*_download_pending.json", "scene_*_editor_check.json"):
        for source in sorted(debug_dir.glob(pattern)):
            dest.mkdir(parents=True, exist_ok=True)
            # The existing module writes safe fields: no credentials or media URLs.
            # Nevertheless, upload only explicit allowlisted metadata; never
            # upload screenshots, HTML, raw browser state or full Playwright traces.
            try:
                raw = json.loads(source.read_text(encoding="utf-8"))
                if pattern == "scene_*_download.json":
                    filtered = {
                        "download_events": raw.get("download_events") if type(raw.get("download_events")) is int else None,
                        "saved": raw.get("saved") is True,
                        "download_controls_seen": raw.get("download_controls_seen") is True,
                        "source_fetch_attempted": raw.get("source_fetch_attempted") is True,
                        "source_scheme": allow(raw.get("source_scheme"), {"none", "http", "https", "blob", "data"}),
                        "ui_actions": [allow(v, action_labels) for v in raw.get("ui_actions", []) if isinstance(v, str)][:20],
                        "rejections": [{
                            "method": allow(v.get("method"), method_labels),
                            "reason": allow(v.get("reason"), reason_labels),
                            "media": {key: val for key, val in v.get("media", {}).items()
                                      if key in ("readable", "duration_seconds", "video_width", "video_height", "audio_track")
                                      and isinstance(val, (bool, int, float))},
                        } for v in raw.get("rejections", []) if isinstance(v, dict)][:12],
                    }
                elif pattern == "scene_*_editor_check.json":
                    filtered = {"results": [{
                        "surface": plain_label(item.get("surface")),
                        "site": plain_label(item.get("site")),
                        "route": plain_label(str(item.get("route", "")).strip("/") or "root"),
                        "auth_gate_visible": item.get("auth_gate_visible") is True,
                        "problem": plain_label(item.get("problem")),
                    } for item in raw.get("results", []) if isinstance(item, dict)][:3]}
                else:
                    filtered = {"status": raw.get("status", "rendered_but_download_pending")}
                (dest / source.name).write_text(json.dumps(filtered, indent=2) + "\n", encoding="utf-8")
            except (OSError, ValueError, TypeError, AttributeError):
                continue


def run_smoke(scene_count: int, artifact_root: Path) -> bool:
    if scene_count not in (1, 5):
        raise ValueError("Only one-scene download test or five-scene full test is supported")
    artifacts = Path(artifact_root)
    artifacts.mkdir(parents=True, exist_ok=True)
    report = {
        "result": "running",
        "requested_scenes": scene_count,
        "scenes": [],
        "source": "Meta AI Create (browser)",
        "youtube_upload": False,
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_status(artifacts, report)
    job_dir: Path | None = None
    stage = "preflight"
    try:
        # No attempt to reuse the normal Windows Chrome process on this runner.
        # The session comes exclusively from the GitHub Actions secret.
        _storage_state_path(required=True)
        account_slots = _storage_state_slots(required=True)
        channel = next(c for c in CHANNELS if c["id"] == "channel_3")
        if channel.get("media_source") != "meta_ai_browser":
            raise RuntimeError("Epic History Kids is not configured for Meta media")
        story = {"title": "Meta GitHub fresh generation and download smoke test", "script": STORY}
        manifest, job_dir = create_job(channel, story)
        print(f"[Smoke] New isolated job created; generating {scene_count} scene(s), no YouTube upload", flush=True)

        stage = "launch_browser"
        sync_playwright = _load_playwright()
        with sync_playwright() as pw:
            previous_last: Path | None = None
            clips: list[str] = []
            unavailable_accounts: set[int] = set()
            for scene in manifest["scenes"][:scene_count]:
                generated = False
                account_errors = []
                for slot, state_path in account_slots:
                    if slot in unavailable_accounts:
                        continue
                    # Every account uses a private context loaded from only its
                    # own state file. Sessions and cookies are never combined.
                    context, browser = _launch_context(
                        pw, None, headless=False,
                        storage_state_path=state_path,
                    )
                    try:
                        print(f"[Smoke] Trying Meta account {slot}", flush=True)
                        number = scene["index"]
                        stage = f"scene_{number:02d}_generate_download"
                        target = job_dir / "renders" / scene["filename"]
                        debug = job_dir / "debug" / f"scene_{number:02d}.png"
                        print(f"[Smoke] Scene {number}/{scene_count}: generate on Meta then download", flush=True)
                        # One submission per account. A rendered-but-undownloaded
                        # scene never falls through to another account.
                        _generate_media(context, scene["prompt"], target, "video", previous_last, debug)
                        stage = f"scene_{number:02d}_validate"
                        _validate_meta_clip(target)
                        generated = True
                        break
                    except MetaAIDownloadPending:
                        raise
                    except MetaAIAutomationError as error:
                        unavailable_accounts.add(slot)
                        account_errors.append(f"account {slot}={type(error).__name__}")
                        print(
                            f"[Smoke] Account {slot} unavailable; trying the next account",
                            flush=True,
                        )
                    finally:
                        try:
                            context.close()
                        finally:
                            if browser is not None:
                                browser.close()
                if not generated:
                    raise MetaAIAutomationError(
                        "All configured Meta accounts failed (" +
                        ", ".join(account_errors) + ")."
                    )

                number = scene["index"]
                target = job_dir / "renders" / scene["filename"]
                if previous_last is not None:
                    _check_scene_handoff(previous_last, target)
                last = job_dir / "continuity" / f"scene_{number:02d}_last.png"
                _extract_last_frame(target, last)
                previous_last = last
                clips.append(str(target))
                metadata = _video_metadata(target)
                metadata["meta_account_slot"] = slot
                (artifacts / "clips").mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, artifacts / "clips" / target.name)
                report["scenes"].append({"index": number, "status": "passed", "media": metadata})
                _write_status(artifacts, report)
                print(f"[Smoke] PASS scene {number}: downloaded and validated, native audio present", flush=True)
            if scene_count == 5:
                stage = "assemble_five_scenes"
                assembled = assemble_meta_short(
                    clip_paths=clips,
                    output_filename="META_GITHUB_SMOKE_50S.mp4",
                    continuity_dir=job_dir / "continuity",
                    scene_seconds=10,
                )
                (artifacts / "short").mkdir(parents=True, exist_ok=True)
                shutil.copy2(assembled, artifacts / "short" / "META_GITHUB_SMOKE_50S.mp4")
                report["assembled_video"] = "short/META_GITHUB_SMOKE_50S.mp4"
        report["result"] = "passed"
        print(f"[Smoke] PASS: {scene_count} Meta clip(s) saved; no YouTube upload", flush=True)
        return True
    except Exception as error:
        category = type(error).__name__
        report["result"] = "failed"
        report["failure"] = {
            "stage": stage,
            "type": category,
            "hint": _failure_hint(category),
        }
        print(f"[Smoke] FAIL at {stage}: {category}. {_failure_hint(category)}", flush=True)
        return False
    finally:
        report["completed_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _copy_safe_diagnostics(job_dir, artifacts)
        _write_status(artifacts, report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate/download 1 Meta clip or a 5-scene Short in a fresh GitHub runner job")
    parser.add_argument("--scenes", choices=(1, 5), default=1, type=int)
    parser.add_argument("--artifacts", type=Path, default=Path("meta_smoke_artifacts"))
    args = parser.parse_args()
    return 0 if run_smoke(args.scenes, args.artifacts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
