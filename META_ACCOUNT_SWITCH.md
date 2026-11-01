# Reuse an existing, already-signed-in Chrome window (no new login)

**For Windows 11, Chrome 144 or newer, PowerShell (non-administrator).**

You can use the Meta AI account already open in your ordinary Chrome profile.
Chrome stays open and **your normal profile is not deleted or copied**.

1. In that same Chrome window/profile, open `chrome://inspect/#remote-debugging`.
   Turn on **Allow remote debugging for this browser instance**. This permits
   locally approved automation access to your browser; turn it off when done.
2. Visit `https://meta.ai/create`, verify that the correct Meta account is
   signed in and its Create page works, and leave Chrome open.
3. Ensure Node.js/npm is installed. In PowerShell, inside `ahfirhack-main`,
   install the official Playwright CLI once:

   ```powershell
   npm install -g @playwright/cli@latest
   ```

4. Import only Meta-related cookies and local storage from the **running**
   Chrome instance, not from a new Chrome window:

   ```powershell
   python switch_meta_account.py --from-open-chrome
   ```

   Approve the connection in Chrome when prompted. If successful, the script
   saves `meta_ai_storage_state.json` without showing cookie values. It captures
   cookies, local storage and IndexedDB, then filters out every non-Meta cookie
   and origin before activating the session. IndexedDB matters because a
   cookies-only export can leave `meta.ai/create` logged out even when Vibes
   opens successfully.
   You can verify success without displaying secrets:

   ```powershell
   Test-Path .\meta_ai_storage_state.json
   ```

5. If your automation runs on GitHub Actions, publish the saved Meta login:

   ```powershell
   gh auth login
   python switch_meta_account.py --publish-only --repo OWNER/REPO
   ```

   Or combine import and publish into one command when GitHub CLI is already
   authenticated:

   ```powershell
   python switch_meta_account.py --from-open-chrome --publish --repo OWNER/REPO
   ```

## Configure four ordered Meta accounts

Account slot 1 is always the primary account. Slots 2, 3 and 4 are isolated
fallbacks used only when an earlier account is signed out, quota-limited,
ineligible or unavailable. Cookies and storage are never merged between slots.

For each additional account, sign into that account in regular Chrome, enable
remote debugging temporarily, then import and publish its numbered slot:

```powershell
# Current primary account (already configured)
python switch_meta_account.py --from-open-chrome --slot 1 --publish --repo OWNER/REPO

# Repeat after switching regular Chrome to each different Meta account
python switch_meta_account.py --from-open-chrome --slot 2 --publish --repo OWNER/REPO
python switch_meta_account.py --from-open-chrome --slot 3 --publish --repo OWNER/REPO
python switch_meta_account.py --from-open-chrome --slot 4 --publish --repo OWNER/REPO
```

The local files are `meta_ai_storage_state.json` (primary), then
`meta_ai_storage_state_2.json` through `_4.json`. GitHub stores them as
`META_AI_STORAGE_STATE_B64`, then `META_AI_STORAGE_STATE_2_B64` through `_4_B64`.
All are ignored by Git. A rendered-but-undownloaded scene never fails over,
because generating it again on another account would spend quota and duplicate
the remote render.

**Important limitations**

- Chrome must already be signed in; this does not bypass login, challenges,
  feature restrictions, or session expiry.
- `--from-open-chrome` uses the browser you already have open for **session
  import**. GitHub-hosted jobs cannot directly drive a browser on your PC.
  They use the imported Meta-only session via the Actions secret.
- Connecting to Chrome exposes browser data to the automation client while
  attached. Run only code you trust and disable remote debugging afterward.
- The CLI's temporary raw state may briefly include logins from other sites.
  The script stores it under the ignored local `.meta-ai-profile/` directory,
  deletes it immediately, and filters it *before* creating the active session
  or publishing anything to GitHub. Do not upload this folder or any session
  JSON files.
- On Chrome versions without this opt-in remote-debugging capability, use
  the separate `--profile new-account` flow described below.
- Importing stored session data is not guaranteed to authenticate a GitHub
  runner: some services restrict session portability. Verify with a test run.
