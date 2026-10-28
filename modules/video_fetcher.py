"""
video_fetcher.py (v5 — ranked sources + exact-topic local fallback)
Sources: Pexels, Pixabay, Coverr, Wikimedia Commons, curated Internet Archive,
NASA, and local FFmpeg motion generation.
Dedup: tracks used video IDs in a JSON file so no clip repeats across runs.
"""

import requests
import os
import re
import json
import random
import hashlib
import html
import subprocess
from urllib.parse import quote
from config import PEXELS_API_KEY, PIXABAY_API_KEY, COVERR_API_KEY, TEMP_DIR, USED_VIDEOS_FILE


MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
MOTION_CLIP_SECONDS = 15
SEARCH_STOPWORDS = {
    "a", "an", "and", "at", "camera", "cinematic", "close", "dramatic",
    "for", "from", "in", "lighting", "medium", "mood", "of", "on", "shot",
    "the", "through", "to", "under", "wide", "with",
}
ARCHIVE_SAFE_COLLECTIONS = "FedFlix OR prelinger"
ARCHIVE_BLOCKED_TERMS = {
    "explicit content", "porn", "sexual", "prank", "grounded severely",
    "gore", "graphic violence",
}


def _load_used() -> set:
    if os.path.exists(USED_VIDEOS_FILE):
        try:
            with open(USED_VIDEOS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_used(used: set):
    with open(USED_VIDEOS_FILE, "w") as f:
        json.dump(list(used), f)


def _mark_used(video_id: str, used: set):
    used.add(str(video_id))
    _save_used(used)


def _query_keywords(query: str, maximum: int = 8) -> list[str]:
    words = [
        word.lower() for word in re.findall(r"[A-Za-z0-9$-]{3,}", query)
        if word.lower() not in SEARCH_STOPWORDS
    ]
    return list(dict.fromkeys(words))[:maximum]


def _archive_query(query: str) -> str:
    return " ".join(_query_keywords(query, 6)) or query


def _relevance_score(item: dict, query: str) -> int:
    """Rank metadata overlap so a beat gets its closest available visual."""
    wanted = set(_query_keywords(query, 12))
    searchable = " ".join(str(item.get(key, "")) for key in (
        "title", "description", "tags", "subject",
    )).lower()
    found = set(re.findall(r"[a-z0-9$-]{3,}", searchable))
    overlap = len(wanted & found)
    phrase = _archive_query(query).lower()
    return overlap * 20 + (25 if phrase and phrase in searchable else 0)


def _metadata_text(value: object) -> str:
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    cleaned = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return " ".join(cleaned.split())


# ── Query Builder ────────────────────────────────────────────
def build_search_queries(
    primary_query: str,
    script: str = "",
    niche_keywords: list = None,
    visual_queries: list | None = None,
) -> list:
    """
    Generate 3-5 varied search queries from the primary query + script content.
    This ensures video clips actually match the topic instead of being generic.
    """
    # AI-generated beat queries come first so the selected clips follow the
    # episode's hook -> escalation -> payoff order.
    queries = [
        str(query).strip()
        for query in (visual_queries or [])[:3]
        if isinstance(query, str) and len(query.split()) >= 3
    ]
    queries.append(primary_query)

    # Extract meaningful 2-3 word phrases from the script
    if script:
        # Remove filler words and extract noun phrases
        stop = {"the", "a", "an", "is", "are", "was", "were", "this", "that",
                "and", "or", "but", "for", "not", "you", "your", "our", "its",
                "with", "from", "will", "can", "has", "had", "have", "been",
                "just", "all", "more", "most", "them", "they", "than", "what",
                "when", "how", "who", "did", "does", "about", "every", "into",
                "here", "there", "like", "follow", "subscribe"}
        words = re.findall(r"[a-zA-Z]{3,}", script.lower())
        content_words = [w for w in words if w not in stop]

        # Build 2-word combos from first 60 content words (hook/core)
        top = content_words[:60]
        if len(top) >= 4:
            # Take pairs that are near each other in the text
            pairs = []
            for i in range(0, min(len(top) - 1, 20), 2):
                pair = f"{top[i]} {top[i+1]}"
                if pair != primary_query:
                    pairs.append(pair)
            random.shuffle(pairs)
            queries.extend(pairs[:3])

    # Add niche keywords as fallback queries
    if niche_keywords:
        for kw in niche_keywords[:2]:
            if kw.lower() not in primary_query.lower():
                queries.append(kw)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for q in queries:
        ql = q.lower().strip()
        if ql and ql not in seen:
            seen.add(ql)
            unique.append(q)

    return unique[:5]


# ── Source 1: Pexels ─────────────────────────────────────────
def _fetch_pexels(query: str, num: int, used: set) -> list:
    """Fetch portrait video clips from Pexels."""
    if not PEXELS_API_KEY:
        return []

    results = []
    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": 15, "orientation": "portrait", "size": "medium"},
            timeout=20,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
    except Exception as e:
        print(f"[Fetcher/Pexels] API error: {e}")
        return []

    for v in videos:
        vid = f"pexels_{v['id']}"
        if vid in used or v.get("duration", 0) < 5:
            continue

        files = v.get("video_files", [])
        portrait = [f for f in files if f.get("height", 0) > f.get("width", 0)]
        target = portrait if portrait else files
        target.sort(key=lambda f: abs(f.get("height", 0) - 1280))
        if not target:
            continue

        results.append({
            "id": vid,
            "url": target[0]["link"],
            "source": "pexels",
            "duration": v.get("duration", 0),
            "title": v.get("url", "").rsplit("/", 2)[-2].replace("-", " "),
            "description": v.get("url", ""),
            "attribution": (
                f"Pexels video by {v.get('user', {}).get('name', 'contributor')}: "
                f"{v.get('url', 'https://www.pexels.com/videos/')}"
            ),
        })
        if len(results) >= num:
            break

    return results


# ── Source 2: Pixabay ────────────────────────────────────────
def _fetch_pixabay(query: str, num: int, used: set) -> list:
    """Fetch video clips from Pixabay (key in config, was previously unused)."""
    if not PIXABAY_API_KEY:
        return []

    results = []
    try:
        resp = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "per_page": 15,
                "video_type": "film",
                "safesearch": "true",
            },
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
    except Exception as e:
        print(f"[Fetcher/Pixabay] API error: {e}")
        return []

    for v in hits:
        vid = f"pixabay_{v['id']}"
        if vid in used or v.get("duration", 0) < 5:
            continue

        vids = v.get("videos", {})
        # Prefer large → medium → small
        url = None
        for quality in ["large", "medium", "small"]:
            entry = vids.get(quality, {})
            if entry.get("url"):
                url = entry["url"]
                break
        if not url:
            continue

        results.append({
            "id": vid,
            "url": url,
            "source": "pixabay",
            "duration": v.get("duration", 0),
            "title": " ".join(v.get("tags", "").split(",")),
            "tags": v.get("tags", ""),
            "attribution": (
                f"Pixabay video by {v.get('user', 'contributor')}: "
                f"{v.get('pageURL', 'https://pixabay.com/videos/')}"
            ),
        })
        if len(results) >= num:
            break

    return results


