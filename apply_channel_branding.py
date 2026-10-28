"""Apply safe YouTube branding fields for Channels 1, 2, and 4.

YouTube's Data API supports channel descriptions, keywords, and banners. It
does not support primary channel-name or profile-picture changes, so those two
fields remain a one-time YouTube Studio step. Run without ``--execute`` for a
read-only identity and asset check.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from config import CHANNELS
from modules.uploader import _get_authenticated_service


TARGETS = {
    "channel_1": "UC2qXBEvGGgoI0N_lJX1anYg",
    "channel_2": "UC7hAw2AAMwxpEEWnCExd7Rw",
    "channel_4": "UCg1JI8DonfCl3UYCbsys24g",
}

# Preserve only writable brandingSettings.channel properties. Sending the
# read-only ``title`` field causes channelTitleUpdateForbidden.
WRITABLE_CHANNEL_FIELDS = {
    "country",
    "defaultLanguage",
    "description",
    "keywords",
    "trackingAnalyticsAccountId",
    "unsubscribedTrailer",
}


def _config(channel_id: str) -> dict:
    return next(channel for channel in CHANNELS if channel["id"] == channel_id)


def _identity(youtube, expected_id: str) -> dict:
    response = youtube.channels().list(
        part="snippet,brandingSettings", mine=True, maxResults=1
    ).execute()
    items = response.get("items", [])
    if len(items) != 1 or items[0].get("id") != expected_id:
        actual_id = items[0].get("id") if items else "missing"
        raise RuntimeError(
            f"Refusing branding update: authenticated ID {actual_id} does not "
            f"match expected ID {expected_id}."
        )
    return items[0]


def apply_branding(channel_id: str, *, execute: bool) -> dict:
    config = _config(channel_id)
    banner = Path(config["banner_file"])
    logo = Path(config["logo_file"])
    if not banner.is_file() or not logo.is_file():
        raise FileNotFoundError(f"Brand assets missing for {channel_id}.")

    youtube = _get_authenticated_service(
        config["client_secrets_file"], config["token_file"], config["name"]
    )
    channel = _identity(youtube, TARGETS[channel_id])
    current_title = channel.get("snippet", {}).get("title", "")
    print(
        f"[Branding] {channel_id}: {current_title} ({channel['id']}) -> "
        f"{config['name']}"
    )
    print(f"[Branding] banner={banner} | logo={logo}")

    if not execute:
        print("[Branding] DRY RUN: banner and description are ready to apply")
        return {"channel": channel_id, "updated": False}

    banner_response = youtube.channelBanners().insert(
        media_body=MediaFileUpload(
            str(banner), mimetype="image/jpeg", resumable=False
        )
    ).execute()
    banner_url = banner_response.get("url")
    if not banner_url:
        raise RuntimeError(f"YouTube did not return a banner URL for {channel_id}.")

    existing_channel_settings = (
        channel.get("brandingSettings", {}).get("channel", {})
    )
    channel_settings = {
        key: value
        for key, value in existing_channel_settings.items()
        if key in WRITABLE_CHANNEL_FIELDS
    }
    channel_settings["description"] = config["description"]
    channel_settings["keywords"] = " ".join(config["keywords"])

    youtube.channels().update(
        part="brandingSettings",
        body={
            "id": channel["id"],
            "brandingSettings": {
                "channel": channel_settings,
                "image": {"bannerExternalUrl": banner_url},
            },
        },
    ).execute()
    print("[Branding] Applied banner, description, and keywords")
    print("[Branding] Name, handle, and logo still require YouTube Studio")
    return {"channel": channel_id, "updated": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--channel",
        choices=("all", "channel_1", "channel_2", "channel_4"),
        default="all",
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    selected = list(TARGETS) if args.channel == "all" else [args.channel]
    for channel_id in selected:
        apply_branding(channel_id, execute=args.execute)


if __name__ == "__main__":
    main()
