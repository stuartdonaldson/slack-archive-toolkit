# OPERATIONS — Slack Archive Toolkit

Operational procedures, failure modes, and recurring maintenance for running the
toolkit. For architecture see [DESIGN.md](DESIGN.md); for first-time setup see
[README.md](../README.md) "Getting Started"; for slackdump-specific behaviour see
[references/slackdump-cli-notes.md](references/slackdump-cli-notes.md).

---

## Authorization / Session Lifecycle

This is the operation that needs the most recurring attention, because Slack sessions
**expire** and every backup depends on them.

### Auth model

The toolkit authenticates to Slack as **you**, using a browser session (`xoxc-` client
token + `xoxd-` `d` cookie) — **not** a bot or app token. Consequences:

- **No Slack admin rights and no app install are required** — you only need to be a
  logged-in member of each workspace.
- **Sessions expire** (Slack's schedule, or on password change / sign-out). When they
  do, `slackdump` calls fail with `authentication details expired, relogin is
  necessary`. This is expected and periodic, not a bug.
- **Re-auth is inherently interactive.** slackdump's automated re-login (*EZ-Login
  3000*) is **not supported on this OS** (headless Linux/WSL2) — and even where it runs,
  Slack login requires a human (password / SSO / 2FA). A machine cannot silently
  re-authenticate; a person must complete the login once per expiry. (A durable bot/app
  token would avoid this but requires per-workspace app install/admin approval — a
  deliberate tradeoff not taken; see the decision discussion in bd `SlackBackup-fac`.)

### Where the secrets live

| Secret | Location | Persisted? |
|--------|----------|-----------|
| `xoxc-` tokens (per workspace) | `~/.slackdump-tokens.json` (`{workspace: token}`) | Yes (on disk, in `$HOME`) |
| slackdump session (`.bin`) | `~/.cache/slackdump/<workspace>.bin` | Yes (slackdump's own store) |
| `xoxd-` `d` cookie | passed inline to slackdump at register time | **No** — never written by this project (it's sensitive and short-lived) |

None of these ever belong in the repo — see `.gitignore`'s "Secrets" section.

### 1. Initial registration

First-time setup for a workspace is documented in [README.md](../README.md) "Getting
Started" §1–2: capture token + cookie from the browser, merge tokens into
`~/.slackdump-tokens.json`, then:

```bash
./slackbackup workspace register <workspace> <xoxd-cookie>
./slackbackup workspace list          # known vs. registered status
```

### 2. Detecting expiry

- **Automatically, every night:** `scripts/nightly-backup-digest.sh` runs a pre-flight
  (`scripts/preflight-auth.sh`) *before* the backup and lists any stale workspaces at
  the **top** of `~/slack-backups/nightly.log`, so expiries are announced up front
  rather than discovered channel-by-channel mid-run.
- **On demand:**

  ```bash
  ./scripts/preflight-auth.sh channels.json
  ```

  Probes every workspace the backup targets (`slackdump list channels -member-only
  -workspace <ws>`) and prints which need re-auth. Always exits 0 — it never blocks a
  run.

### 3. Re-authenticating an expired workspace

Two supported methods — both need you to log in through a browser (no admin required):

**A. Streamlined helper (recommended) — `scripts/auth-refresh/`**

Reads both the `xoxc` token (localStorage) and the HttpOnly `xoxd` cookie (cookie jar,
which a bookmarklet cannot reach) from a persistent Chromium profile, prompting login
**only** for the workspaces that actually expired, then re-registers each in one pass.

```bash
cd scripts/auth-refresh
npm install            # one-time; reuses the cached ms-playwright Chromium, no download
npm run refresh        # browser opens only for stale workspaces; log in, press ENTER
npm run refresh:dry    # print the slackdump commands instead of running them
```

Set the persistent-profile path once in `.envrc`:
`export SLACKDUMP_AUTH_PROFILE="$HOME/.cache/slackdump-auth-profile"`. See
[scripts/auth-refresh/README.md](../scripts/auth-refresh/README.md) for details.

**B. Manual (always available)**

Repeat the browser capture from README §1 (a fresh cookie, and a fresh token if it
rotated), then re-run `./slackbackup workspace register <workspace> <xoxd-cookie>`. Use
this if Node/Playwright isn't set up.

### 4. Preventing expiry (headless keep-alive)

Slack invalidates a session by **rotating** the shared cookie forward, not by hitting
its expiry timestamp (the cookie's own `expires` attribute is ~13 months out, yet
slackdump sessions die in ~2–3 weeks). A browser follows the rotation automatically;
slackdump keeps a static snapshot and falls behind. `scripts/auth-refresh/keepalive.sh`
(`refresh-auth.mjs --keepalive`) closes that gap: headlessly, on a schedule, it loads
Slack on the persistent profile — keeping the session active and picking up any
rotation — then re-captures the current cookie + tokens and re-registers every
workspace present in the profile. No prompts.

It is wired into `nightly-backup-digest.sh` (before the pre-flight and backup), so a
running nightly job keeps credentials fresh with no human involvement. Requirements: the
persistent profile must still be logged in (a hard logout — password change / forced
sign-out — drops back to interactive §3), and the cadence must beat Slack's inactivity
window (nightly is comfortably inside the observed ~2–3 week expiry).

### Failure modes

| Symptom | Cause | Recovery |
|---------|-------|----------|
| `authentication details expired, relogin is necessary` | Session (cookie/token) expired | Re-auth (§3) |
| `EZ-Login 3000 is not supported on this OS` | slackdump's automated login is unavailable on headless Linux/WSL2 | Expected — re-auth interactively (§3), do not rely on auto-login |
| `004 (Authentication Error)` during `backup run` | One workspace's session died; run continues for the rest (see commit `7834c07`) | Check the pre-flight banner; re-auth the named workspace |
| `flag provided but not defined: -w` | Wrong flag — the workspace flag is `-workspace`, not `-w` | Use `-workspace <name>` (see slackdump-cli-notes) |
| Pre-flight reports a workspace as "error" (not "stale") | Probe failed for a non-auth reason (network, slackdump missing) | Check connectivity / `slackdump` on PATH |

---

## Nightly Backup

`scripts/nightly-backup-digest.sh` is invoked by a Windows Scheduled Task
(`wsl.exe -d Ubuntu -- .../scripts/nightly-backup-digest.sh`) at 2am. It runs the
headless auth keep-alive (§4), then the auth pre-flight (§2), then `backup run`, then the
digest / users / job-digest exports, appending everything to `~/slack-backups/nightly.log`.
It deliberately does **not** `set -e`: a single workspace or channel failure — or the
keep-alive itself — must not stop the rest of the run.

### Tiered cadence (why most channels are "skipped" nightly)

`backup run` no longer opens slackdump for every tracked channel each night. A cadence
filter (`backup_logic.should_check_tonight`, table `BACKUP_CADENCE_TIERS` in
`backup_logic.py`) skips dormant and empty channels on nights they are not due: active
channels (last post < 8 wk) stay nightly, 8–12 wk go every other day, and > 12 wk / empty
channels every 10 days, deterministically staggered so a tier never all runs on one night.
The run summary line reports the not-due skip count. This is safe — the max 10-day cadence
is far inside Slack's ~90-day retention, so a skipped channel that suddenly gets traffic is
still re-checked while every post is live. To force a full sweep regardless of cadence, run
`backup run` with `-f/--full`. To retune, edit the single `BACKUP_CADENCE_TIERS` constant.
Deleting a workspace's catalog resets `last_checked`, so the next run checks everything once.
