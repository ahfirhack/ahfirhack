"""Switch the Meta AI login without mixing browser profiles or exposing cookies.

Run locally (not in GitHub Actions) and log into your own Meta account:
    python switch_meta_account.py --profile new-account

After successfully logging in, publish its session to the GitHub repository:
    python switch_meta_account.py --publish-only --repo OWNER/REPO

Or reuse the Meta account already signed in to your running Chrome (Chrome 144+):
    # In that Chrome profile, first enable chrome://inspect/#remote-debugging
    python switch_meta_account.py --from-open-chrome
    python switch_meta_account.py --publish-only --repo OWNER/REPO

No passwords, cookies, or GitHub tokens are printed or committed by this tool.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import tempfile
import uuid
from urllib.parse import urlsplit
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
PROFILE_ROOT = PROJECT_DIR / ".meta-ai-profile"  # already excluded by .gitignore
STATE_PATH = PROJECT_DIR / "meta_ai_storage_state.json"  # excluded by .gitignore
SECRET_NAME = "META_AI_STORAGE_STATE_B64"
MAX_ACCOUNT_SLOT = 5


def _slot_state_path(slot: int) -> Path:
    return (
        STATE_PATH if slot == 1 else
        PROJECT_DIR / f"meta_ai_storage_state_{slot}.json"
    )


def _slot_secret_name(slot: int) -> str:
    return SECRET_NAME if slot == 1 else f"META_AI_STORAGE_STATE_{slot}_B64"


def _validate_state(path: Path) -> bytes:
    if not path.is_file():
        raise RuntimeError(
            f"No saved Meta AI session at {path}. Log into the new account first."
        )
    data = path.read_bytes()
    try:
        state = json.loads(data)
    except (ValueError, UnicodeDecodeError) as error:
        raise RuntimeError("The Meta AI session file is not valid JSON.") from error
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list):
        raise RuntimeError("The Meta AI session file is not Playwright storage state.")
    if not state["cookies"]:
        raise RuntimeError("The saved session contains no browser cookies; login may have failed.")
    return data


# Limit the saved session to domains that can participate in Meta AI sign-in.
# Playwright CLI's state-save would otherwise include cookies from *other*
# websites in the user's personal Chrome profile; never publish those.
_ALLOWED_META_DOMAINS = (
    "meta.ai", "meta.com", "facebook.com", "fb.com",
    "instagram.com", "threads.net", "vibes.ai",
)


def _meta_hostname(value: str) -> bool:
    value = value.strip().lower().lstrip(".")
    return any(value == suffix or value.endswith("." + suffix)
               for suffix in _ALLOWED_META_DOMAINS)


def _meta_origin(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and _meta_hostname(parsed.hostname or "")


def _limited_meta_state(raw_path: Path) -> bytes:
    """Redact all non-Meta cookies/storage before using a personal profile."""
    try:
        state = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("Chrome did not export a valid browser session.") from error
    if not isinstance(state, dict):
        raise RuntimeError("Chrome returned an invalid session object.")
    cookies = state.get("cookies", [])
    origins = state.get("origins", [])
    if not isinstance(cookies, list) or not isinstance(origins, list):
        raise RuntimeError("Chrome returned invalid cookie/local-storage fields.")
    meta_cookies = [
        cookie for cookie in cookies
        if isinstance(cookie, dict) and _meta_hostname(str(cookie.get("domain", "")))
    ]
    meta_origins = [
        origin for origin in origins
        if isinstance(origin, dict) and _meta_origin(str(origin.get("origin", "")))
    ]
    if not meta_cookies:
        raise RuntimeError(
            "No Meta/Facebook/Instagram cookies were found in the attached "
            "Chrome profile. Confirm that meta.ai/create is signed in in "
            "THAT Chrome profile, then try again. The old session was preserved."
        )
    return json.dumps(
        {"cookies": meta_cookies, "origins": meta_origins},
        ensure_ascii=False, indent=2,
    ).encode("utf-8")


def _chrome_cli(args: list[str], *, seconds: int = 120) -> None:
    # When the repository runs under WSL but Chrome runs on Windows, the Linux
    # CLI cannot discover that Windows browser even though Chrome remote
    # debugging is enabled. Invoke the Windows CLI through WSL interop so both
    # processes live on the same OS side. Output stays captured because attach
    # can list unrelated personal tab titles.
    windows_bridge = (
        os.name != "nt"
        and bool(os.getenv("WSL_DISTRO_NAME"))
        and shutil.which("cmd.exe") is not None
    )
    cli = "playwright-cli.cmd" if windows_bridge else shutil.which("playwright-cli")
    if not cli:
        raise RuntimeError(
            "Playwright CLI is missing. In PowerShell (non-administrator), "
            "run: npm install -g @playwright/cli@latest"
        )
    command = (
        ["cmd.exe", "/d", "/s", "/c", cli, *args]
        if windows_bridge else [cli, *args]
    )
    try:
        result = subprocess.run(
            command, cwd=PROJECT_DIR, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            "Could not communicate with existing Chrome. In Chrome 144+, "
            "enable chrome://inspect/#remote-debugging and approve the "
            "connection prompt; keep Chrome open."
        ) from error
    if result.returncode:
        # Do not echo possibly sensitive Chrome tab titles, URLs or token-bearing
        # CLI diagnostic output into terminals or Actions logs.
        raise RuntimeError(
            "Playwright CLI could not attach to or read Chrome. Make sure "
            "you enabled chrome://inspect/#remote-debugging in the intended "
            "Chrome profile, approved any browser prompt, and are using "
            "an up-to-date Playwright CLI. Your previous session is intact."
        )


def _save_attached_meta_state(session_name: str, destination: Path) -> None:
    """Export cookies, localStorage and IndexedDB from attached Chrome.

    ``playwright-cli state-save`` currently calls ``storageState`` without its
    IndexedDB option. Meta AI can keep authentication/application state there,
    so a cookies-only export may open Vibes while meta.ai/create appears logged
    out. Run code inside the already-approved attached session and request the
    complete Playwright storage state. The caller immediately filters it down
    to Meta-owned origins before activating or publishing it.
    """
    # JSON string encoding is also valid JavaScript string encoding and avoids
    # path quoting bugs on both Windows and WSL. No cookie value or credential
    # is embedded in this command; only the temporary destination path is.
    destination_value = str(destination)
    if (os.name != "nt" and bool(os.getenv("WSL_DISTRO_NAME"))
            and shutil.which("wslpath") is not None):
        converted = subprocess.run(
            ["wslpath", "-w", destination_value], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if converted.returncode or not converted.stdout.strip():
            raise RuntimeError("Could not translate the temporary session path for Windows Chrome.")
        destination_value = converted.stdout.strip()
    destination_js = json.dumps(destination_value)
    code = (
        "async page => { await page.context().storageState({ path: "
        + destination_js
        + ", indexedDB: true }); }"
    )
    _chrome_cli([f"-s={session_name}", "run-code", code], seconds=120)


def _import_open_chrome(state_path: Path | None = None) -> None:
    """Import Meta-only login from Chrome *without relaunching Chrome*.

    Playwright CLI can attach by channel to a Chrome instance after the user
    explicitly turns on remote debugging in the currently running browser.
    This command never reads Chrome profile databases or changes its files.
    """
    state_path = state_path or STATE_PATH
    if os.name != "nt":
        print("[MetaAI] Chrome attachment is supported on macOS/Linux too if Playwright CLI finds Chrome.")
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    session_name = "ahfirhack-meta-" + uuid.uuid4().hex[:12]
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=".meta-only-import-", suffix=".json", dir=str(PROFILE_ROOT)
    )
    os.close(temp_fd)
    temp_path = Path(temp_name)
    pending_path = PROFILE_ROOT / f".{session_name}.filtered.json"
    attached = False
    try:
        print("[MetaAI] Attaching to your ALREADY OPEN Chrome window (no new Chrome profile).")
        print("[MetaAI] Make sure https://vibes.ai/ is signed in inside that Chrome profile.")
        print("[MetaAI] If Chrome asks permission, choose Allow on your own computer.")
        _chrome_cli([f"-s={session_name}", "attach", "--cdp=chrome"], seconds=180)
        attached = True
        # Load both allowed Meta creation origins in the attached profile before
        # exporting. Playwright can serialize an origin's localStorage/IndexedDB
        # only after that origin has been initialized in the browser context.
        # Command output is captured, so unrelated tab titles are never printed.
        _chrome_cli(
            [f"-s={session_name}", "tab-new", "https://meta.ai/create"],
            seconds=120,
        )
        _chrome_cli(
            [f"-s={session_name}", "tab-new", "https://vibes.ai/"],
            seconds=120,
        )
        _save_attached_meta_state(session_name, temp_path)
        filtered = _limited_meta_state(temp_path)
        parsed = json.loads(filtered)
        has_studio = any(str(c.get("domain", "")).lower().lstrip(".").endswith("vibes.ai")
                         for c in parsed.get("cookies", []))
        if not has_studio:
            print("[MetaAI] NOTE: No vibes.ai cookies were exported. "
                  "The dedicated Vibes Studio may require signing in there first.")
        pending_path.write_bytes(filtered)
        _validate_state(pending_path)
        pending_path.replace(state_path)
        print("[MetaAI] Imported only Meta/Facebook/Instagram session data.")
        print("[MetaAI] Other websites' cookies and storage were excluded.")
        print(f"[MetaAI] Saved new session: {state_path.name}")
        print("[MetaAI] Chrome remains open and your other Chrome tabs are untouched.")
    finally:
        # Delete unfiltered state immediately: it may temporarily include
        # unrelated Chrome logins. Do not commit, upload or share it.
        try:
            temp_path.unlink(missing_ok=True)
            pending_path.unlink(missing_ok=True)
        finally:
            if attached:
                try:
                    _chrome_cli([f"-s={session_name}", "detach"], seconds=30)
                except RuntimeError:
                    print("[MetaAI] Could not confirm detachment; Chrome itself was not closed.")


def _login(profile_name: str, reuse: bool,
           state_path: Path | None = None) -> None:
    state_path = state_path or STATE_PATH
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", profile_name):
        raise RuntimeError("Profile name must be 1–48 characters: letters, numbers, - or _.")
    profile_dir = PROFILE_ROOT / profile_name
    if profile_dir.is_dir() and any(profile_dir.iterdir()) and not reuse:
        raise RuntimeError(
            f"The profile '{profile_name}' already has browser data. Choose another "
            "--profile name for a fresh account, or use --reuse-profile to reopen "
            "this profile and log out/in manually."
        )

    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    pending_path = PROFILE_ROOT / f".{profile_name}.pending-session.json"
    if pending_path.exists():
        pending_path.unlink()

    # Set these before importing the browser module (config reads env at import).
    os.environ["META_AI_CHROME_PROFILE_DIR"] = str(profile_dir)
    os.environ["META_AI_STORAGE_STATE_FILE"] = str(pending_path)

    print(f"[MetaAI] Starting a separate browser profile: {profile_dir}")
    print("[MetaAI] In the browser, sign into the NEW Meta account.")
    print("[MetaAI] Complete any manual verification, then follow the login prompt.")
    from modules.meta_ai_generator import bootstrap_meta_login

    try:
        bootstrap_meta_login()
        _validate_state(pending_path)
        # Only replace the previously active session after successful editor verification.
        pending_path.replace(state_path)
    finally:
        if pending_path.exists():
            pending_path.unlink()

    print(f"[MetaAI] New local session activated: {state_path.name}")
    print("[MetaAI] Existing browser profiles are preserved.")


def _publish(repo: str, state_path: Path | None = None,
             secret_name: str | None = None) -> None:
    state_path = state_path or STATE_PATH
    secret_name = secret_name or SECRET_NAME
    if not repo or not re.fullmatch(r"(?:[\w.-]+/)?[\w.-]+/[\w.-]+", repo):
        raise RuntimeError(
            "For a safe, explicit destination, specify --repo OWNER/REPO "
            "(for example --repo myaccount/myvideos)."
        )
    if not shutil.which("gh"):
        raise RuntimeError(
            "GitHub CLI (gh) is not installed. Install it and run 'gh auth login', "
            "then retry --publish-only --repo OWNER/REPO."
        )

    session_data = _validate_state(state_path)
    # GitHub workflow expects a gzip-compressed, base64-encoded JSON storage state.
    secret_value = base64.b64encode(gzip.compress(session_data, mtime=0)).decode("ascii")
    command = [
        "gh", "secret", "set", secret_name,
        "--app", "actions", "--repo", repo,
    ]
    print(f"[GitHub] Updating Actions secret {secret_name} in {repo} ...")
    try:
        result = subprocess.run(
            command, input=secret_value, text=True, cwd=PROJECT_DIR,
            capture_output=True, timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("Unable to contact GitHub CLI to publish the secret.") from error
    if result.returncode != 0:
        raise RuntimeError(
            "GitHub rejected the secret update. Check 'gh auth status', "
            f"repository access and the repository name. {result.stderr.strip()}"
        )
    print("[GitHub] New Meta AI login session published successfully.")
    print("[GitHub] Future Actions runs will use the new account session.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sign into a new Meta AI browser profile and optionally update GitHub Actions."
    )
    parser.add_argument(
        "--from-open-chrome", action="store_true",
        help="Reuse Meta sign-in from your already-running regular Chrome (Chrome 144+).",
    )
    parser.add_argument(
        "--profile",
        help="Dedicated browser profile name (default: meta-account-SLOT).",
    )
    parser.add_argument(
        "--reuse-profile", action="store_true",
        help="Reopen an existing profile for reauthentication; log out first if necessary.",
    )
    parser.add_argument(
        "--publish", action="store_true",
        help="After successful login, update GitHub Actions secret in --repo.",
    )
    parser.add_argument(
        "--publish-only", action="store_true",
        help="Skip browser login and publish the currently saved session to --repo.",
    )
    parser.add_argument(
        "--repo", help="Exact GitHub destination as OWNER/REPO (required for publishing)."
    )
    parser.add_argument(
        "--slot", type=int, choices=range(1, MAX_ACCOUNT_SLOT + 1), default=1,
        help="Ordered Meta account slot; 1 is the primary account (default: 1).",
    )
    args = parser.parse_args()
    if args.publish and args.publish_only:
        parser.error("--publish and --publish-only are mutually exclusive")
    if args.from_open_chrome and args.publish_only:
        parser.error("--from-open-chrome and --publish-only are mutually exclusive")
    if args.from_open_chrome and args.reuse_profile:
        parser.error("--reuse-profile is only for the dedicated new-profile login")
    state_path = _slot_state_path(args.slot)
    secret_name = _slot_secret_name(args.slot)
    profile_name = args.profile or f"meta-account-{args.slot}"
    try:
        if args.from_open_chrome:
            _import_open_chrome(state_path)
        elif not args.publish_only:
            _login(profile_name, args.reuse_profile, state_path)
        if args.publish or args.publish_only:
            _publish(args.repo or "", state_path, secret_name)
        else:
            print(
                "[Next] To activate the new account in scheduled GitHub Actions, run:\n"
                "  python switch_meta_account.py --publish-only "
                f"--slot {args.slot} --repo OWNER/REPO"
            )
            print(f"[Next] Do not commit or share {state_path.name}.")
        return 0
    except (RuntimeError, OSError, KeyboardInterrupt) as error:
        print(f"[MetaAI] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
