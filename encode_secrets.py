"""
encode_secrets.py — Encode credential files as base64 for GitHub Secrets.

Run this ONCE locally after running auth_tokens.py:
    python encode_secrets.py

Then copy each value into GitHub:
    Repo → Settings → Secrets and variables → Actions → New repository secret
"""

import base64
import os


FILES = {
    "CLIENT_SECRETS_B64":  "credentials/client_secrets.json",
    "CHANNEL1_TOKEN_B64":  "credentials/channel1_token.json",
    "CHANNEL2_TOKEN_B64":  "credentials/channel2_token.json",
    "CHANNEL3_TOKEN_B64":  "credentials/channel3_token.json",
    "CHANNEL4_TOKEN_B64":  "credentials/channel4_token.json",
}


def encode(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


print("\n" + "=" * 70)
print("  GitHub Secrets Encoder")
print("  Copy each value below into: Repo → Settings → Secrets → Actions")
print("=" * 70 + "\n")

missing = []
for secret_name, file_path in FILES.items():
    if not os.path.exists(file_path):
        missing.append((secret_name, file_path))
        continue
    value = encode(file_path)
    print(f"Secret name : {secret_name}")
    print(f"Secret value: {value}")
    print()

if missing:
    print("=" * 70)
    print("  MISSING FILES (run auth_tokens.py first):")
    for name, path in missing:
        print(f"  [{name}] → {path} not found")
    print("=" * 70)