# ── Source 3: Coverr ─────────────────────────────────────────
def _fetch_coverr(query: str, num: int, used: set) -> list:
    """Fetch video clips from Coverr (portrait-friendly, CC0)."""
    if not COVERR_API_KEY:
        return []

    results = []
    try:
        resp = requests.get(
            "https://coverr.co/api/videos",
            headers={"Authorization": f"Bearer {COVERR_API_KEY}"},
            params={"search": query, "per_page": 15, "page": 1},
            timeout=20,
        )
        resp.raise_for_status()
        data   = resp.json()
        videos = data.get("page", {}).get("videos", data.get("results", []))
    except Exception as e:
        print(f"[Fetcher/Coverr] API error: {e}")
        return []

    for v in videos:
        vid = f"coverr_{v.get('id', hashlib.md5(str(v).encode()).hexdigest()[:8])}"
        if vid in used:
            continue

        url = None
        for key in ["hd", "sd", "mobile", "url", "video_url"]:
            url = v.get("urls", {}).get(key) or v.get(key)
            if url:
                break
        if not url:
            continue

        results.append({
            "id": vid,
            "url": url,
            "source": "coverr",
            "duration": v.get("duration", 0),
            "title": v.get("title", v.get("name", "")),
            "description": v.get("description", ""),
            "attribution": f"Coverr: {v.get('title', v.get('name', vid))}",
        })
        if len(results) >= num:
            break

    return results


