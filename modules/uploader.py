"""
uploader.py (v3 — YouTube Algorithm Optimized 2026)
- SEO descriptions with keywords, hashtags, and CTA
- Proper category IDs per niche (not generic "22")
- Structured tags for search discovery
"""

import os
import pickle
import json
import re
import socket
import threading
import time
from pathlib import Path
import httplib2
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import UPLOADED_TITLES_FILE

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

AUTH_HTTP_TIMEOUT = 30
UPLOAD_HTTP_TIMEOUT = 60
MAX_UPLOAD_TIMEOUTS = 4
_UPLOAD_LEDGER_LOCK = threading.Lock()


def _normalized_title(title: str) -> str:
    """Normalize titles so '#Shorts' or punctuation cannot hide a duplicate."""
    without_shorts = re.sub(r"#?shorts?\b", " ", title, flags=re.IGNORECASE)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_shorts.lower()).split())


def _load_upload_ledger(path: str | Path | None = None) -> dict:
    ledger_path = Path(path or UPLOADED_TITLES_FILE)
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "channels": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("channels"), dict):
        return {"version": 1, "channels": {}}
    return payload


def _recorded_upload(
    channel_id: str,
    normalized_title: str,
    path: str | Path | None = None,
) -> str:
    """Return a prior video ID without spending YouTube read quota."""
    with _UPLOAD_LEDGER_LOCK:
        ledger = _load_upload_ledger(path)
        entry = ledger["channels"].get(channel_id, {}).get(normalized_title, {})
        return str(entry.get("video_id") or "") if isinstance(entry, dict) else ""


def _remember_upload(
    channel_id: str,
    normalized_title: str,
    title: str,
    video_id: str,
    path: str | Path | None = None,
) -> None:
    """Atomically persist a successful upload receipt for idempotent retries."""
    ledger_path = Path(path or UPLOADED_TITLES_FILE)
    with _UPLOAD_LEDGER_LOCK:
        ledger = _load_upload_ledger(ledger_path)
        channel_entries = ledger["channels"].setdefault(channel_id, {})
        channel_entries[normalized_title] = {
            "title": title,
            "video_id": video_id,
        }
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        pending = ledger_path.with_name(f"{ledger_path.name}.pending")
        pending.write_text(
            json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        pending.replace(ledger_path)


def _oauth_client_id(client_secrets_file: str) -> str:
    """Return the configured shared OAuth client ID without logging secrets."""
    try:
        with open(client_secrets_file, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Shared YouTube OAuth credentials are missing or invalid: "
            f"{client_secrets_file}"
        ) from error
    config = payload.get("installed") or payload.get("web") or {}
    client_id = str(config.get("client_id") or "")
    if not client_id:
        raise RuntimeError(
            f"Shared YouTube OAuth credentials have no client_id: "
            f"{client_secrets_file}"
        )
    return client_id


def _require_shared_client(
    creds,
    client_secrets_file: str,
    token_file: str,
    channel_name: str,
) -> None:
    """Reject legacy per-channel tokens before they contact Google."""
    expected_client_id = _oauth_client_id(client_secrets_file)
    actual_client_id = str(getattr(creds, "client_id", "") or "")
    if actual_client_id == expected_client_id:
        return
    slot_match = re.search(r"channel(\d+)", token_file, re.IGNORECASE)
    slot = slot_match.group(1) if slot_match else "<channel-number>"
    raise RuntimeError(
        f"{channel_name} still uses a legacy per-channel OAuth token. "
        "Google requires every channel to use the one shared OAuth project. "
        f"Run `python auth_tokens.py {slot}` locally and republish "
        f"CHANNEL{slot}_TOKEN_B64 before running this channel."
    )


def _get_authenticated_service(client_secrets_file: str, token_file: str, channel_name: str):
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)
        if creds:
            _require_shared_client(
                creds, client_secrets_file, token_file, channel_name
            )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print(f"[Uploader] Refreshing token for {channel_name}...")
            try:
                creds.refresh(Request())
            except RefreshError as error:
                if "disabled_client" in str(error).lower():
                    slot_match = re.search(r"channel(\d+)", token_file, re.IGNORECASE)
                    slot = slot_match.group(1) if slot_match else "N"
                    auth_command = (
                        f"python auth_tokens.py {slot}"
                        if slot != "N" else "python auth_tokens.py <channel-number>"
                    )
                    raise RuntimeError(
                        f"The shared YouTube OAuth client is disabled for {channel_name}. "
                        "Restore the one shared Google Cloud project through its "
                        "suspension appeal; do not create another per-channel project. "
                        f"Then run `{auth_command}` locally and republish "
                        f"CHANNEL{slot}_TOKEN_B64. "
                        "The completed Meta video job remains cached and will not "
                        "be regenerated."
                    ) from error
                raise
        else:
            print(f"\n{'='*60}")
            print(f"  ACTION REQUIRED: {channel_name}")
            print(f"  Switch to channel '{channel_name}' BEFORE clicking Allow")
            print(f"{'='*60}\n")
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)

    http = httplib2.Http(timeout=UPLOAD_HTTP_TIMEOUT)
    http.follow_redirects = False
    http.follow_all_redirects = False
    # Prevent httplib2 from treating redirects as followable requests (fixes
    # "Redirected but the response is missing a Location: header." crash).
    http.redirect_codes = frozenset()
    authed_http = AuthorizedHttp(creds, http=http)
    return build("youtube", "v3", http=authed_http, cache_discovery=False)


