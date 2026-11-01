"""Download a video produced in the user's signed-in Meta Create/Vibes browser.

No third-party source, secret extraction or hidden service endpoints are used. The
visible Download/Export control is preferred over reading a temporary player URL.
A clip is committed only after the caller's ffprobe/media checks succeed.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit


class MetaClipDownloadError(RuntimeError):
    """Meta finished rendering, but the completed video was not saved."""

    def __init__(self, message: str, *, rejection_reasons=()):
        super().__init__(message)
        self.rejection_reasons = frozenset(rejection_reasons)


class _Capture:
    """Observe downloads started in this isolated Playwright browser context."""

    def __init__(self, context, page):
        self.context, self.page = context, page
        self.downloads = []
        self._pages = []
        self._seen = set()

    def _on_download(self, item):
        self.downloads.append(item)

    def _on_new_page(self, page):
        self._listen(page)

    def _listen(self, page):
        key = id(page)
        if key not in self._seen:
            self._seen.add(key)
            page.on("download", self._on_download)
            self._pages.append(page)

    def __enter__(self):
        self._listen(self.page)
        for page in getattr(self.context, "pages", []):
            self._listen(page)
        self.context.on("page", self._on_new_page)
        return self

    def __exit__(self, *_):
        try:
            self.context.remove_listener("page", self._on_new_page)
        except Exception:
            pass
        for page in self._pages:
            try:
                page.remove_listener("download", self._on_download)
            except Exception:
                pass


def _find_visible(locator):
    try:
        for idx in range(locator.count() - 1, -1, -1):
            candidate = locator.nth(idx)
            if candidate.is_visible() and candidate.is_enabled():
                return candidate
    except Exception:
        return None
    return None


_DOWNLOAD = re.compile(
    r"^(?:download(?:\s+(?:video|clip|mp4|original|file|hd|1080p|720p|4k))?"
    r"|save (?:video|clip|mp4)|export (?:video|mp4)|download\s*\(.*\))$", re.I
)
_EXPORT = re.compile(r"^(?:export|export video|export clip)$", re.I)
_MORE = re.compile(r"^(?:more(?: options| actions)?|options|actions|\.\.\.|⋯)$", re.I)


def _page_and_frames(page):
    frames = [page]
    try:
        frames.extend(frame for frame in page.frames if frame != page.main_frame)
    except Exception:
        pass
    return frames


def _find_action(page, kind: str):
    pattern = {"download": _DOWNLOAD, "export": _EXPORT, "more": _MORE}[kind]
    # Prefer newly added result controls (last in document order). Embedded
    # Meta editors sometimes render inside an iframe.
    for frame in reversed(_page_and_frames(page)):
        for role in ("menuitem", "button", "link"):
            action = _find_visible(frame.get_by_role(role, name=pattern))
            if action is not None:
                return action
        if kind == "download":
            selectors = (
                "button[aria-label*='download' i]",
                "button[title*='download' i]",
                "a[download]",
                "[data-testid*='download' i]",
                "svg[aria-label*='download' i]",
            )
        elif kind == "export":
            selectors = (
                "button[aria-label*='export' i]",
                "button[title*='export' i]",
                "[data-testid*='export' i]",
            )
        else:
            selectors = (
                "button[aria-label='More']",
                "button[title='More']",
                "button[aria-label='More options']",
            )
        for selector in selectors:
            action = _find_visible(frame.locator(selector))
            if action is not None:
                if selector.startswith("svg"):
                    try:
                        action = action.locator("xpath=ancestor::button[1]")
                    except Exception:
                        continue
                return action
    return None


def has_download_control(page) -> bool:
    """Only for post-generation readiness; not proof of completed video by itself."""
    return _find_action(page, "download") is not None


def _wait(page, milliseconds: int) -> None:
    try:
        page.wait_for_timeout(milliseconds)
    except Exception:
        time.sleep(milliseconds / 1000)


def _validation_label(error: Exception) -> str:
    """Use only fixed categories; exception messages can contain private URLs."""
    reason = str(error).lower()
    if "missing video or meta-native audio" in reason:
        return "missing_native_audio_or_video_track"
    if "required is one complete 10s" in reason:
        return "clip_duration_not_10_seconds"
    if "must be 9:16-ish portrait" in reason:
        return "not_portrait_video"
    if "below the required" in reason and "source quality" in reason:
        return "source_resolution_below_1080p"
    if "ffprobe" in reason or "metadata" in reason:
        return "invalid_video_container"
    if "did not return a real video" in reason:
        return "not_a_video_file"
    return "validation_rejected"


def _video_metadata(path: Path) -> dict:
    """Local, privacy-safe video-only metadata. No media URL or filenames."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {"readable": False}
        info = json.loads(result.stdout)
        streams = info.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        duration = float(info.get("format", {}).get("duration") or 0)
        return {
            "readable": bool(video),
            "duration_seconds": round(duration, 3),
            "video_width": int(video.get("width") or 0) if video else 0,
            "video_height": int(video.get("height") or 0) if video else 0,
            "audio_track": any(s.get("codec_type") == "audio" for s in streams),
        }
    except Exception:
        return {"readable": False}