# ── Source 4: Wikimedia Commons (free, no API key) ───────────
WIKIMEDIA_API  = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_UA   = "YTShortsPipeline/1.0 (automated; free-license video)"


def _fetch_wikimedia(query: str, num: int, used: set) -> list:
    """
    Search Wikimedia Commons for CC-licensed video files.
    No API key required — only a User-Agent header.
    """
    results = []
    try:
        # Step 1: search for video files (namespace 6 = File:)
        search_resp = requests.get(
            WIKIMEDIA_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": f"{query} filetype:video",
                "srnamespace": "6",
                "srlimit": str(min(num * 3, 20)),
                "format": "json",
            },
            headers={"User-Agent": WIKIMEDIA_UA},
            timeout=15,
        )
        search_resp.raise_for_status()
        search_data = search_resp.json()
        titles = [s["title"] for s in search_data.get("query", {}).get("search", [])]

        if not titles:
            return []

        # Step 2: get direct download URLs via imageinfo
        info_resp = requests.get(
            WIKIMEDIA_API,
            params={
                "action": "query",
                "titles": "|".join(titles[:10]),
                "prop": "imageinfo",
                "iiprop": "url|size|mime|mediatype|extmetadata",
                "format": "json",
            },
            headers={"User-Agent": WIKIMEDIA_UA},
            timeout=15,
        )
        info_resp.raise_for_status()
        pages = info_resp.json().get("query", {}).get("pages", {})

        for page_id, page in pages.items():
            if page_id == "-1":
                continue
            for ii in page.get("imageinfo", []):
                mime = ii.get("mime", "")
                if "video" not in mime and ii.get("mediatype") != "VIDEO":
                    continue
                url = ii.get("url")
                if not url:
                    continue
                metadata = ii.get("extmetadata", {})
                license_name = metadata.get("LicenseShortName", {}).get("value", "")
                if not license_name or any(
                    blocked in license_name.lower()
                    for blocked in ("noncommercial", "no derivatives")
                ):
                    continue
                title = page.get("title", "").removeprefix("File:")
                artist = _metadata_text(metadata.get("Artist", {}).get("value", ""))
                credit_name = f"{title} — {artist}" if artist else title

                vid = f"wiki_{hashlib.md5(url.encode()).hexdigest()[:12]}"
                if vid in used:
                    continue

                results.append({
                    "id": vid,
                    "url": url,
                    "source": "wikimedia",
                    "duration": 0,  # Wikimedia API doesn't return duration
                    "title": title,
                    "description": _metadata_text(
                        metadata.get("ImageDescription", {}).get("value", "")
                    ),
                    "attribution": (
                        f"Wikimedia Commons: {credit_name} ({license_name}): "
                        f"{ii.get('descriptionurl', page.get('canonicalurl', 'https://commons.wikimedia.org/'))}"
                    ),
                })
                if len(results) >= num:
                    return results

    except Exception as e:
        print(f"[Fetcher/Wikimedia] API error: {e}")

    return results


