"""
video_fetcher.py (v4 — multi-source + dedup + topic-relevant queries)
Sources: Pexels, Pixabay, Coverr, Wikimedia Commons, Internet Archive
Dedup: tracks used video IDs in a JSON file so no clip repeats across runs.
"""

import requests
import os
import re
import json
import random
import hashlib
from config import PEXELS_API_KEY, PIXABAY_API_KEY, COVERR_API_KEY, TEMP_DIR, USED_VIDEOS_FILE


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


# ── Query Builder ────────────────────────────────────────────
def build_search_queries(primary_query: str, script: str = "", niche_keywords: list = None) -> list:
    """
    Generate 3-5 varied search queries from the primary query + script content.
    This ensures video clips actually match the topic instead of being generic.
    """
    queries = [primary_query]

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

        results.append({"id": vid, "url": url, "source": "coverr", "duration": v.get("duration", 0)})
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
                "iiprop": "url|size|mime|mediatype",
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

                vid = f"wiki_{hashlib.md5(url.encode()).hexdigest()[:12]}"
                if vid in used:
                    continue

                results.append({
                    "id": vid,
                    "url": url,
                    "source": "wikimedia",
                    "duration": 0,  # Wikimedia API doesn't return duration
                })
                if len(results) >= num:
                    return results

    except Exception as e:
        print(f"[Fetcher/Wikimedia] API error: {e}")

    return results




# ── Download Helper ──────────────────────────────────────────
def _download_clip(url: str, dest: str) -> bool:
    try:
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
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


# ── Main Entry Point ─────────────────────────────────────────
def fetch_video_clips(
    query: str,
    num_clips: int = 5,
    min_duration: int = 5,
    script: str = "",
    niche_keywords: list = None,
) -> list:
    """
    Fetches video clips from ALL sources, deduplicates, and downloads.
    Returns list of local file paths.

    Params:
        query          - primary search term from script_generator
        num_clips      - how many clips to download
        script         - full script text (used to build extra search queries)
        niche_keywords - channel keywords for fallback queries
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    used = _load_used()

    # Build multiple topic-relevant queries
    queries = build_search_queries(query, script, niche_keywords)
    print(f"[Fetcher] Queries: {queries}")

    # Collect candidates from ALL sources across ALL queries
    candidates = []
    seen_ids   = set()

    # Per-query, per-source — round-robin to maximize variety
    clips_per_source = max(num_clips // 3, 2)

    for q in queries:
        if len(candidates) >= num_clips * 3:
            break

        for fetcher, name in [
            (_fetch_pexels,    "Pexels"),
            (_fetch_pixabay,   "Pixabay"),
            (_fetch_coverr,    "Coverr"),
            (_fetch_wikimedia, "Wikimedia"),
        ]:
            try:
                batch = fetcher(q, clips_per_source, used)
                for item in batch:
                    if item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        candidates.append(item)
                if batch:
                    print(f"[Fetcher] {name} -> {len(batch)} clips for '{q}'")
            except Exception as e:
                print(f"[Fetcher] {name} failed for '{q}': {e}")

    # Shuffle to mix sources, then pick top N
    random.shuffle(candidates)
    selected = candidates[:num_clips]

    if not selected:
        print(f"[Fetcher] No clips found for any query. Trying bare niche keywords...")
        if niche_keywords:
            for kw in niche_keywords[:3]:
                batch = _fetch_pexels(kw, 3, used)
                batch += _fetch_pixabay(kw, 3, used)
                for item in batch:
                    if item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        selected.append(item)
                if len(selected) >= num_clips:
                    break
            selected = selected[:num_clips]

    # Download selected clips
    clip_paths = []
    for i, item in enumerate(selected):
        ext = ".mp4"
        if item["url"].endswith(".ogv"):
            ext = ".ogv"
        elif item["url"].endswith(".webm"):
            ext = ".webm"

        dest = os.path.join(TEMP_DIR, f"clip_{i}_{item['source']}_{item['id'][-8:]}{ext}")

        if os.path.exists(dest):
            clip_paths.append(dest)
            _mark_used(item["id"], used)
            continue

        print(f"[Fetcher] Downloading {i+1}/{len(selected)} from {item['source']}...")
        if _download_clip(item["url"], dest):
            clip_paths.append(dest)
            _mark_used(item["id"], used)
        else:
            print(f"[Fetcher] Skipped bad clip from {item['source']}")

    sources_used = set(item["source"] for item in selected if item["id"] in used)
    print(f"[Fetcher] Downloaded {len(clip_paths)} clips | Sources: {', '.join(sources_used)}")
    return clip_paths
