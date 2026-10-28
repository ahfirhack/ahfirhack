"""Build Channel 1's offline source pack from the official DOJ News API.

The output contains source facts, not generated claims. Runtime prompt seeding
turns each distinct public record into a compact Short while preserving the
record's stated legal status and URL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import html
import json
import re
import time
from pathlib import Path

import requests


API_URL = "https://www.justice.gov/api/v1/press_releases.json"
USER_AGENT = "SiliconCrimeFilesReserveBuilder/1.0 (official-record archive)"
TARGET_COUNT = 2048
TERMS = (
    "cyber",
    "ransomware",
    "cryptocurrency",
    "hacking",
    "malware",
    "data breach",
    "computer fraud",
    "digital asset",
    "business email compromise",
    "online fraud",
    "technology fraud",
    "securities fraud",
    "investment fraud",
    "corporate fraud",
    "wire fraud",
    "chief executive officer",
    "insider trading",
    "antitrust",
    "health care fraud",
)
EXCLUDED = (
    "child pornography",
    "child sexual",
    "sex trafficking",
    "human trafficking",
    "fentanyl",
    "methamphetamine",
    "cocaine",
    "drug trafficking",
    "firearm",
    "murder",
)
GENERIC_ENTITIES = {
    "department justice", "district judge", "justice department",
    "united states", "u s attorney", "attorney office", "federal court",
    "earlier today", "for immediate release", "grand jury",
}
STATUS_PATTERNS = (
    ("SENTENCED", r"\bsentenced\b|\bprison sentence\b"),
    ("CONVICTED", r"\bconvicted\b|\bfound guilty\b|\bjury verdict\b"),
    ("GUILTY PLEA", r"\bpleads? guilty\b|\bpleaded guilty\b|\bguilty plea\b"),
    ("CHARGED", r"\bcharged\b|\bindicted\b|\bindictment\b|\bcriminal complaint\b"),
    ("RESOLUTION", r"\bsettlement\b|\bsettles\b|\bagrees to pay\b|\bresolution\b"),
    ("ENFORCEMENT", r"\bseized\b|\bseizure\b|\bdismantled\b|\bdisrupted\b|\btakedown\b"),
    ("ARRESTED", r"\barrested\b|\bextradited\b"),
    ("CIVIL ACTION", r"\bsued\b|\bcivil complaint\b|\bfiles complaint\b"),
)


def _plain(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u00a0", " ").replace("\ufffd", "")
    return " ".join(text.split())


def _status(title: str) -> str | None:
    lowered = title.lower()
    for label, pattern in STATUS_PATTERNS:
        if re.search(pattern, lowered):
            return label
    return None


def _date_year(timestamp: object) -> tuple[str, int] | None:
    try:
        moment = dt.datetime.fromtimestamp(int(str(timestamp)), tz=dt.timezone.utc)
    except (ValueError, TypeError, OSError):
        return None
    if moment > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1):
        return None
    return moment.date().isoformat(), moment.year


def _compact_summary(row: dict) -> str:
    source = _plain(row.get("teaser"))
    if len(source.split()) < 18:
        source = _plain(row.get("body"))
    source = re.sub(r"^[A-Z][A-Z .,-]{2,35}\s+[–—-]\s+", "", source)
    sentences = re.split(r"(?<=[.!?])\s+", source)
    selected: list[str] = []
    word_count = 0
    for sentence in sentences:
        sentence = sentence.strip(" \"“”")
        if not sentence or sentence.startswith(("For Immediate Release", "Contact:")):
            continue
        words = sentence.split()
        if selected and word_count + len(words) > 70:
            break
        selected.append(sentence)
        word_count += len(words)
        if word_count >= 28:
            break
    summary = " ".join(selected)
    if len(summary.split()) > 70:
        summary = " ".join(summary.split()[:70]).rstrip(",;:") + "."
    return summary


def _record(row: dict) -> dict | None:
    title = _plain(row.get("title"))
    url = str(row.get("url") or "").replace("http://", "https://", 1)
    uuid = str(row.get("uuid") or "").strip()
    if not title or not uuid or not url.startswith("https://www.justice.gov/"):
        return None
    status = _status(title)
    dated = _date_year(row.get("date"))
    summary = _compact_summary(row)
    if not status or not dated or len(summary.split()) < 18:
        return None
    lowered = f"{title} {summary}".lower()
    if any(term in lowered for term in EXCLUDED):
        return None
    date, year = dated
    topics = [
        _plain(item.get("name")) for item in row.get("topic", [])
        if isinstance(item, dict) and item.get("name")
    ]
    components = [
        _plain(item.get("name")) for item in row.get("component", [])
        if isinstance(item, dict) and item.get("name")
    ]
    return {
        "uuid": uuid,
        "date": date,
        "year": year,
        "title": title,
        "summary": summary,
        "status": status,
        "topics": topics[:4],
        "components": components[:3],
        "url": url,
    }


def _case_key(record: dict) -> str:
    """Collapse same-day duplicate releases about the same named subject."""
    text = f"{record['title']} {record['summary'][:500]}"
    candidates = re.findall(
        r"\b(?:[A-Z][a-z'’-]+|[A-Z]{2,})"
        r"(?:\s+(?:[A-Z][a-z'’-]+|[A-Z]{2,})){1,3}\b",
        text,
    )
    for candidate in candidates:
        normalized = " ".join(re.findall(r"[a-z0-9]+", candidate.lower()))
        if normalized not in GENERIC_ENTITIES and not any(
            generic in normalized for generic in GENERIC_ENTITIES
        ):
            return f"{normalized}|{record['date']}|{record['status']}"
    keywords = [
        word for word in re.findall(r"[a-z0-9]+", record["title"].lower())
        if len(word) > 3 and word not in {"charged", "convicted", "sentenced", "former"}
    ]
    return f"{' '.join(keywords[:10])}|{record['date']}|{record['status']}"


def build(output: Path, target: int = TARGET_COUNT) -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    records: dict[str, dict] = {}
    fields = "date,title,url,uuid,teaser,body,topic,component"
    for term in TERMS:
        for page in range(40):
            response = session.get(
                API_URL,
                params={
                    "parameters[title]": term,
                    "sort": "date",
                    "direction": "DESC",
                    "pagesize": 50,
                    "page": page,
                    "fields": fields,
                },
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("results", [])
            if not rows:
                break
            for row in rows:
                record = _record(row)
                if record:
                    records.setdefault(record["uuid"], record)
            print(f"{term}: page {page + 1}, {len(records)} unique usable records")
            if len(records) >= target + 800:
                break
            total = int(payload.get("metadata", {}).get("resultset", {}).get("count", 0))
            if (page + 1) * 50 >= total:
                break
            time.sleep(0.28)
        if len(records) >= target + 800:
            break

    ordered = sorted(
        records.values(), key=lambda item: (item["date"], item["uuid"]), reverse=True
    )
    selected: list[dict] = []
    seen_cases: set[str] = set()
    for record in ordered:
        key = _case_key(record)
        if key in seen_cases:
            continue
        seen_cases.add(key)
        selected.append(record)
        if len(selected) == target:
            break
    if len(selected) < target:
        raise RuntimeError(
            f"Only {len(selected)} distinct official cases from {len(ordered)} "
            f"usable records; need {target}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8", compresslevel=9) as handle:
        json.dump(selected, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {len(selected)} official records to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/channel1_official_cases.json.gz"),
    )
    parser.add_argument("--target", type=int, default=TARGET_COUNT)
    args = parser.parse_args()
    build(args.output, args.target)
