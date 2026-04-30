"""
setup.py - One-time automated setup for 4-Channel YouTube Bot
Each channel has its own OAuth app (separate client_secrets file).
Opens browser 4 times — one login per channel.

What it does automatically:
  - OAuth login for all 4 channels using their own secrets
  - Encodes all credential files to base64
  - Pushes every secret + API key to GitHub
  - Bot runs forever after this
github apikey: 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
"""

import os, sys, json, base64, subprocess, time, pickle
import requests

# ─────────────────────────────────────────────
# FILL THESE IN (only 2 lines required)
# ─────────────────────────────────────────────
GITHUB_REPO    = "ahfirhack/ahfirhack"
GITHUB_PAT     = "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"

# ─────────────────────────────────────────────

CHANNELS = [
    {
        "id":      1,
        "name":    "Karma & Revenge Stories", # PIVOT: High Retention
        "secrets": "credentials/channel1_secrets.json",
        "token":   "credentials/channel1_token.json",
    },
    {
        "id":      2,
        "name":    "The History Mystery",      # PIVOT: Educational/Documentary
        "secrets": "credentials/channel2_secrets.json",
        "token":   "credentials/channel2_token.json",
    },
    {
        "id":      3,
        "name":    "Digital & Home Declutter", # PIVOT: Specific Utility
        "secrets": "credentials/channel3_secrets.json",
        "token":   "credentials/channel3_token.json",
    },
    {
        "id":      4,
        "name":    "The Modern Stoic",         # PIVOT: Men's Mental Health
        "secrets": "credentials/channel4_secrets.json",
        "token":   "credentials/channel4_token.json",
    },
]


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

GH_API     = "https://api.github.com/repos/" + GITHUB_REPO + "/actions/secrets"
GH_KEY_API = "https://api.github.com/repos/" + GITHUB_REPO + "/actions/secrets/public-key"
GH_HEADERS = {
    "Authorization": "Bearer " + GITHUB_PAT,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def check_requirements():
    try:
        __import__("nacl")
    except ImportError:
        print("[Setup] Installing packages...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "google-auth-oauthlib", "google-api-python-client",
            "google-auth-httplib2", "requests", "PyNaCl", "--quiet"
        ])
    print("[Setup] Dependencies ready")


def validate_config():
    errors = []
    if "YOUR_USERNAME" in GITHUB_REPO:
        errors.append("Set GITHUB_REPO at top of setup.py")
    if "YOUR_GITHUB_PAT" in GITHUB_PAT:
        errors.append("Set GITHUB_PAT at top of setup.py")
    for ch in CHANNELS:
        if not os.path.exists(ch["secrets"]):
            errors.append("Missing " + ch["secrets"] + " — place channel" + str(ch["id"]) + "_secrets.json in credentials/")
    if errors:
        print("\n[Setup] Fix these first:\n")
        for e in errors:
            print("  -> " + e)
        sys.exit(1)
    print("[Setup] Config valid — all 4 secrets files found")


def run_oauth_for_channel(ch: dict):
    from google_auth_oauthlib.flow import InstalledAppFlow

    ch_id   = ch["id"]
    name    = ch["name"]
    secrets = ch["secrets"]
    token_f = ch["token"]

    if os.path.exists(token_f):
        print(f"[OAuth] Channel {ch_id} ({name}): token exists, skipping")
        return

    print(f"\n{'='*55}")
    print(f"  CHANNEL {ch_id}: {name}")
    print(f"  Switch to the '{name}' YouTube account in your browser")
    print(f"{'='*55}")
    print(f"  Opening browser in 4 seconds...")
    time.sleep(4)

    flow  = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    with open(token_f, "wb") as f:
        pickle.dump(creds, f)

    print(f"[OAuth] Channel {ch_id} ({name}): token saved -> {token_f}")