def _keep_rejected_video(part: Path, target: Path, meta: dict) -> str | None:
    """Preserve a playable rejected Meta clip outside renders, never HTML or JSON."""
    if not meta.get("readable") or not part.exists() or part.stat().st_size > 150 * 1024 * 1024:
        return None
    debug = target.parent.parent / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    saved = debug / f"{target.stem}_rejected_export.mp4"
    if saved.exists():
        return saved.name
    try:
        shutil.copyfile(part, saved)
        return saved.name
    except Exception:
        return None


def _commit_file(part: Path, target: Path, validate, record_issue=None, method="download") -> bool:
    try:
        if not part.is_file() or part.stat().st_size < 10_000:
            if record_issue:
                record_issue({"method": method, "reason": "empty_or_nonvideo_response"})
            return False
        with part.open("rb") as stream:
            first_byte = stream.read(1)
        if first_byte in (b"<", b"{"):
            if record_issue:
                record_issue({"method": method, "reason": "empty_or_nonvideo_response"})
            return False
        try:
            validate(part)
        except Exception as error:
            meta = _video_metadata(part)
            kept_name = _keep_rejected_video(part, target, meta)
            report = {"method": method, "reason": _validation_label(error), "media": meta}
            if kept_name:
                report["preserved_in_debug"] = kept_name
            if record_issue:
                record_issue(report)
            return False
        part.replace(target)
        return True
    finally:
        part.unlink(missing_ok=True)


def _commit_valid_bytes(payload: bytes, target: Path, validate,
                        record_issue=None, method="media-source") -> bool:
    if len(payload) < 10_000 or payload[:1] in (b"<", b"{"):
        if record_issue:
            record_issue({"method": method, "reason": "empty_or_nonvideo_response"})
        return False
    part = target.with_name(target.name + ".download-part")
    part.unlink(missing_ok=True)
    try:
        part.write_bytes(payload)
        return _commit_file(part, target, validate, record_issue, method)
    except Exception:
        if record_issue:
            record_issue({"method": method, "reason": "file_write_error"})
        return False
    finally:
        part.unlink(missing_ok=True)


def _commit_download(download, target: Path, validate, record_issue=None) -> bool:
    part = target.with_name(target.name + ".download-part")
    part.unlink(missing_ok=True)
    try:
        download.save_as(str(part))
    except Exception:
        if record_issue:
            record_issue({"method": "browser-download", "reason": "browser_download_save_failed"})
        part.unlink(missing_ok=True)
        return False
    try:
        return _commit_file(part, target, validate, record_issue, "browser-download")
    except Exception:
        if record_issue:
            record_issue({"method": "browser-download", "reason": "file_write_error"})
        return False
    finally:
        part.unlink(missing_ok=True)


