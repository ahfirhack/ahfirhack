"""
uploader.py (v3 — YouTube Algorithm Optimized 2026)
- SEO descriptions with keywords, hashtags, and CTA
- Proper category IDs per niche (not generic "22")
- Structured tags for search discovery
"""

import os
import pickle
import re
import socket
import time
import httplib2
from google.auth.transport.requests import Request
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

AUTH_HTTP_TIMEOUT = 30
UPLOAD_HTTP_TIMEOUT = 60
MAX_UPLOAD_TIMEOUTS = 4


def _normalized_title(title: str) -> str:
    """Normalize titles so '#Shorts' or punctuation cannot hide a duplicate."""
    without_shorts = re.sub(r"#?shorts?\b", " ", title, flags=re.IGNORECASE)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_shorts.lower()).split())


def _existing_upload_titles(youtube) -> set[str]:
    """Read every title already uploaded to the authenticated channel."""
    channel_response = youtube.channels().list(
        part="contentDetails", mine=True, maxResults=1
    ).execute()
    items = channel_response.get("items", [])
    if not items:
        raise RuntimeError("Could not resolve the authenticated YouTube channel.")

    uploads_playlist = (
        items[0].get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )
    if not uploads_playlist:
        raise RuntimeError("Could not resolve the channel uploads playlist.")

    titles: set[str] = set()
    page_token = None
    while True:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=page_token,
        )
        response = request.execute()
        for item in response.get("items", []):
            title = item.get("snippet", {}).get("title", "")
            normalized = _normalized_title(title)
            if normalized:
                titles.add(normalized)
        page_token = response.get("nextPageToken")
        if not page_token:
            return titles


def _get_authenticated_service(client_secrets_file: str, token_file: str, channel_name: str):
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print(f"[Uploader] Refreshing token for {channel_name}...")
            creds.refresh(Request())
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
) -> str:
    """Uploads video with SEO-optimized metadata."""
    channel_name = channel_config["name"]
    category_id  = channel_config.get("category_id", "22")
    made_for_kids = bool(channel_config.get("made_for_kids", False))

    youtube = _get_authenticated_service(
        channel_config["client_secrets_file"],
        channel_config["token_file"],
        channel_name,
    )

    if channel_config.get("strict_upload_dedup", False):
        normalized_upload_title = _normalized_title(title)
        existing_titles = _existing_upload_titles(youtube)
        if normalized_upload_title in existing_titles:
            raise RuntimeError(
                f"Duplicate YouTube title blocked for {channel_name}: {title}"
            )
        print(
            f"[Uploader] Duplicate-title preflight passed against "
            f"{len(existing_titles)} existing uploads"
        )

    if not description:
        description = _build_seo_description(title, script, tags, channel_name)

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

    video_id = response.get("id", "UNKNOWN")
    print(f"[Uploader] Live: https://youtube.com/shorts/{video_id}")
    return video_id