def _fetch_internet_archive(query: str, num: int, used: set) -> list:
    """Fetch only public-domain/CC0 MP4 derivatives from Internet Archive."""
    results = []
    simple_query = _archive_query(query)
    try:
        response = requests.get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": (
                    f"({simple_query}) AND mediatype:movies AND "
                    f"collection:({ARCHIVE_SAFE_COLLECTIONS}) AND "
                    '(licenseurl:*publicdomain* OR licenseurl:*zero* OR rights:"Public Domain")'
                ),
                "fl[]": [
                    "identifier", "title", "description", "licenseurl",
                    "rights", "subject", "creator", "collection",
                ],
                "rows": max(num * 4, 8), "page": 1, "output": "json",
            },
            headers={"User-Agent": WIKIMEDIA_UA}, timeout=20,
        )
        response.raise_for_status()
        documents = response.json().get("response", {}).get("docs", [])
        documents.sort(key=lambda item: _relevance_score(item, simple_query), reverse=True)
        for document in documents:
            searchable = _metadata_text(
                f"{document.get('title', '')} {document.get('description', '')} "
                f"{document.get('subject', '')}"
            ).lower()
            if (
                _relevance_score(document, simple_query) < 60
                or any(term in searchable for term in ARCHIVE_BLOCKED_TERMS)
            ):
                continue
            identifier = str(document.get("identifier", ""))
            media_id = f"archive_{identifier}"
            if not identifier or media_id in used:
                continue
            metadata_response = requests.get(
                f"https://archive.org/metadata/{quote(identifier, safe='')}",
                headers={"User-Agent": WIKIMEDIA_UA}, timeout=20,
            )
            metadata_response.raise_for_status()
            files = metadata_response.json().get("files", [])
            mp4s = [
                item for item in files
                if str(item.get("name", "")).lower().endswith(".mp4")
                and "thumb" not in str(item.get("name", "")).lower()
            ]
            mp4s.sort(key=lambda item: (
                "512kb" not in str(item.get("format", "")).lower(),
                int(item.get("size") or MAX_DOWNLOAD_BYTES + 1),
            ))
            chosen = next(
                (item for item in mp4s if int(item.get("size") or 0) <= MAX_DOWNLOAD_BYTES),
                None,
            )
            if not chosen:
                continue
            file_name = str(chosen["name"])
            license_url = _metadata_text(
                document.get("licenseurl") or document.get("rights") or "Public Domain"
            )
            item_title = _metadata_text(document.get("title", identifier))
            creator = _metadata_text(document.get("creator", ""))
            credit_name = f"{item_title} — {creator}" if creator else item_title
            results.append({
                "id": media_id,
                "url": (
                    f"https://archive.org/download/{quote(identifier, safe='')}/"
                    f"{quote(file_name)}"
                ),
                "source": "internet_archive", "duration": 0,
                "title": item_title,
                "description": _metadata_text(document.get("description", "")),
                "subject": _metadata_text(document.get("subject", "")),
                "attribution": (
                    f"Internet Archive: {credit_name} ({license_url}): "
                    f"https://archive.org/details/{quote(identifier, safe='')}"
                ),
            })
            if len(results) >= num:
                break
    except Exception as error:
        print(f"[Fetcher/InternetArchive] API error: {error}")
    return results