- Never publish session JSON files to a Git repository, attach them to a chat,
  or send them to anyone. They are active login credentials.

---

# Switching Meta AI to a new account

This project uses separate login artifacts for every configured account:

- Local Playwright Chrome profile: controls the browser used to sign in interactively.
- An ordered `META_AI_STORAGE_STATE[_2..4]_B64` GitHub Actions secret for each saved session on fresh runners.

**Changing the local browser alone is not sufficient.** Update the secret so scheduled jobs use the new account. The YouTube OAuth tokens do **not** need to be changed.

## On Windows 11 (PowerShell, non-administrator)

Open PowerShell in the extracted project directory. Install requirements once (within your normal Python environment or an activated virtual environment):

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Open a **brand-new, isolated Chrome/Chromium profile** and log into the new Meta account:

```powershell
python switch_meta_account.py --profile new-account
```

1. In the browser window, go through Meta's login and any security verification **manually**.
2. Make sure `https://meta.ai/create` is showing the prompt editor for the intended account.
3. Return to PowerShell and press **Enter** when prompted. The code verifies the editor before replacing the local saved session.
4. **Do not upload or share** `meta_ai_storage_state.json`, the browser-profile directory, or encoded secret values. These contain live login credentials.

The former browser data is preserved. To create another totally fresh account session later, run `--profile another-new-account` instead. If your first attempt ended with **"prompt editor was not available"**, the browser profile still exists; recover it with `python switch_meta_account.py --profile new-account --reuse-profile`. The fixed login code checks a fresh tab after account sign-in and can retry verification up to three times. It keeps the old exported session if all checks fail.

## Activate the new login in GitHub Actions

Install [GitHub CLI](https://cli.github.com/), authenticate with your GitHub account using `gh auth login`, and provide your **exact** repository owner and name:

```powershell
python switch_meta_account.py --publish-only --repo OWNER/REPO
```

Or, for new attempts, sign in and publish in one step:

```powershell
python switch_meta_account.py --profile another-new-account --publish --repo OWNER/REPO
```

The script passes a gzip+base64-encoded session directly to `gh secret set` via standard input. It does **not** print the secret, put it in the command line, or commit it to Git. The repository workflow reads the primary `META_AI_STORAGE_STATE_B64` and optional numbered secrets `META_AI_STORAGE_STATE_2_B64` through `_4_B64`; no workflow changes are necessary.

You can confirm the secret exists under **GitHub repository → Settings → Secrets and variables → Actions**. GitHub will not show the secret's value.

## Windows alternatives / WSL

On WSL Ubuntu, use the same commands with `python3` and your configured Python virtual environment. For the browser to show, WSL requires desktop GUI support (WSLg or a graphical session). If that is unavailable, run the local login command in Windows PowerShell, then publish using GitHub CLI from Windows.

## Troubleshooting

- **Old Meta account remains signed in:** Choose a different `--profile` name; this avoids all previous browser cookies. `--reuse-profile` is for intentionally reopening an existing profile, and may require manually signing out.
- **Chromium executable not installed:** Run `python -m playwright install chromium`.
- **Meta editor not available:** Complete security verification, confirm the new account is the one displayed, and check that the Meta AI Create prompt editor is available. This version opens a fresh verification tab after sign-in (to avoid checking a stale login tab), and allows another check without losing the browser profile. A failed check saves a local `meta_ai_debug_login.png` screenshot under `.meta-ai-profile/` for your inspection; it may contain personal account information, so do not upload or share it unchanged. The script will not overwrite the active session unless verification passes.
- **GitHub secret publish fails:** Run `gh auth status` and verify your `--repo OWNER/REPO` and permission to modify its Actions secrets. Your local new session remains saved, so `--publish-only` can be retried without logging in again.
- **Future Actions runs still ask for login:** Re-export by running with `--reuse-profile`, then `--publish-only`. Session validity can expire; if the intended new account is restricted or does not support Create, switching profile cannot bypass that.

The project has **not** been remotely authenticated by preparing this archive. Account login and GitHub publication are actions you must complete on your own authorized machine and repository.