def encode_file(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_repo_public_key():
    r = requests.get(GH_KEY_API, headers=GH_HEADERS)
    if r.status_code != 200:
        print("[GitHub] Cannot fetch public key: " + str(r.status_code))
        print(r.text)
        sys.exit(1)
    data = r.json()
    return data["key_id"], data["key"]


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    from nacl import encoding, public
    pk  = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    return base64.b64encode(box.encrypt(secret_value.encode())).decode("utf-8")


def push_secret(name: str, value: str, key_id: str, public_key: str):
    if not value or not value.strip():
        print("[GitHub] Skipped (empty): " + name)
        return
    encrypted = encrypt_secret(public_key, value)
    r = requests.put(
        GH_API + "/" + name,
        headers=GH_HEADERS,
        json={"encrypted_value": encrypted, "key_id": key_id},
    )
    if r.status_code in (201, 204):
        print("[GitHub] Secret set: " + name)
    else:
        print("[GitHub] FAILED " + name + ": " + str(r.status_code) + " " + r.text)


def read_api_keys_from_config() -> dict:
    import re
    keys = {}
    if not os.path.exists("config.py"):
        return keys
    with open("config.py", encoding='utf-8') as f:
        content = f.read()
    wanted = [
        "GROQ_API_KEY", "GEMINI_API_KEY", "CLAUDE_API_KEY",
        "ANTHROPIC_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY",
        "JAMENDO_CLIENT_ID", "FREESOUND_API_KEY", "REPLICATE_API_KEY",
        "YOUTUBE_API_KEY", "NOVA_API_KEY", "ELEVEMLABS_API_KEY", "DEEPGRAM_API_KEY", "COVERR_API_KEY", 
    ]
    for var in wanted:
        m = re.search(r'^\s*' + var + r'\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if m and m.group(1).strip():
            keys[var] = m.group(1).strip()
            print("[Config] Found " + var)
    return keys


def push_all_secrets():
    print("\n[GitHub] Fetching repo public key...")
    key_id, public_key = get_repo_public_key()

    all_secrets = {}

    # Each channel: encode its own secrets file + token
    for ch in CHANNELS:
        i = ch["id"]
        all_secrets[f"CHANNEL{i}_SECRETS_B64"] = encode_file(ch["secrets"])
        all_secrets[f"CHANNEL{i}_TOKEN_B64"]   = encode_file(ch["token"])

    # API keys from config.py
    api_keys = read_api_keys_from_config()
    all_secrets.update(api_keys)

    print("\n[GitHub] Pushing " + str(len(all_secrets)) + " secrets...\n")
    for name, value in all_secrets.items():
        push_secret(name, value, key_id, public_key)


def verify_secrets():
    print("\n[Verify] Checking secrets in GitHub...")
    r = requests.get(GH_API, headers=GH_HEADERS)
    if r.status_code != 200:
        print("[Verify] Cannot list secrets: " + str(r.status_code))
        return False
    names = [s["name"] for s in r.json().get("secrets", [])]
    required = []
    for ch in CHANNELS:
        i = ch["id"]
        required += [f"CHANNEL{i}_SECRETS_B64", f"CHANNEL{i}_TOKEN_B64"]
    all_ok = True
    for name in required:
        status = "OK" if name in names else "MISSING"
        if status == "MISSING":
            all_ok = False
        print("  [" + status + "] " + name)
    return all_ok


def main():
    print("\n" + "="*55)
    print("  4-CHANNEL YOUTUBE BOT - ONE-TIME SETUP")
    print("  (4 separate OAuth apps)")
    print("="*55 + "\n")

    check_requirements()
    validate_config()

    print("\nIMPORTANT - Publish all 4 OAuth apps to make tokens permanent:")
    print("  For EACH channel's Google Cloud project:")
    print("  APIs & Services -> OAuth consent screen -> Publish App")
    print("\nPress Enter when done (or Enter to skip for now)...")
    input()

    print("\n[OAuth] Logging in to 4 channels. Switch accounts each time.\n")
    os.makedirs("credentials", exist_ok=True)

    for ch in CHANNELS:
        run_oauth_for_channel(ch)
        if ch["id"] < len(CHANNELS):
            print("\n  Next channel in 3 seconds...\n")
            time.sleep(3)

    push_all_secrets()
    all_ok = verify_secrets()

    print("\n" + "="*55)
    print("  SETUP COMPLETE" + (" - All good" if all_ok else " - Check MISSING above"))
    print("="*55)
    print("\nNext steps:")
    print("  1. Make sure daily_upload.yml is in .github/workflows/")
    print("  2. git add .")
    print('  3. git commit -m "Add 4-channel YouTube bot"')
    print("  4. git push")
    print("  5. Repo -> Actions -> Daily YouTube Upload -> Run workflow")
    print("\nRuns daily at 3:00 UTC. 4 channels x 3 videos = 12 Shorts/day.\n")


if __name__ == "__main__":
    main()