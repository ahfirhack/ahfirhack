"""
auth_tokens.py — Generate YouTube OAuth tokens for each channel.
Run this ONCE per channel. Opens browser for Google login.
No video production, no uploading.

Usage:
    python auth_tokens.py            # all channels
    python auth_tokens.py 1          # channel_1 only
    python auth_tokens.py 1 3        # channel_1 and channel_3
"""

import os
import sys
import pickle
import google.auth.transport.requests
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

sys.path.insert(0, os.path.dirname(__file__))
from config import CHANNELS

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


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
        print(f"  Download it from Google Cloud Console -> Credentials -> OAuth 2.0 Client IDs")
        print(f"  Save it as: {secrets_file}")
        return False

    # Check if token already exists and is valid
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)

        if creds and creds.valid:
            # Verify by calling YouTube API
            try:
                youtube = build("youtube", "v3", credentials=creds)
                resp = youtube.channels().list(part="snippet", mine=True).execute()
                items = resp.get("items", [])
                if items:
                    ch_title = items[0]["snippet"]["title"]
                    print(f"\n  [OK] Token valid. Authenticated as: {ch_title}")
                    return True
            except Exception as e:
                print(f"\n  Token exists but verification failed: {e}")
                print(f"  Re-authenticating...")

        elif creds and creds.expired and creds.refresh_token:
            try:
                print(f"\n  Token expired. Refreshing...")
                creds.refresh(google.auth.transport.requests.Request())
                with open(token_file, "wb") as f:
                    pickle.dump(creds, f)
                print(f"  [OK] Token refreshed successfully.")
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
        creds = flow.run_local_server(port=0)

        with open(token_file, "wb") as f:
            pickle.dump(creds, f)

        # Verify
        youtube = build("youtube", "v3", credentials=creds)
        resp = youtube.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        if items:
            ch_title = items[0]["snippet"]["title"]
            print(f"  [OK] Token saved. Authenticated as: {ch_title}")
        else:
            print(f"  [OK] Token saved. (Could not verify channel name)")

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
        print(f"  1. credentials/channelN_secrets.json exists (from Google Cloud Console)")
        print(f"  2. YouTube Data API v3 is enabled in your Google Cloud project")
        print(f"  3. OAuth consent screen is configured")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