def _try_browser_media_fetch(context, page, source: str, target: Path, validate, record_issue=None) -> bool:
    if not source:
        return False
    parsed = urlsplit(source)
    if parsed.scheme in {"https", "http"}:
        # Only the already-present <video> source; never guess a private API.
        try:
            response = context.request.get(
                source, timeout=120_000, headers={"Referer": page.url, "Accept": "video/*,*/*"}
            )
            if response.ok and not any(x in (response.headers.get("content-type") or "").lower()
                                       for x in ("text/html", "application/json")):
                if _commit_valid_bytes(response.body(), target, validate, record_issue):
                    return True
        except Exception:
            if record_issue:
                record_issue({"method": "media-source", "reason": "http_media_fetch_failed"})
    if parsed.scheme not in {"https", "http", "blob", "data"}:
        return False
    for frame in _page_and_frames(page):
        try:
            # Browser-generated blob: URLs cannot be fetched by requests/HTTP.
            # A blob made in a child iframe must be fetched in THAT frame.
            encoded = frame.evaluate(
                """async url => {
                    const response = await fetch(url, {credentials:'include'});
                    if (!response.ok) throw new Error('Media fetch failed');
                    const blob = await response.blob();
                    if (blob.size > 120 * 1024 * 1024) throw new Error('Clip too large');
                    return await new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload = () => resolve(reader.result);
                        reader.onerror = reject;
                        reader.readAsDataURL(blob);
                    });
                }""", source
            )
            if isinstance(encoded, str) and "," in encoded:
                if _commit_valid_bytes(base64.b64decode(encoded.split(",", 1)[1]), target, validate, record_issue):
                    return True
        except Exception:
            if record_issue:
                record_issue({"method": "media-source", "reason": "browser_media_fetch_failed"})
    return False


def _safe_diagnostic(path: Path | None, events: dict) -> Path | None:
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never write media URLs, cookies, names, prompt text, HTML or query strings.
    path.write_text(json.dumps(events, indent=2), encoding="utf-8")
    return path


