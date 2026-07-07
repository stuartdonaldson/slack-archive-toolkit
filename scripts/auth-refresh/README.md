# auth-refresh — one-command Slack session refresh

Re-authenticating slackdump normally means, per workspace, digging the `xoxc` token
out of `localStorage` and the **HttpOnly** `xoxd` `d` cookie out of DevTools. A
bookmarklet can't do the cookie (JS is blocked from HttpOnly cookies by design). This
helper uses the Chromium you already have (ms-playwright) to read **both** and
re-register every expired workspace in one pass.

It uses the plain browser-session method, so it needs **no admin rights and no Slack
app install** — the tradeoff is that sessions expire and you re-run this when they do.

## Setup (once)

```bash
cd scripts/auth-refresh
npm install          # installs @playwright/test; the Chromium binary is already in ~/.cache/ms-playwright
```

Add the persistent-profile path to your `.envrc` (direnv) so logins survive between runs:

```bash
export SLACKDUMP_AUTH_PROFILE="$HOME/.cache/slackdump-auth-profile"
```

## Use

```bash
npm run refresh        # probe all workspaces; open a browser only for expired ones
npm run refresh:dry    # same, but print the slackdump commands instead of running them
node refresh-auth.mjs --all   # force-refresh every workspace
```

For each workspace that needs it, a browser window opens on that workspace's Slack —
log in normally (SSO / 2FA included), wait for the workspace to load, press ENTER. The
helper then extracts the credentials and runs `slackdump workspace new -token … -cookie …`.

### Keeping sessions alive (headless)

Slack rotates the shared session cookie forward; a browser follows the rotation but
slackdump keeps a static snapshot, so its sessions expire in ~2–3 weeks. `--keepalive`
prevents that: it headlessly loads Slack on the persistent profile (keeping the session
active and picking up any rotation), re-captures the current cookie + tokens, and
re-registers every workspace present in the profile — no prompts.

```bash
npm run keepalive              # headless; safe to schedule
./keepalive.sh                 # same, via a node-resolving wrapper (used by the nightly job)
```

`keepalive.sh` is wired into `scripts/nightly-backup-digest.sh` before the backup, so a
scheduled nightly run keeps credentials fresh on its own. Interactive `npm run refresh`
is then only needed after a **hard** logout (password change / forced sign-out), which
no automated flow can survive.

## Environment

| Var | Default | Purpose |
|-----|---------|---------|
| `SLACKDUMP_AUTH_PROFILE` | `~/.cache/slackdump-auth-profile` | Persistent Chromium profile (set in `.envrc`) |
| `SLACKDUMP_TOKENS` | `~/.slackdump-tokens.json` | Workspace list (the file's keys) |
| `SLACKDUMP_BIN` | `slackdump` | slackdump binary |

## Design

- `auth_logic.mjs` — pure, unit-tested logic (workspace list, token parse, cookie pick,
  session classification, workspace→token match, argv build). `node --test`.
- `refresh-auth.mjs` — thin I/O shell: slackdump probing, Playwright browser, spawning.

The `xoxd` cookie is only held in memory and passed inline to slackdump; this helper
never writes it to disk.

See bd `SlackBackup-fac` for acceptance criteria.