def _nasa_assets(manifest_url: str) -> list[str]:
    response = requests.get(manifest_url, headers={"User-Agent": WIKIMEDIA_UA}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return [str(value).replace("http://", "https://", 1) for value in payload]
    return [
        str(item.get("href", "")).replace("http://", "https://", 1)
        for item in payload.get("collection", {}).get("items", [])
        if isinstance(item, dict) and item.get("href")
    ]


def _fetch_nasa(query: str, num: int, used: set, media_type: str = "video") -> list:
    """Fetch NASA library media; the returned credit is added at upload."""
    results = []
    try:
        response = requests.get(
            "https://images-api.nasa.gov/search",
            params={
                "q": _archive_query(query), "media_type": media_type,
                "page_size": max(num * 4, 8),
            },
            headers={"User-Agent": WIKIMEDIA_UA}, timeout=20,
        )
        response.raise_for_status()
        candidates = []
        for item in response.json().get("collection", {}).get("items", []):
            data = (item.get("data") or [{}])[0]
            nasa_id = str(data.get("nasa_id", ""))
            media_id = f"nasa_{media_type}_{nasa_id}"
            if not nasa_id or media_id in used or not item.get("href"):
                continue
            creator = _metadata_text(data.get("secondary_creator", ""))
            credit_note = f" (credit: {creator})" if creator else ""
            candidate = {
                "id": media_id, "source": "nasa", "duration": 0,
                "title": data.get("title", nasa_id),
                "description": data.get("description", ""),
                "tags": " ".join(data.get("keywords") or []),
                "attribution": (
                    f"NASA Image and Video Library{credit_note}: "
                    f"https://images.nasa.gov/details/{quote(nasa_id)}"
                ),
                "manifest_url": item["href"], "media_kind": media_type,
            }
            candidate["relevance"] = _relevance_score(candidate, query)
            candidates.append(candidate)
        candidates.sort(key=lambda item: item["relevance"], reverse=True)
        for candidate in candidates:
            assets = _nasa_assets(candidate.pop("manifest_url"))
            if media_type == "video":
                options = [url for url in assets if url.lower().split("?", 1)[0].endswith(".mp4")]
                preferred = next((url for url in options if "~medium.mp4" in url.lower()), None)
                preferred = preferred or next((url for url in options if "~mobile.mp4" in url.lower()), None)
                preferred = preferred or next((url for url in options if "~small.mp4" in url.lower()), None)
            else:
                options = [
                    url for url in assets
                    if url.lower().split("?", 1)[0].endswith((".jpg", ".jpeg", ".png"))
                ]
                preferred = next((url for url in options if "~large." in url.lower()), None)
                preferred = preferred or next((url for url in options if "~medium." in url.lower()), None)
                preferred = preferred or (options[0] if options else None)
            if preferred:
                candidate["url"] = preferred
                results.append(candidate)
            if len(results) >= num:
                break
    except Exception as error:
        print(f"[Fetcher/NASA] API error: {error}")
    return results


def _fetch_wikimedia_public_domain_images(query: str, num: int, used: set) -> list:
    """Fetch public-domain/CC0 stills for the local motion generator."""
    results = []
    try:
        search_response = requests.get(
            WIKIMEDIA_API,
            params={
                "action": "query", "list": "search", "srsearch": _archive_query(query),
                "srnamespace": "6", "srlimit": str(max(num * 5, 10)), "format": "json",
            },
            headers={"User-Agent": WIKIMEDIA_UA}, timeout=15,
        )
        search_response.raise_for_status()
        titles = [
            item["title"] for item in search_response.json().get("query", {}).get("search", [])
        ]
        if not titles:
            return []
        info_response = requests.get(
            WIKIMEDIA_API,
            params={
                "action": "query", "titles": "|".join(titles[:20]),
                "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "format": "json",
            },
            headers={"User-Agent": WIKIMEDIA_UA}, timeout=15,
        )
        info_response.raise_for_status()
        for page in info_response.json().get("query", {}).get("pages", {}).values():
            for info in page.get("imageinfo", []):
                metadata = info.get("extmetadata", {})
                license_name = metadata.get("LicenseShortName", {}).get("value", "")
                if not any(term in license_name.lower() for term in ("public domain", "cc0", "pdm")):
                    continue
                if info.get("mime") not in {"image/jpeg", "image/png", "image/webp"}:
                    continue
                url = info.get("url", "")
                title = page.get("title", "").removeprefix("File:")
                artist = _metadata_text(metadata.get("Artist", {}).get("value", ""))
                credit_name = f"{title} — {artist}" if artist else title
                media_id = f"wiki_image_{hashlib.md5(url.encode()).hexdigest()[:12]}"
                if not url or media_id in used:
                    continue
                results.append({
                    "id": media_id, "url": url, "source": "wikimedia_motion",
                    "media_kind": "image", "duration": MOTION_CLIP_SECONDS,
                    "title": title,
                    "description": _metadata_text(
                        metadata.get("ImageDescription", {}).get("value", "")
                    ),
                    "attribution": (
                        f"Wikimedia Commons: {credit_name} ({license_name}): "
                        f"{info.get('descriptionurl', 'https://commons.wikimedia.org/')}"
                    ),
                })
                if len(results) >= num:
                    return results
    except Exception as error:
        print(f"[Fetcher/WikimediaMotion] API error: {error}")
    return results




# ── Download Helper ──────────────────────────────────────────
def _download_clip(url: str, dest: str) -> bool:
    try:
        r = requests.get(
            url,
            stream=True,
            headers={"User-Agent": WIKIMEDIA_UA},
            timeout=120,
        )
        r.raise_for_status()
        content_length = int(r.headers.get("Content-Length") or 0)
        if content_length > MAX_DOWNLOAD_BYTES:
            print(f"[Fetcher] Skipped oversized media ({content_length} bytes)")
            return False
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                downloaded += len(chunk)
                if downloaded > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError("download exceeded safe size limit")
                f.write(chunk)
        # Verify file is not empty
        if os.path.getsize(dest) < 10000:
            os.remove(dest)
            return False
        return True
    except Exception as e:
        print(f"[Fetcher] Download failed: {e}")
        if os.path.exists(dest):
            os.remove(dest)
        return False


def _generate_motion_clip(image_path: str, output_path: str) -> bool:
    """Turn an exact-topic public-domain still into a vertical motion clip."""
    filter_graph = (
        "scale=720:1280:force_original_aspect_ratio=increase,"
        "crop=720:1280,"
        "zoompan=z='min(max(zoom,pzoom)+0.0007,1.12)':d=1:s=720x1280:fps=30,"
        "eq=contrast=1.04:saturation=1.06"
    )
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", image_path,
            "-vf", filter_graph, "-t", str(MOTION_CLIP_SECONDS), "-r", "30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an", output_path,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[Fetcher/Motion] Generation failed: {result.stderr[-400:]}")
        return False
    return os.path.getsize(output_path) > 10000


def _generate_topic_motion_clip(query: str, output_path: str, beat_index: int) -> bool:
    """Generate a free, exact-topic kinetic clip when no licensed media fits."""
    keywords = _query_keywords(query, 6) or ["story", "evidence", "revealed"]
    lines = [" ".join(keywords[index:index + 2]).upper() for index in range(0, len(keywords), 2)]
    topic_text = r"\n".join(lines[:3])
    labels = ("HOOK", "ESCALATION", "PAYOFF")
    label = labels[min(beat_index, len(labels) - 1)]
    palette = (
        ("0x06111f", "0x20d9ff"),
        ("0x170b25", "0xff3d81"),
        ("0x07190f", "0x55ff9a"),
    )
    background, accent = palette[beat_index % len(palette)]
    font = next((
        candidate for candidate in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ) if os.path.exists(candidate)
    ), "")
    font_option = f"fontfile='{font}':" if font else ""
    filter_graph = (
        f"noise=alls=9:allf=t+u,"
        f"drawgrid=w=90:h=90:t=2:c={accent}@0.13,"
        f"drawbox=x='mod(t*110,920)-200':y=0:w=200:h=1280:c={accent}@0.10:t=fill,"
        f"drawbox=x=56:y=170:w=608:h=8:c={accent}@0.95:t=fill,"
        f"drawtext={font_option}text='{label}':fontsize=38:fontcolor={accent}:"
        "x=58:y=102:box=1:boxcolor=black@0.35:boxborderw=12,"
        f"drawtext={font_option}text='{topic_text}':fontsize=62:fontcolor=white:"
        "line_spacing=24:x=(w-text_w)/2:y=(h-text_h)/2:"
        "borderw=3:bordercolor=black@0.8:box=1:boxcolor=black@0.38:boxborderw=24,"
        f"drawbox=x=56:y=1100:w=608:h=8:"
        f"c={accent}@0.95:t=fill,format=yuv420p"
    )
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i",
            f"color=c={background}:s=720x1280:r=30:d={MOTION_CLIP_SECONDS}",
            "-vf", filter_graph, "-t", str(MOTION_CLIP_SECONDS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", output_path,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[Fetcher/TopicMotion] Generation failed: {result.stderr[-400:]}")
        return False
    return os.path.getsize(output_path) > 10000