def save_generated_clip(context, page, source: str, target: Path, validate,
                        *, diagnostic_path: Path | None = None,
                        source_supplier=None, max_wait_seconds: float | None = None) -> None:
    """Use Meta's visible Download/Export first; fallback to its video player.

    A generated scene is NOT resubmitted just because export failed. A successful
    video is written atomically after ffprobe confirms it is suitable for the
    five-clip assembler. All diagnostic fields exclude credentials/media URLs.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if max_wait_seconds is None:
        try:
            max_wait_seconds = max(10, min(180, int(os.getenv("META_AI_DOWNLOAD_WAIT_SECONDS", "75"))))
        except ValueError:
            max_wait_seconds = 75
    data = {"ui_actions": [], "download_events": 0,
            "source_scheme": urlsplit(source).scheme if source else "none",
            "source_fetch_attempted": False, "saved": False,
            "rejections": [], "download_controls_seen": False}
    def record_issue(issue: dict) -> None:
        # Cap diagnostic size, but retain the first actionable cause.
        if issue not in data["rejections"] and len(data["rejections"]) < 12:
            data["rejections"].append(issue)
    target.unlink(missing_ok=True)
    checked_sources = set()
    with _Capture(context, page) as capture:
        seen = 0
        clicks = {"download": 0, "export": 0, "more": 0}
        started = time.monotonic()
        deadline = started + max_wait_seconds
        next_source_attempt = started + 12
        while time.monotonic() < deadline:
            # If the result controls are initially hidden, hovering reveals
            # them without clicking/submitting another generation prompt.
            if (time.monotonic() - started < 2 or sum(clicks.values()) == 0):
                try:
                    video = _find_visible(page.locator("video"))
                    if video is not None:
                        video.hover(timeout=1200)
                except Exception:
                    pass
            while seen < len(capture.downloads):
                download = capture.downloads[seen]
                seen += 1
                data["download_events"] += 1
                if _commit_download(download, target, validate, record_issue):
                    data["saved"] = True
                    data["method"] = "browser-download"
                    _safe_diagnostic(diagnostic_path, data)
                    return
                data["ui_actions"].append("invalid-download")

            for kind, cap in (("download", 2), ("export", 2), ("more", 1)):
                # Capture whether there was any UI export option at all.
                if kind == "download":
                    try:
                        data["download_controls_seen"] = data["download_controls_seen"] or has_download_control(page)
                    except Exception:
                        pass
                if clicks[kind] >= cap:
                    continue
                control = _find_action(page, kind)
                if control is None:
                    continue
                clicks[kind] += 1
                data["ui_actions"].append(kind)
                try:
                    control.click(timeout=4_000)
                except Exception:
                    data["ui_actions"].append(f"{kind}-click-failed")
                # Give a popup or asynchronous Export action time to start.
                _wait(page, 1500)
                break

            # Some Meta pages expose a temporary blob/video URL instead of a
            # Download button. Only fetch sources actually present in the user's
            # newly generated result, never guessed/private endpoints.
            if time.monotonic() >= next_source_attempt:
                next_source_attempt = time.monotonic() + 16
                candidates = [source] if source else []
                if source_supplier is not None:
                    try:
                        candidates.extend(source_supplier())
                    except Exception:
                        pass
                for candidate in dict.fromkeys(x for x in candidates if x):
                    # A previously invalid preview can eventually finalize;
                    # retry it at most once per polling interval.
                    if len(checked_sources) < 10:
                        checked_sources.add(candidate)
                    data["source_fetch_attempted"] = True
                    if _try_browser_media_fetch(context, page, candidate, target, validate, record_issue):
                        data["saved"] = True
                        data["method"] = "media-source"
                        _safe_diagnostic(diagnostic_path, data)
                        return
            _wait(page, 900)

        # Handle a download triggered just before the deadline.
        while seen < len(capture.downloads):
            download = capture.downloads[seen]
            seen += 1
            data["download_events"] += 1
            if _commit_download(download, target, validate, record_issue):
                data["saved"] = True
                data["method"] = "browser-download"
                _safe_diagnostic(diagnostic_path, data)
                return
    # Last direct-source attempt, after the renderer has had time to finalize.
    candidates = [source] if source else []
    if source_supplier is not None:
        try:
            candidates.extend(source_supplier())
        except Exception:
            pass
    for candidate in dict.fromkeys(x for x in candidates if x):
        data["source_fetch_attempted"] = True
        if _try_browser_media_fetch(context, page, candidate, target, validate, record_issue):
            data["saved"] = True
            data["method"] = "media-source"
            _safe_diagnostic(diagnostic_path, data)
            return
    # Read-only DOM player metadata. Excludes source URLs, prompts and cookies.
    try:
        data["player_summary"] = page.locator("video").evaluate_all("""elements => elements.slice(-3).map(v => ({
            duration_seconds: Number.isFinite(v.duration) ? Math.round(v.duration * 1000) / 1000 : null,
            ready_state: v.readyState, width: v.videoWidth, height: v.videoHeight,
            source_scheme: ((v.currentSrc || v.src || '').split(':')[0] || 'none'),
        }))""")
    except Exception:
        data["player_summary"] = []
    location = _safe_diagnostic(diagnostic_path, data)
    hint = f" Diagnostic: {location}" if location else ""
    raise MetaClipDownloadError(
        "Meta video rendered but no valid clip was saved using its Download/Export "
        "control or browser media source. The job is paused to avoid "
        "regenerating the same scene and wasting credits." + hint,
        rejection_reasons={
            item.get("reason") for item in data["rejections"]
            if isinstance(item, dict) and isinstance(item.get("reason"), str)
        },
    )


def visible_download_control_count(page) -> int:
    """Count explicit Download actions; used only to detect NEW render results."""
    count = 0
    frames = [page]
    try:
        frames.extend(frame for frame in page.frames if frame != page.main_frame)
    except Exception:
        pass
    for frame in frames:
        for role in ("button", "link", "menuitem"):
            try:
                locator = frame.get_by_role(role, name=_DOWNLOAD)
                count += sum(1 for i in range(locator.count()) if locator.nth(i).is_visible())
            except Exception:
                pass
        try:
            locator = frame.locator("a[download], [data-testid*='download' i]")
            count += sum(1 for i in range(locator.count()) if locator.nth(i).is_visible())
        except Exception:
            pass
    return count
