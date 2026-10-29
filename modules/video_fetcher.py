"""
video_fetcher.py (v7 — ranked real video, stills, and evidence capture)
Sources: Pexels, Pixabay, Coverr, Wikimedia Commons, curated Internet Archive,
NASA, Openverse, Art Institute of Chicago, and official-record screenshots.
Wikimedia videos use maintained HD transcodes for GitHub-hosted runners.
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
import shutil
import glob
import time
from urllib.parse import quote, urlparse
from config import PEXELS_API_KEY, PIXABAY_API_KEY, COVERR_API_KEY, TEMP_DIR, USED_VIDEOS_FILE


MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
MOTION_CLIP_SECONDS = 15
SEARCH_STOPWORDS = {
    "a", "an", "and", "at", "camera", "cinematic", "close", "dramatic",
    "case", "clue", "consequence", "decision", "digital", "discovers",
    "document", "documented", "evidence", "federal", "final", "follows",
    "for", "from", "handheld", "in", "investigation", "legal", "lighting",
    "makes", "medium", "mood", "of", "official", "on", "records", "shot",
    "the", "through", "to", "under", "urgent", "wide", "with",
}
ARCHIVE_SAFE_COLLECTIONS = "FedFlix OR prelinger"
ARCHIVE_BLOCKED_TERMS = {
    "explicit content", "porn", "sexual", "prank", "grounded severely",
    "gore", "graphic violence",
}
TRUSTED_RECORD_DOMAINS = (
    "justice.gov", "sec.gov", "ftc.gov", "cisa.gov", "fbi.gov",
)
HUMAN_QUERY_TERMS = {"woman", "man", "girl", "boy", "person", "professional", "employee"}
HUMAN_MEDIA_TERMS = HUMAN_QUERY_TERMS | {"people", "portrait", "female", "male", "lady"}
ANIMAL_MEDIA_TERMS = {"animal", "canine", "cat", "dog", "pet", "puppy"}
OPENVERSE_BLOCKED_TAGS = {
    "diaper", "fetish", "frenchmaid", "porn", "sissy", "sexual", "nude", "nudity",
}
VISUAL_OBJECT_TERMS = {
    "book", "camera", "computer", "door", "email", "file", "key", "letter",
    "monitor", "note", "phone", "radio", "receipt", "screen", "server",
    "terminal", "ticket", "watch",
}
APPEARANCE_TERMS = {
    "blazer", "braid", "coat", "glasses", "hair", "hoodie", "jacket",
    "raincoat", "scarf", "shirt", "suit", "uniform",
}
TECH_MEDIA_TERMS = (
    "ransomware", "cryptocurrency", "bitcoin", "malware", "cybersecurity",
    "cyber", "hacking", "computer", "technology", "data", "securities",
    "investment", "corporate", "fraud",
)


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


def _compact_api_query(query: str, maximum: int = 100) -> str:
    """Return a stock-library query that stays within provider limits."""
    compact = _archive_query(query).strip()
    if len(compact) <= maximum:
        return compact

    # Keep complete words where possible. A single unusually long token still
    # gets clipped so callers can rely on the hard character limit.
    shortened = compact[:maximum].rsplit(" ", 1)[0].strip()
    return shortened or compact[:maximum]


def _search_variants(query: str, beat_index: int = 0) -> list[str]:
    """Reduce cinematic prompts to concepts that media libraries can match."""
    keywords = _query_keywords(query, 16)
    if not keywords:
        return [query]
    broad_candidates = []
    if len(keywords) >= 4:
        broad_candidates.append(" ".join(keywords[:4]))
    if len(keywords) >= 3:
        broad_candidates.append(" ".join(keywords[-3:]))
    pairs = [
        " ".join(keywords[index:index + 2])
        for index in range(max(0, len(keywords) - 1))
    ]
    informative_pairs = [
        pair for pair in pairs
        if not (set(pair.split()) & HUMAN_QUERY_TERMS)
    ] or pairs
    if beat_index == 0:
        object_pairs = [
            pair for pair in informative_pairs
            if set(pair.split()) & VISUAL_OBJECT_TERMS
        ]
        non_overlapping = informative_pairs[::2]
        ordered_pairs = object_pairs + non_overlapping + informative_pairs[-2:]
    elif beat_index == 1:
        ordered_pairs = informative_pairs[-2:] + informative_pairs[
            len(informative_pairs) // 2:len(informative_pairs) // 2 + 2
        ]
    else:
        ordered_pairs = list(reversed(informative_pairs[-3:])) + informative_pairs[:1]
    candidates = ordered_pairs + broad_candidates
    seen = set()
    variants = []
    for candidate in candidates:
        normalized = candidate.casefold().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            variants.append(candidate)
    return variants[:4]


def _appearance_query(query: str) -> str:
    keywords = _query_keywords(query, 20)
    for index, word in enumerate(keywords):
        if word not in APPEARANCE_TERMS:
            continue
        start = max(0, index - 1)
        return " ".join(keywords[start:index + 1])
    return ""


def _tech_media_query(query: str, beat_index: int) -> str:
    if beat_index >= 2:
        return "federal courthouse"
    lowered = query.casefold()
    term = next((candidate for candidate in TECH_MEDIA_TERMS if candidate in lowered), "")
    if term in {"corporate", "fraud", "investment", "securities"}:
        return "corporate investigation"
    if term:
        return f"{term} computer"
    return "computer security analyst"


def _real_video_fallback_query(query: str, beat_index: int) -> str:
    """Return a broad, visible concept for key-free motion-footage search."""
    lowered = query.casefold()
    if beat_index >= 2 and any(
        term in lowered for term in ("courthouse", "legal consequence", "sentenced")
    ):
        return ""
    if any(term in lowered for term in ("train", "railway", "carriage")):
        return "train carriage interior" if beat_index == 1 else "train station night"
    if any(term in lowered for term in ("cryptocurrency", "bitcoin")):
        return "bitcoin computer"
    if any(term in lowered for term in ("cybercrime", "cyber", "hacking", "malware")):
        return "cybercrime computer"
    if any(term in lowered for term in ("server", "computer", "technology", "data")):
        return "computer server room"
    return ""


def _story_media_query(query: str, beat_index: int) -> str:
    """Translate prose-like story beats into literal library subjects."""
    lowered = query.casefold()
    if any(term in lowered for term in ("notebook", "writing", "writes")):
        return "hand writing notebook"
    if "phone" in lowered or "smartphone" in lowered:
        return "person smartphone"
    if "sunrise" in lowered or "sunset" in lowered:
        return "person sunrise silhouette"
    if any(term in lowered for term in ("train", "railway", "carriage")):
        return "night train carriage"
    return _search_variants(query, beat_index)[0]


def _media_matches_entities(item: dict, query: str) -> bool:
    """Reject obvious entity mismatches such as animals for a person query."""
    query_terms = set(_query_keywords(query, 20))
    searchable = " ".join(str(item.get(key, "")) for key in (
        "title", "description", "tags", "subject",
    )).casefold()
    media_terms = set(re.findall(r"[a-z]+", searchable))
    if query_terms & HUMAN_QUERY_TERMS and not media_terms & HUMAN_MEDIA_TERMS:
        return False
    if query_terms & HUMAN_QUERY_TERMS and media_terms & ANIMAL_MEDIA_TERMS:
        return False
    return True


def _relevance_score(item: dict, query: str) -> int:
    """Rank metadata overlap so a beat gets its closest available visual."""
    wanted = set(_query_keywords(query, 12))
    searchable = " ".join(str(item.get(key, "")) for key in (
        "title", "description", "tags", "subject",
    )).lower()
    found = set(re.findall(r"[a-z0-9$-]{3,}", searchable))
    overlap = len(wanted & found)
    title_found = set(re.findall(
        r"[a-z0-9$-]{3,}", str(item.get("title", "")).lower()
    ))
    title_overlap = len(wanted & title_found)
    phrase = _archive_query(query).lower()
    return overlap * 20 + title_overlap * 10 + (
        25 if phrase and phrase in searchable else 0
    )


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
                # Pixabay rejects search terms longer than 100 characters.
                # Visual prompts are prose, so reduce them to useful keywords
                # instead of sending camera and lighting directions verbatim.
                "q": _compact_api_query(query),
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
            "https://api.coverr.co/videos",
            headers={"Authorization": f"Bearer {COVERR_API_KEY}"},
            params={
                "query": _compact_api_query(query),
                "page_size": 15,
                "page": 0,
                "urls": "true",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        videos = data.get("hits", []) if isinstance(data, dict) else []
    except Exception as e:
        print(f"[Fetcher/Coverr] API error: {e}")
        return []

    for v in videos:
        if not isinstance(v, dict):
            continue
        vid = f"coverr_{v.get('id', hashlib.md5(str(v).encode()).hexdigest()[:8])}"
        if vid in used:
            continue

        url = None
        urls = v.get("urls") if isinstance(v.get("urls"), dict) else {}
        for key in ["mp4", "mp4_preview", "hd", "sd", "mobile"]:
            url = urls.get(key)
            if url:
                break
        url = url or v.get("url") or v.get("video_url")
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
WIKIMEDIA_UA   = (
    "YTShortsPipeline/2.0 "
    "(https://github.com/ahfirhack/ahfirhack; automated licensed-media fetch)"
)


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

        # Step 2: request Wikimedia's maintained transcodes. Originals can be
        # enormous; selecting an HD derivative is faster and more reliable on
        # a fresh GitHub Actions runner without sacrificing vertical quality.
        info_resp = requests.get(
            WIKIMEDIA_API,
            params={
                "action": "query",
                "titles": "|".join(titles[:10]),
                "prop": "videoinfo",
                "viprop": "url|size|mime|mediatype|extmetadata|derivatives",
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
            for ii in page.get("videoinfo", []):
                mime = ii.get("mime", "")
                if "video" not in mime and ii.get("mediatype") != "VIDEO":
                    continue
                derivatives = []
                duration = float(ii.get("duration") or 0)
                for derivative in ii.get("derivatives", []):
                    source = derivative.get("src")
                    width = int(derivative.get("width") or 0)
                    bandwidth = int(derivative.get("bandwidth") or 0)
                    estimated_size = bandwidth * duration / 8 if duration else 0
                    if (
                        source
                        and str(derivative.get("type", "")).startswith("video/")
                        and width >= 640
                        and (not estimated_size or estimated_size <= MAX_DOWNLOAD_BYTES)
                    ):
                        derivatives.append((width, source))
                derivatives.sort(reverse=True)
                original_size = int(ii.get("size") or 0)
                url = derivatives[0][1] if derivatives else (
                    ii.get("url") if original_size <= MAX_DOWNLOAD_BYTES else ""
                )
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
                    "duration": duration,
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
    """Fetch freely licensed Commons stills for cinematic motion treatment."""
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
                license_lower = license_name.lower()
                if (
                    not license_name
                    or any(term in license_lower for term in ("noncommercial", "no derivatives"))
                ):
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


def _fetch_openverse_images(
    query: str,
    num: int,
    used: set,
    beat_index: int = 0,
    search_override: str = "",
) -> list:
    """Fetch openly licensed photography through Openverse without a key."""
    results = []
    variants = [search_override] if search_override else _search_variants(query, beat_index)[:2]
    for variant in variants:
        try:
            response = requests.get(
                "https://api.openverse.org/v1/images/",
                params={
                    "q": variant,
                    "page_size": 12,
                    "mature": "false",
                    "license": "cc0,pdm,by,by-sa",
                },
                headers={"User-Agent": WIKIMEDIA_UA},
                timeout=10,
            )
            response.raise_for_status()
            for item in response.json().get("results", []):
                media_id = f"openverse_{item.get('id', '')}"
                image_url = str(item.get("url") or item.get("thumbnail") or "")
                if not item.get("id") or not image_url.startswith("http") or media_id in used:
                    continue
                license_name = str(item.get("license", "")).upper()
                creator = _metadata_text(item.get("creator", "Unknown creator"))
                title = _metadata_text(item.get("title", variant))
                tag_names = {
                    str(tag.get("name", "")).casefold()
                    for tag in (item.get("tags") or [])
                    if isinstance(tag, dict)
                }
                searchable_terms = set(re.findall(
                    r"[a-z]+", f"{title.casefold()} {' '.join(tag_names)}"
                ))
                query_terms = set(_query_keywords(variant, 20))
                original_query_terms = set(_query_keywords(query, 20))
                if (
                    (
                        (query_terms & HUMAN_QUERY_TERMS)
                        or (
                            (original_query_terms & HUMAN_QUERY_TERMS)
                            and (query_terms & APPEARANCE_TERMS)
                        )
                    )
                    and not (searchable_terms & HUMAN_MEDIA_TERMS)
                ):
                    continue
                if (original_query_terms & HUMAN_QUERY_TERMS) and (
                    searchable_terms & ANIMAL_MEDIA_TERMS
                ):
                    continue
                if searchable_terms & OPENVERSE_BLOCKED_TAGS:
                    continue
                landing_url = str(
                    item.get("foreign_landing_url")
                    or item.get("detail_url")
                    or "https://openverse.org/"
                )
                results.append({
                    "id": media_id,
                    "url": image_url,
                    "source": "openverse_motion",
                    "media_kind": "image",
                    "duration": MOTION_CLIP_SECONDS,
                    "title": title,
                    "description": _metadata_text(item.get("tags") or []),
                    "matched_query": variant,
                    "attribution": (
                        f"Openverse: {title} — {creator} ({license_name}): "
                        f"{landing_url}"
                    ),
                })
                if len(results) >= num:
                    return results
            if results:
                return results
        except Exception as error:
            print(f"[Fetcher/Openverse] '{variant}' failed: {error}")
    return results


def _fetch_artic_images(
    query: str,
    num: int,
    used: set,
    beat_index: int = 0,
) -> list:
    """Fetch public-domain artwork from the Art Institute of Chicago."""
    results = []
    for variant in _search_variants(query, beat_index)[:3]:
        try:
            response = requests.get(
                "https://api.artic.edu/api/v1/artworks/search",
                params={
                    "q": variant,
                    "limit": 15,
                    "fields": (
                        "id,title,artist_title,image_id,is_public_domain,thumbnail"
                    ),
                },
                headers={"AIC-User-Agent": WIKIMEDIA_UA},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            iiif_url = payload.get("config", {}).get(
                "iiif_url", "https://www.artic.edu/iiif/2"
            )
            for item in payload.get("data", []):
                if not item.get("is_public_domain") or not item.get("image_id"):
                    continue
                media_id = f"artic_{item['id']}"
                if media_id in used:
                    continue
                title = _metadata_text(item.get("title", variant))
                artist = _metadata_text(item.get("artist_title", "Unknown artist"))
                results.append({
                    "id": media_id,
                    "url": f"{iiif_url}/{item['image_id']}/full/1200,/0/default.jpg",
                    "source": "artic_motion",
                    "media_kind": "image",
                    "duration": MOTION_CLIP_SECONDS,
                    "title": title,
                    "description": _metadata_text(
                        (item.get("thumbnail") or {}).get("alt_text", "")
                    ),
                    "matched_query": variant,
                    "attribution": (
                        f"Art Institute of Chicago: {title} — {artist} "
                        f"(Public Domain): https://www.artic.edu/artworks/{item['id']}"
                    ),
                })
                if len(results) >= num:
                    return results
            if results:
                return results
        except Exception as error:
            print(f"[Fetcher/ArtIC] '{variant}' failed: {error}")
    return results


def _chromium_executable() -> str:
    configured = os.getenv("CHROME_PATH") or os.getenv(
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"
    )
    candidates = [
        configured,
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        shutil.which("msedge"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    candidates.extend(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"
    )))
    return next((path for path in candidates if path and os.path.exists(path)), "")


def _capture_official_record(source_url: str, output_path: str) -> bool:
    """Capture a trusted public-record page as real, case-specific evidence."""
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in TRUSTED_RECORD_DOMAINS
    ):
        return False
    browser = _chromium_executable()
    if not browser:
        print("[Fetcher/Evidence] Chromium unavailable; skipping record capture")
        return False
    try:
        result = subprocess.run(
            [
                browser,
                "--headless", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--hide-scrollbars",
                "--window-size=1080,1920", "--virtual-time-budget=7000",
                f"--screenshot={os.path.abspath(output_path)}", source_url,
            ],
            capture_output=True,
            text=True,
            timeout=75,
        )
        valid = (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 50_000
        )
        if not valid:
            print(f"[Fetcher/Evidence] Capture failed: {result.stderr[-300:]}")
        return valid
    except (OSError, subprocess.SubprocessError) as error:
        print(f"[Fetcher/Evidence] Capture failed: {error}")
        return False




# ── Download Helper ──────────────────────────────────────────
def _download_clip(url: str, dest: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").casefold()
        headers = {"User-Agent": WIKIMEDIA_UA}
        # The Art Institute's IIIF CDN permits automated open-access downloads
        # but its WAF rejects non-browser user agents unless the museum page is
        # supplied as referrer.
        if hostname == "artic.edu" or hostname.endswith(".artic.edu"):
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Referer": "https://www.artic.edu/",
            }
        r = None
        for attempt in range(3):
            r = requests.get(
                url,
                stream=True,
                headers=headers,
                timeout=120,
            )
            if r.status_code not in {429, 502, 503, 504}:
                break
            retry_after = min(float(r.headers.get("Retry-After") or 1), 8)
            r.close()
            time.sleep(retry_after * (attempt + 1))
        if r is None:
            return False
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


def _generate_motion_clip(
    image_path: str,
    output_path: str,
    beat_index: int = 0,
    document: bool = False,
) -> bool:
    """Turn licensed photography/art/evidence into a cinematic real-media clip."""
    frame_count = MOTION_CLIP_SECONDS * 30
    if document:
        motion = (
            f"zoompan=z='min(1+0.00014*on,1.06)':"
            "x='iw/2-(iw/zoom/2)':y='min((ih-ih/zoom)*0.20,ih-ih/zoom)':"
            f"d={frame_count}:s=720x1280:fps=30"
        )
        finish = "eq=contrast=1.06:saturation=0.92,unsharp=5:5:0.45"
    else:
        motions = (
            f"zoompan=z='min(1+0.00032*on,1.14)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frame_count}:s=720x1280:fps=30",
            f"zoompan=z=1.10:x='(iw-iw/zoom)*on/{frame_count}':"
            f"y='ih/2-(ih/zoom/2)':d={frame_count}:s=720x1280:fps=30",
            f"zoompan=z=1.10:x='(iw-iw/zoom)*(1-on/{frame_count})':"
            f"y='ih/2-(ih/zoom/2)':d={frame_count}:s=720x1280:fps=30",
        )
        motion = motions[beat_index % len(motions)]
        finish = (
            "eq=contrast=1.08:saturation=1.10:brightness=-0.015,"
            "unsharp=5:5:0.55,vignette=PI/5"
        )
    filter_graph = (
        "scale=900:1600:force_original_aspect_ratio=increase,"
        f"crop=900:1600,{motion},{finish},format=yuv420p"
    )
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-loop", "1",
            "-framerate", "1", "-i", image_path,
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


def _download_candidate(item: dict, destination: str, beat_index: int = 0) -> bool:
    if item.get("media_kind") != "image":
        return _download_clip(item["url"], destination)
    image_path = destination + ".source-image"
    try:
        if not _download_clip(item["url"], image_path):
            return False
        return _generate_motion_clip(image_path, destination, beat_index=beat_index)
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
    source_url: str = "",
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
    evidence_clip = ""

    if source_url:
        evidence_image = os.path.join(TEMP_DIR, "official_record.png")
        evidence_video = os.path.join(TEMP_DIR, "clip_0_official_record.mp4")
        if _capture_official_record(source_url, evidence_image) and _generate_motion_clip(
            evidence_image,
            evidence_video,
            beat_index=0,
            document=True,
        ):
            from modules.video_assembler import _visual_quality_ok

            if _visual_quality_ok(evidence_video):
                evidence_clip = evidence_video
                print("[Fetcher/Evidence] Official public-record visual ready")

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
            downloaded = os.path.exists(destination) or _download_candidate(
                item, destination, beat_index=beat_index
            )
            if downloaded:
                from modules.video_assembler import _visual_quality_ok

                if not _visual_quality_ok(destination):
                    print(
                        f"[Fetcher] Visual guard rejected {item['source']}; "
                        "trying the next source"
                    )
                    if os.path.exists(destination):
                        os.remove(destination)
                    continue
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
        if beat_index == 0 and evidence_clip:
            clip_paths.append(evidence_clip)
            chosen_sources.add("official_record")
            continue
        matches = [
            item for item in candidates
            if item.get("beat_query") == beat_query and item["id"] not in chosen_ids
        ]
        matches.sort(key=lambda item: item.get("relevance", 0), reverse=True)
        if download_first(matches, beat_index):
            continue

        niche_text = " ".join(niche_keywords or []).casefold()
        story_like = any(term in niche_text for term in ("story", "stoic", "philosophy"))
        motion_query = _real_video_fallback_query(beat_query, beat_index)
        # For character-led stories the hook still is often the only source
        # that preserves the protagonist's visible traits. Later beats favor
        # genuine motion whenever Commons has a relevant transcode.
        if motion_query and not (story_like and beat_index == 0):
            motion_options = _fetch_wikimedia(motion_query, 6, used)
            for item in motion_options:
                item["matched_query"] = motion_query
                item["relevance"] = _relevance_score(item, motion_query)
            motion_options = [
                item for item in motion_options if item["relevance"] >= 30
            ]
            motion_options.sort(
                key=lambda item: item.get("relevance", 0), reverse=True
            )
            if download_first(motion_options, beat_index):
                continue

        print(
            f"[Fetcher] No usable video for beat {beat_index + 1}; "
            "trying licensed photography and public-domain art..."
        )
        if story_like:
            stills = []
            appearance = _appearance_query(beat_query)
            if beat_index == 0 and appearance:
                stills.extend(_fetch_openverse_images(
                    beat_query, 3, used, beat_index, search_override=appearance
                ))
            concept = _story_media_query(beat_query, beat_index)
            commons = [
                item for item in _fetch_wikimedia_public_domain_images(
                    concept, 8, used
                )
                if _media_matches_entities(item, concept)
            ][:4]
            for item in commons:
                item["matched_query"] = concept
            stills.extend(commons)
            stills.extend(_fetch_artic_images(beat_query, 5, used, beat_index))
            if len(stills) < 3:
                stills.extend(_fetch_wikimedia_public_domain_images(
                    beat_query, 3 - len(stills), used
                ))
        else:
            stills = _fetch_wikimedia_public_domain_images(beat_query, 3, used)
            generic_query = _tech_media_query(beat_query, beat_index)
            generic_commons = _fetch_wikimedia_public_domain_images(
                generic_query, 4, used
            )
            for item in generic_commons:
                item["matched_query"] = generic_query
            stills.extend(generic_commons)
            if len(stills) < 3:
                stills.extend(_fetch_openverse_images(
                    beat_query,
                    4,
                    used,
                    beat_index,
                    search_override=generic_query,
                ))
            stills.extend(_fetch_nasa(beat_query, 2, used, "image"))
            if len(stills) < 3:
                stills.extend(_fetch_artic_images(
                    beat_query, 3 - len(stills), used, beat_index
                ))
        for item in stills:
            matched_query = item.get("matched_query", beat_query)
            item["relevance"] = _relevance_score(item, matched_query)
            if item["source"] == "artic_motion" and item["relevance"] == 0:
                item["relevance"] = 10
        stills.sort(key=lambda item: item.get("relevance", 0), reverse=True)
        if download_first(stills, beat_index):
            continue
        print(
            f"[Fetcher] Beat {beat_index + 1} has no acceptable real visual; "
            "synthetic color fallback is disabled."
        )

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
    required = min(3, num_clips)
    if len(clip_paths) < required:
        raise RuntimeError(
            f"Only {len(clip_paths)}/{required} narrative beats obtained real "
            "visuals. Upload stopped instead of creating a black or colored video."
        )
    if include_attributions:
        return clip_paths, attributions
    return clip_paths