def _download_candidate(item: dict, destination: str) -> bool:
    if item.get("media_kind") != "image":
        return _download_clip(item["url"], destination)
    image_path = destination + ".source-image"
    try:
        if not _download_clip(item["url"], image_path):
            return False
        return _generate_motion_clip(image_path, destination)
    finally:
        if os.path.exists(image_path):
            os.remove(image_path)


# ── Main Entry Point ─────────────────────────────────────────
def fetch_video_clips(
    query: str,
    num_clips: int = 5,
    min_duration: int = 5,
    script: str = "",
    niche_keywords: list = None,
    visual_queries: list | None = None,
    include_attributions: bool = False,
) -> list | tuple[list, list]:
    """
    Fetches video clips from all sources, ranks them by topic overlap, and
    downloads them in hook -> escalation -> payoff order. With
    ``include_attributions=True``, returns ``(paths, source_credits)``.

    Params:
        query          - primary search term from script_generator
        num_clips      - how many clips to download
        script         - full script text (used to build extra search queries)
        niche_keywords - channel keywords for fallback queries
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    used = _load_used()

    # Build multiple topic-relevant queries
    queries = build_search_queries(query, script, niche_keywords, visual_queries)
    print(f"[Fetcher] Queries: {queries}")

    # Collect candidates from every source for the three narrative beats. The
    # generator supplies these in hook -> escalation -> payoff order.
    candidates = []
    seen_ids   = set()

    clips_per_source = max((num_clips + 2) // 3, 1)
    beat_queries = queries[:min(3, num_clips)]

    for q in beat_queries:
        for fetcher, name in [
            (_fetch_pexels,    "Pexels"),
            (_fetch_pixabay,   "Pixabay"),
            (_fetch_coverr,    "Coverr"),
            (_fetch_wikimedia, "Wikimedia"),
            (_fetch_internet_archive, "Internet Archive"),
            (lambda search, count, seen: _fetch_nasa(search, count, seen, "video"), "NASA"),
        ]:
            try:
                batch = fetcher(q, clips_per_source, used)
                for item in batch:
                    if item["id"] not in seen_ids:
                        item = dict(item)
                        item["beat_query"] = q
                        item["relevance"] = _relevance_score(item, q)
                        if item.get("source") in {
                            "wikimedia", "internet_archive", "nasa"
                        }:
                            minimum = 60 if len(_query_keywords(q)) >= 3 else 40
                            if item["relevance"] < minimum:
                                continue
                        seen_ids.add(item["id"])
                        candidates.append(item)
                if batch:
                    print(f"[Fetcher] {name} -> {len(batch)} clips for '{q}'")
            except Exception as e:
                print(f"[Fetcher] {name} failed for '{q}': {e}")

    # Download the best successful match for each beat. If no video survives,
    # turn an exact-topic public-domain still into a slow local motion clip.
    clip_paths = []
    attributions = []
    chosen_ids = set()
    chosen_sources = set()

    def download_first(options: list[dict], beat_index: int) -> bool:
        for item in options:
            if item["id"] in chosen_ids:
                continue
            destination = os.path.join(
                TEMP_DIR,
                f"clip_{beat_index}_{item['source']}_{item['id'][-8:]}.mp4",
            )
            print(
                f"[Fetcher] Beat {beat_index + 1}: trying {item['source']} "
                f"(relevance {item.get('relevance', 0)})..."
            )
            if os.path.exists(destination) or _download_candidate(item, destination):
                clip_paths.append(destination)
                chosen_ids.add(item["id"])
                chosen_sources.add(item["source"])
                credit = str(item.get("attribution", "")).strip()
                if credit and credit not in attributions:
                    attributions.append(credit)
                _mark_used(item["id"], used)
                return True
            print(f"[Fetcher] Skipped bad media from {item['source']}")
        return False

    for beat_index, beat_query in enumerate(beat_queries):
        matches = [
            item for item in candidates
            if item.get("beat_query") == beat_query and item["id"] not in chosen_ids
        ]
        matches.sort(key=lambda item: item.get("relevance", 0), reverse=True)
        if download_first(matches, beat_index):
            continue

        print(f"[Fetcher] No usable video for beat {beat_index + 1}; trying motion stills...")
        stills = _fetch_wikimedia_public_domain_images(beat_query, 2, used)
        if len(stills) < 2:
            stills.extend(_fetch_nasa(beat_query, 2 - len(stills), used, "image"))
        for item in stills:
            item["relevance"] = _relevance_score(item, beat_query)
        minimum_still_score = 60 if len(_query_keywords(beat_query)) >= 3 else 40
        stills = [
            item for item in stills
            if item.get("relevance", 0) >= minimum_still_score
        ]
        stills.sort(key=lambda item: item.get("relevance", 0), reverse=True)
        if download_first(stills, beat_index):
            continue

        destination = os.path.join(TEMP_DIR, f"clip_{beat_index}_topic_motion.mp4")
        print(
            f"[Fetcher] Beat {beat_index + 1}: generating exact-topic "
            "kinetic fallback locally..."
        )
        if _generate_topic_motion_clip(beat_query, destination, beat_index):
            clip_paths.append(destination)
            chosen_sources.add("local_topic_motion")

    # Callers asking for more than three clips retain the old fill behavior,
    # while the production channels request exactly three aligned beat clips.
    if num_clips > 3 and len(clip_paths) < num_clips:
        remaining = [item for item in candidates if item["id"] not in chosen_ids]
        remaining.sort(key=lambda item: item.get("relevance", 0), reverse=True)
        for item in remaining:
            if len(clip_paths) >= num_clips:
                break
            download_first([item], len(clip_paths))

    sources_used = chosen_sources
    print(f"[Fetcher] Downloaded {len(clip_paths)} clips | Sources: {', '.join(sources_used)}")
    if include_attributions:
        return clip_paths, attributions
    return clip_paths