def _build_seo_description(title: str, script: str, tags: list, channel_name: str) -> str:
    """
    Builds a keyword-rich description optimized for YouTube search.
    YouTube uses the first 2-3 lines for search ranking and Shorts shelf preview.
    """
    # First line: restate the value proposition (YouTube shows this in search)
    first_line = title.replace(" #Shorts", "").strip()

    # Build hashtag block (YouTube indexes up to 60 hashtags, shows first 3 above title)
    hashtags_primary = ["#Shorts", "#YouTubeShorts"]
    hashtags_niche = [f"#{t.replace(' ', '').replace('#', '')}" for t in tags[:6]]
    hashtags_growth = ["#viral", "#trending", "#fyp"]
    all_hashtags = hashtags_primary + hashtags_niche + hashtags_growth

    # Extract 3-4 keyword phrases from the script for mid-description SEO
    words = script.split()
    # Take meaningful phrases from start and middle
    phrases = []
    if len(words) > 10:
        phrases.append(" ".join(words[0:8]))
    if len(words) > 40:
        phrases.append(" ".join(words[20:28]))

    description = f"""{first_line}

{" ".join(phrases[:1])}

{" ".join(all_hashtags)}

---
Like this? Follow {channel_name} for daily videos.
Turn on notifications so you never miss a post.

Tags: {", ".join(tags[:8])}
"""
    return description[:5000]


def upload_video(
    video_path: str,
    title: str,
    tags: list,
    channel_config: dict,
    description: str = "",
    script: str = "",
    source_url: str = "",
    media_credits: list[str] | None = None,
) -> str:
    """Uploads video with SEO-optimized metadata."""
    channel_name = channel_config["name"]
    category_id  = channel_config.get("category_id", "22")
    made_for_kids = bool(channel_config.get("made_for_kids", False))
    channel_id = str(channel_config.get("id") or channel_name)
    normalized_upload_title = _normalized_title(title)

    if channel_config.get("strict_upload_dedup", False):
        existing_video_id = _recorded_upload(channel_id, normalized_upload_title)
        if existing_video_id:
            print(
                f"[Uploader] Upload already recorded for {channel_name}; "
                f"reusing YouTube ID {existing_video_id}"
            )
            return existing_video_id
        print(
            "[Uploader] Local duplicate-title receipt check passed "
            "(zero YouTube read quota)"
        )

    youtube = _get_authenticated_service(
        channel_config["client_secrets_file"],
        channel_config["token_file"],
        channel_name,
    )

    if not description:
        description = _build_seo_description(title, script, tags, channel_name)
    suffix_sections = []
    if channel_config.get("media_source") == "meta_ai_browser":
        suffix_sections.append(
            "This Short contains original AI-generated scenes and native audio "
            "created with Meta AI; realistic scenes are illustrative reenactments, "
            "not authentic documentary footage."
        )
    if source_url:
        suffix_sections.append(f"Public record used for this episode:\n{source_url}")
    credits = list(dict.fromkeys(
        credit.strip() for credit in (media_credits or []) if credit.strip()
    ))
    if credits:
        suffix_sections.append(
            "Media sources and credits:\n" + "\n".join(f"- {credit}" for credit in credits)
        )
    if suffix_sections:
        suffix = "\n\n" + "\n\n".join(suffix_sections) + "\n"
        available = max(0, 5000 - len(suffix))
        description = description.rstrip()[:available].rstrip() + suffix

    # Clean tags: remove #, deduplicate, add algorithmic boosters
    clean_tags = []
    seen = set()
    for t in tags + ["Shorts", "short", channel_name]:
        clean = t.replace("#", "").strip()
        if clean.lower() not in seen and clean:
            seen.add(clean.lower())
            clean_tags.append(clean)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": clean_tags[:30],
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": made_for_kids,
            # API-supported disclosure of realistic synthetic content. All
            # channels transparently mark their Meta AI-generated Shorts.
            "containsSyntheticMedia": channel_config.get("media_source") == "meta_ai_browser",
            "embeddable": True,
            # madeShort signals to YouTube this is a Short (vertical ≤60s + #Shorts in title)
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5,
    )

    print(f"[Uploader] '{title}' -> {channel_name} (cat:{category_id})")

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    timeout_count = 0

    while response is None:
        try:
            status, response = request.next_chunk(num_retries=3)
            if status:
                print(f"[Uploader] {int(status.progress() * 100)}%...")
            timeout_count = 0
        except (socket.timeout, TimeoutError) as e:
            timeout_count += 1
            if timeout_count >= MAX_UPLOAD_TIMEOUTS:
                raise RuntimeError(
                    f"Upload timed out repeatedly for {channel_name}. "
                    f"Aborting after {MAX_UPLOAD_TIMEOUTS} timeouts."
                ) from e
            print(f"[Uploader] Timeout during upload ({timeout_count}/{MAX_UPLOAD_TIMEOUTS}), retrying...")
            time.sleep(2)

    video_id = str(response.get("id") or "")
    if not video_id:
        raise RuntimeError(f"YouTube returned no video ID for {channel_name}")
    if channel_config.get("strict_upload_dedup", False):
        _remember_upload(
            channel_id,
            normalized_upload_title,
            title,
            video_id,
        )
    print(f"[Uploader] Live: https://youtube.com/shorts/{video_id}")
    return video_id
