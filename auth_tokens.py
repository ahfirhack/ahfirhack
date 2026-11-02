"""
auth_tokens.py — Generate YouTube OAuth tokens for each channel.
All channels use one shared Google Cloud OAuth client and keep separate tokens.
Run this once per channel after creating/restoring that shared client.
No video production, no uploading.

Usage:
    python auth_tokens.py            # all channels
    python auth_tokens.py 1          # channel_1 only
    python auth_tokens.py 1 3        # channel_1 and channel_3
"""

import os
import sys
import pickle
import json
import google.auth.transport.requests
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

sys.path.insert(0, os.path.dirname(__file__))
from config import CHANNELS

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _oauth_client_id(secrets_file: str) -> str:
    try:
        with open(secrets_file, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Shared OAuth credentials are missing or invalid: {secrets_file}"
        ) from error
    config = payload.get("installed") or payload.get("web") or {}
    client_id = str(config.get("client_id") or "")
    if not client_id:
        raise RuntimeError(
            f"Shared OAuth credentials have no client_id: {secrets_file}"
        )
    return client_id


def _verified_channel(creds) -> dict:
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    response = youtube.channels().list(
        part="snippet", mine=True, maxResults=1
    ).execute()
    items = response.get("items", [])
    if len(items) != 1:
        raise RuntimeError("Authenticated YouTube channel could not be resolved.")
    return items[0]


def _title_matches(actual: str, expected: str) -> bool:
    return " ".join(actual.casefold().split()) == " ".join(expected.casefold().split())


def _identity_matches(identity: dict, channel: dict) -> bool:
    snippet = identity.get("snippet", {})
    actual_handle = str(snippet.get("customUrl") or "").lstrip("@").casefold()
    expected_handle = str(channel.get("handle") or "").lstrip("@").casefold()
    if actual_handle and expected_handle:
        return actual_handle == expected_handle
    return _title_matches(str(snippet.get("title") or ""), channel["name"])


def authenticate_channel(channel: dict):
    """Run OAuth flow for one channel. Saves token file."""
    name         = channel["name"]
    secrets_file = channel["client_secrets_file"]
    token_file   = channel["token_file"]

    print(f"\n{'='*60}")
    print(f"  Channel: {name}")
    print(f"  Secrets: {secrets_file}")
    print(f"  Token:   {token_file}")
    print(f"{'='*60}")

    # Check secrets file exists
    if not os.path.exists(secrets_file):
        print(f"\n  [SKIP] Client secrets file not found: {secrets_file}")
        print("  Download the ONE shared OAuth desktop client from Google Cloud Console")
        print(f"  Save it as: {secrets_file}")
        return False
    try:
        shared_client_id = _oauth_client_id(secrets_file)
    except RuntimeError as error:
        print(f"\n  [SKIP] {error}")
        return False

    # Check if token already exists and is valid
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)

        if str(getattr(creds, "client_id", "") or "") != shared_client_id:
            print("\n  Legacy per-channel token detected; re-authorizing with the shared client...")
            creds = None

        if creds and creds.valid:
            # Verify by calling YouTube API
            try:
                identity = _verified_channel(creds)
                ch_title = str(identity.get("snippet", {}).get("title") or "")
                if _identity_matches(identity, channel):
                    print(f"\n  [OK] Token valid. Authenticated as: {ch_title}")
                    return True
                print(
                    f"\n  Token belongs to '{ch_title}', not '{name}'; "
                    "re-authenticating..."
                )
                creds = None
            except Exception as e:
                print(f"\n  Token exists but verification failed: {e}")
                print(f"  Re-authenticating...")

        elif creds and creds.expired and creds.refresh_token:
            try:
                print(f"\n  Token expired. Refreshing...")
                creds.refresh(google.auth.transport.requests.Request())
                identity = _verified_channel(creds)
                ch_title = str(identity.get("snippet", {}).get("title") or "")
                if not _identity_matches(identity, channel):
                    raise RuntimeError(
                        f"Refreshed token belongs to '{ch_title}', not the "
                        f"configured handle {channel.get('handle')}."
                    )
                with open(token_file, "wb") as f:
                    pickle.dump(creds, f)
                print(f"  [OK] Token refreshed successfully for: {ch_title}")
                return True
            except Exception as e:
                print(f"\n  Refresh failed: {e}")
                print(f"  Re-authenticating from scratch...")

    # Run OAuth flow — opens browser
    os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)

    print(f"\n  BROWSER WILL OPEN — Follow these steps:")
    print(f"  1. Log into your Google account")
    print(f"  2. Switch to the YouTube channel: {name}")
    print(f"     (Click profile pic -> Switch account -> {name})")
    print(f"  3. Click 'Allow' to grant permissions")
    print(f"  4. Close the browser tab when done\n")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(secrets_file, SCOPES)
        creds = flow.run_local_server(
            port=0, prompt="consent", access_type="offline"
        )

        identity = _verified_channel(creds)
        ch_title = str(identity.get("snippet", {}).get("title") or "")
        if not _identity_matches(identity, channel):
            raise RuntimeError(
                f"Authorized '{ch_title}', but this token slot requires '{name}'. "
                "No token was saved; run again and choose the correct channel."
            )

        with open(token_file, "wb") as f:
            pickle.dump(creds, f)

        print(f"  [OK] Token saved. Authenticated as: {ch_title}")

        return True

    except Exception as e:
        print(f"\n  [FAIL] Authentication failed: {e}")
        return False


def main():
    # Parse channel filter from args
    target_ids = set()
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            target_ids.add(f"channel_{arg}")

    channels = CHANNELS
    if target_ids:
        channels = [c for c in CHANNELS if c["id"] in target_ids]
        if not channels:
            print(f"No channels found for IDs: {target_ids}")
            print(f"Available: {[c['id'] for c in CHANNELS]}")
            sys.exit(1)

    print(f"\n  YouTube Token Generator")
    print(f"  Channels to authenticate: {len(channels)}")
    for c in channels:
        print(f"    - {c['name']} ({c['id']})")

    results = []
    for channel in channels:
        ok = authenticate_channel(channel)
        results.append({"name": channel["name"], "id": channel["id"], "ok": ok})

    # Summary
    print(f"\n{'='*60}")
    print(f"  TOKEN SUMMARY")
    print(f"{'='*60}")
    for r in results:
        icon = "OK" if r["ok"] else "FAIL"
        print(f"  [{icon}] {r['name']} ({r['id']})")

    ok_count   = sum(1 for r in results if r["ok"])
    fail_count = sum(1 for r in results if not r["ok"])
    print(f"\n  Ready: {ok_count} | Need attention: {fail_count}")

    if fail_count:
        print(f"\n  For failed channels, make sure:")
        print("  1. credentials/youtube_shared_secrets.json exists")
        print(f"  2. YouTube Data API v3 is enabled in your Google Cloud project")
        print(f"  3. OAuth consent screen is configured")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
