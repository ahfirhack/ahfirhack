"""Remove the audited low-view backlog from YouTube Channels 2 and 4.

This cleanup is deliberately bounded by exact authenticated channel IDs and an
audit timestamp. It cannot select Channel 3 or uploads created after the audit.
Candidates are rechecked on every run and are preserved once they have at least
300 views. Run without ``--execute`` for a read-only report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

from googleapiclient.errors import HttpError

from config import CHANNELS
from modules.uploader import _get_authenticated_service


VIEW_THRESHOLD = 300
AUDIT_CUTOFF_UTC = dt.datetime.fromisoformat("2026-10-28T22:01:52+00:00")
DEFAULT_MAX_DELETE_PER_CHANNEL = 90
TARGETS = {
    "channel_2": {
        "youtube_channel_id": "UC7hAw2AAMwxpEEWnCExd7Rw",
        "youtube_name": "The Unveiling",
    },
    "channel_4": {
        "youtube_channel_id": "UCg1JI8DonfCl3UYCbsys24g",
        "youtube_name": "SELF Improvement",
    },
}


def _published_at(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _quota_exhausted(error: HttpError) -> bool:
    if getattr(error.resp, "status", None) != 403:
        return False
    try:
        payload = json.loads(error.content.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return "quota" in str(error).lower()
    reasons = {
        item.get("reason", "")
        for item in payload.get("error", {}).get("errors", [])
        if isinstance(item, dict)
    }
    return bool(reasons & {"quotaExceeded", "dailyLimitExceeded"})


def _authenticated_channel(youtube, expected_id: str) -> dict:
    response = youtube.channels().list(
        part="snippet,contentDetails", mine=True, maxResults=1
    ).execute()
    items = response.get("items", [])
    if len(items) != 1:
        raise RuntimeError("Authenticated YouTube channel could not be resolved.")
    channel = items[0]
    if channel.get("id") != expected_id:
        raise RuntimeError(
            "Refusing cleanup: authenticated channel ID "
            f"{channel.get('id')} does not match expected ID {expected_id}."
        )
    return channel


def _upload_ids(youtube, uploads_playlist: str) -> list[str]:
    ids: list[str] = []
    page_token = None
    while True:
        response = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        ids.extend(
            item.get("contentDetails", {}).get("videoId", "")
            for item in response.get("items", [])
        )
        page_token = response.get("nextPageToken")
        if not page_token:
            return [video_id for video_id in ids if video_id]


def _videos(youtube, ids: list[str]) -> list[dict]:
    videos: list[dict] = []
    for offset in range(0, len(ids), 50):
        response = youtube.videos().list(
            part="snippet,statistics,status",
            id=",".join(ids[offset:offset + 50]),
            maxResults=50,
        ).execute()
        videos.extend(response.get("items", []))
    return videos


def _candidates(videos: list[dict]) -> tuple[list[dict], list[dict]]:
    delete: list[dict] = []
    preserve: list[dict] = []
    for video in videos:
        snippet = video.get("snippet", {})
        published = _published_at(snippet.get("publishedAt", "1970-01-01T00:00:00Z"))
        if published > AUDIT_CUTOFF_UTC:
            continue
        row = {
            "id": video["id"],
            "title": snippet.get("title", ""),
            "published": published,
            "views": int(video.get("statistics", {}).get("viewCount", 0)),
        }
        if row["views"] < VIEW_THRESHOLD:
            delete.append(row)
        else:
            preserve.append(row)
    # Oldest videos are removed first, giving newer uploads additional time to
    # cross the preservation threshold before a later quota-limited batch.
    delete.sort(key=lambda row: (row["published"], row["id"]))
    preserve.sort(key=lambda row: (-row["views"], row["id"]))
    return delete, preserve


def clean_channel(channel_id: str, *, execute: bool, max_delete: int) -> dict:
    target = TARGETS[channel_id]
    config = next(channel for channel in CHANNELS if channel["id"] == channel_id)
    youtube = _get_authenticated_service(
        config["client_secrets_file"], config["token_file"], config["name"]
    )
    identity = _authenticated_channel(youtube, target["youtube_channel_id"])
    actual_name = identity.get("snippet", {}).get("title", "")
    uploads = (
        identity.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )
    if not uploads:
        raise RuntimeError(f"Uploads playlist missing for {channel_id}.")

    videos = _videos(youtube, _upload_ids(youtube, uploads))
    candidates, preserved = _candidates(videos)
    print(
        f"[Cleanup] {channel_id}: {actual_name} ({identity['id']}) | "
        f"{len(candidates)} below {VIEW_THRESHOLD} | "
        f"{len(preserved)} preserved at {VIEW_THRESHOLD}+"
    )

    if not execute:
        print(f"[Cleanup] DRY RUN: would delete up to {min(max_delete, len(candidates))}")
        return {"channel": channel_id, "deleted": 0, "remaining": len(candidates)}

    deleted = 0
    quota_limited = False
    for video in candidates[:max_delete]:
        try:
            youtube.videos().delete(id=video["id"]).execute()
        except HttpError as error:
            if _quota_exhausted(error):
                quota_limited = True
                print(f"[Cleanup] {channel_id}: daily API quota reached; stopping safely")
                break
            raise
        deleted += 1
        print(
            f"[Cleanup] DELETED {channel_id} {video['id']} | "
            f"{video['views']} views | {video['title']}"
        )

    remaining = len(candidates) - deleted
    print(
        f"[Cleanup] {channel_id}: deleted {deleted}; estimated remaining "
        f"below threshold {remaining}; quota_limited={quota_limited}"
    )
    return {
        "channel": channel_id,
        "deleted": deleted,
        "remaining": remaining,
        "quota_limited": quota_limited,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete candidates. Without this flag the command is read-only.",
    )
    parser.add_argument(
        "--max-delete-per-channel",
        type=int,
        default=DEFAULT_MAX_DELETE_PER_CHANNEL,
    )
    parser.add_argument(
        "--channel",
        choices=("all", "channel_2", "channel_4"),
        default="all",
    )
    args = parser.parse_args()
    if not 1 <= args.max_delete_per_channel <= DEFAULT_MAX_DELETE_PER_CHANNEL:
        parser.error(
            f"--max-delete-per-channel must be between 1 and "
            f"{DEFAULT_MAX_DELETE_PER_CHANNEL}"
        )

    channels = list(TARGETS) if args.channel == "all" else [args.channel]
    results = [
        clean_channel(
            channel_id,
            execute=args.execute,
            max_delete=args.max_delete_per_channel,
        )
        for channel_id in channels
    ]
    print(
        "[Cleanup] TOTAL: "
        f"deleted={sum(result['deleted'] for result in results)} | "
        f"estimated_remaining={sum(result['remaining'] for result in results)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
