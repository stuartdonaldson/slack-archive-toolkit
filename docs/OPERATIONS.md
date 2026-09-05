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
(`wsl.exe -d Ubuntu -- /home/stuar/proj/SlackArchiver/scripts/nightly-backup-digest.sh`) at 2am,
appending everything to `~/slack-backups/nightly.log`. In order, each run:

| # | Step | Notes |
|---|------|-------|
| 0 | Copy the canonical LLM context pack into `~/slack-exports/llm-context/` | Individually uploadable Project-knowledge files live under `docs/llm-context/uploads/`; `project-instructions.md` and `session-preamble.md` are pasted, while `prompts/*.md` are selected by an operator. [docs/llm-context/README.md](llm-context/README.md) is the upload and validation guide for both one-off sessions and ChatGPT Projects. The legacy per-file prompt/context docs were retired in `sat-ejk.5` per [ADR-0008](adr/0008-llm-context-pack-decomposition.md). Local edits made under `~/slack-exports/` **are overwritten every night** — edit the copy in `docs/` |
| 1 | `scripts/auth-refresh/keepalive.sh` — headless credential keep-alive (§4) | Non-fatal; a hard logout still needs interactive `npm run refresh` |
| 2 | `scripts/preflight-auth.sh channels.json` — stale-session banner (§2) | Informational, always exits 0 |
| 3 | `./slackbackup channel register <one workspace> '*'` — pick up newly-created public channels | **One workspace per night**, rotating — see below |
| 4 | `./slackbackup backup run channels.json ~/slack-backups` | Subject to the tiered cadence filter, below |
| 5 | `./slackbackup dm register-matching '*' --dms-file dms.json` — discover/prune tracked DM conversations | Cheap member-only tier only; see `docs/DESIGN-dms.md` |
| 6 | `./slackbackup backup run dms.json ~/slack-backups` | Same `backup_logic.run()` as step 4, pointed at `dms.json` |
| 7 | `./slackbackup export digest --jobs jobs/*.json` — one digest (plus optional user roster and `files_out` sidecar) per report job, including `jobs/f3-dm-digest.json` | Job files are gitignored; see `docs/DESIGN-export.md` §Report jobs and `docs/DESIGN-dms.md` |

There is deliberately **no blanket `export digest` / `export users` step** any more: every real
recipient is described by a job file in `jobs/`, and the blanket run duplicated that work at full
cost. Both remain available as manual commands when needed.

The script deliberately does **not** `set -e`: a single workspace or channel failure — or the
keep-alive itself — must not stop the rest of the run. Each step's exit code is echoed into the
log (`----- <step> exited N -----`) rather than acted on.

### Nightly channel registration (all workspaces, every night)

Step 3 exists because a newly-created public channel is otherwise invisible to the backup until a
human notices and registers it by hand (the motivating case: `disc-it` went un-backed-up for weeks
in `f3pugetsound`). `channel_logic.register_matching` skips private, archived,
`shuttered*`-named, and already-registered channels when deciding what to *add*. It also *prunes*
`channels.json` (sat-21k): an already-tracked channel that's now archived, or missing entirely
from that workspace's full-tier scan (only when the scan came back complete, not truncated), is
removed and reported as `channel register: removed ... — archived|missing`. `shuttered*`-named
channels are exempt from pruning (deliberate manual retention). Pruning never deletes or touches
the channel's local archive on disk — only its `channels.json` entry, so it stops being backed up
nightly but its history stays put.

The cost is the **full** (non-`-member-only`) catalog listing it must do per workspace to know
what exists — flagged in `docs/references/slackdump-cli-notes.md` as potentially minutes per
workspace and rate-limit-prone, with no cheaper "just the new ones" API. This originally motivated
scanning only one workspace per night (`day-of-year mod <workspace count>`), re-scanning each
roughly weekly. Measured in practice it's actually ~1.5–2 minutes per workspace, not "several" —
cheap enough across all 9 registered workspaces that the script now scans every workspace every
night (`./slackbackup channel register '*' '*'`), so a newly-created channel shows up in the very
next run instead of waiting up to a week for its rotation slot. Already-registered lines are
filtered out of the log to keep it readable.

To force a scan of a specific workspace immediately:

```bash
./slackbackup channel register <workspace> '*' --channels-file channels.json
```

### Stopping an in-progress run

`scripts/stop-nightly-backup.sh` (bd `sat-b9b`) stops a running
`nightly-backup-digest.sh` and verifies the stop, instead of hand-walking `ps`/`kill`
across the wrapper, whichever `slackbackup` stage is active (`backup run` or
`export digest`), and any orphaned `slackdump` child (archive/resume/dedupe/convert) —
the wrapper doesn't propagate `SIGTERM` to that child itself.

```bash
./scripts/stop-nightly-backup.sh                 # defaults: wrapper at
                                                   # scripts/nightly-backup-digest.sh,
                                                   # archive root ~/slack-backups
./scripts/stop-nightly-backup.sh --grace-seconds 10   # tune the SIGTERM grace window
./scripts/stop-nightly-backup.sh --wrapper-script <path> --archive-root <dir>  # non-default paths
```

What it does, in order:

1. Finds the running wrapper by its exact script path (not a name substring, which could
   catch an unrelated process) — reports cleanly and exits 0 if none is running.
2. Walks the full process tree under it by parentage (`pgrep -P`, recursively — not
   `pgrep -f slackdump`, which risks matching an unrelated concurrent process),
   captured *before* any signal is sent, since a dead parent's children are reparented
   and no longer discoverable via their original parent.
3. Sends `SIGTERM` to the wrapper, then to anything in the tree still alive after a
   bounded poll (not a blind `sleep N`).
4. Sends `SIGKILL` to anything still alive after a further bounded grace period
   (`--grace-seconds`, default 5s per phase — ~15s worst case end to end).
5. Verifies via `kill -0` that nothing in the tree remains, then scans every
   `<workspace>/.<channel>.lock` file under the archive root
   (`src/slackbackup/channel_lock.py`): a lock whose pid is still alive is flagged as a
   live holder needing manual attention (should not normally happen right after this
   script's own kill pass); a lock whose pid is dead is reported informationally and
   left in place — reclaim-by-liveness (`channel_lock()`) handles it automatically on
   the next use, so this script never deletes lock files.

Prints one final `STATUS:` line: stopped cleanly (nothing was running, or `SIGTERM`
alone was enough), force-killed (some process needed `SIGKILL`, but the run is
confirmed fully stopped), or a live lock holder / a process that survived `SIGKILL` —
either of which needs manual attention (exit codes 1 and 2 respectively; see the
script's own `--help` for details).

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

### Recovering catalog recency after an interrupted run

`backup run` stamps `last_posted`/`registered_at`/`last_checked` per channel as it goes, so an
interrupted run leaves the catalog partially stale. `backup sync-catalog` rebuilds those recency
fields from **local archives only** — no Slack API calls, safe to run any time:

```bash
./slackbackup backup sync-catalog channels.json ~/slack-backups
```

### The `files_out` sidecar is not disposable output

Everything under `~/slack-exports/` is regenerable from the archive **except** a job's `files_out`
sidecar. It is cumulative across runs: each run merges into the existing document and carries
forward files whose source has since aged out of Slack's ~90-day retention or whose channel fell
outside that run's selectors. Deleting it discards records the archive can no longer reproduce.
A corrupt/unreadable sidecar is logged and treated as absent (the job still completes), which
means a truncated file silently restarts the history — back it up with the digests, and check the
`N files -> <path>` log line for an unexpected drop. See `docs/DESIGN-export.md` §`files_out`
sidecar.
