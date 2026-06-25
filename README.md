# Slack Archive Toolkit

A local Python CLI (`./slackbackup`) that backs up Slack channel history via slackdump, then
exports it into LLM-ready digests, per-month archives, and a user-profile roster — no Slack
admin access, no app install, no cloud infrastructure. See [docs/DESIGN.md](docs/DESIGN.md) for
the full architecture and a data-flow diagram of what this app does versus what slackdump does.

**Status:** Active development

---

## Getting Started

Everything below runs locally via the `./slackbackup` CLI — no Slack workspace admin access
required. Secrets (the `xoxc-` token and `xoxd-` cookie) stay on your machine in
`~/.slackdump-tokens.json` and slackdump's own local session store — **never** in this repo
(see `.gitignore`'s "Secrets" section).

### Prerequisites

- [slackdump](https://github.com/rusq/slackdump) binary installed — `scripts/install-slackdump.sh`
  downloads and checksum-verifies a pinned release to `~/bin`
- Python ≥3.10; `pip install -e ".[test]"` from the repo root

### 1. Get a token + cookie for each workspace

1. Log into each Slack workspace in your browser (the web app, not just the login page).
2. Open DevTools Console (F12 → Console). If Chrome blocks pasting, type `allow pasting`
   and press Enter first, then paste:

   ```js
   Object.fromEntries(
     Object.values(JSON.parse(localStorage.localConfig_v2).teams)
       .map(t => [(t.domain || t.name).toLowerCase(), t.token])
   )
   ```

   This lists every workspace you're logged into in that browser at once — run it once
   per browser session, not once per workspace.
3. Merge the resulting `{workspace: xoxc-token}` object into `~/.slackdump-tokens.json`
   (create it if it doesn't exist), e.g.:

   ```json
   { "f3pugetsound": "xoxc-...", "f3kirkland": "xoxc-..." }
   ```

4. Get the cookie — **one cookie works for every workspace under the same account**, so
   this is a one-time step, not once per workspace: DevTools → Application/Storage →
   Cookies → `https://<any-workspace>.slack.com` → cookie named `d` → copy its Value
   (starts with `xoxd-`).

### 2. Register a workspace

```bash
./slackbackup workspace register <workspace> <xoxd-cookie>
./slackbackup workspace list   # shows known vs. registered status
```

`<workspace>` is matched against the tokens file keys after lowercasing and stripping a
leading `https://` and trailing `.slack.com` — `f3kirkland`, `f3kirkland.slack.com`, and
`https://f3kirkland.slack.com` all resolve the same way. Registration calls `slackdump
workspace import` under the hood, which needs both the token (from the file) and the
cookie (passed fresh — slackdump doesn't persist cookies, since they expire) every time
you register or re-register.

### 3. Register channels to track

```bash
./slackbackup channel list <workspace>                       # see what's available
./slackbackup channel register <workspace> <#channel-or-id>  # adds it to channels.json
./slackbackup channel validate channels.json
```

### 4. Back up

```bash
./slackbackup backup run channels.json ~/slack-backups
```

Per-channel-month exports (a different, narrower artifact than the digest below) are
also available: `./slackbackup export monthly --from ... --to ... --workspace ...
--channel ... --archive-root ~/slack-backups --out ~/slack-exports`.

### 5. Generate the digest

```bash
./slackbackup export digest --archive-root ~/slack-backups
# -> ~/slack-exports/f3-digest-<today>.json — last 3 months, every f3* workspace,
#    one merged document with messages, channels, and inferred leadership roles
```

### 6. Generate the newsletter report

Feed the digest JSON plus [`docs/newsletter-prompt.md`](docs/newsletter-prompt.md) to an
LLM (e.g. paste both into Claude/ChatGPT, or use the Claude CLI/API with the digest as an
attachment) to produce the actual newsletter. The prompt defines the regional structure,
event/leadership handling, and sourcing rules — it expects the digest's schema
(`messages`, `channels`, `leadership.by_region`) as-is, so don't reshape the JSON first.

### 7. Generate a new-member "Start Here" guide (optional)

Feed the digest JSON plus [`docs/fng-getting-started-prompt.md`](docs/fng-getting-started-prompt.md)
to an LLM to produce a "Slack: Start Here / FAQ" guide for new members, sourced only from the
digest's actual channels/roles/events — same pattern as the newsletter prompt above.

Run `./slackbackup help` for the full command list.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [CONTEXT.md](docs/CONTEXT.md) | Purpose, capabilities, use cases |
| [DESIGN.md](docs/DESIGN.md) | Per-channel backup architecture, modules, key decisions |
| [DESIGN-export.md](docs/DESIGN-export.md) | Export pipeline: monthly per-channel JSON, cross-workspace LLM digest, user-profile roster |
| [DESIGN-files.md](docs/DESIGN-files.md) | Channel catalog (implemented) + canvas/file harvesting (designed, not yet ported to Python) |
| [references/slackdump-cli-notes.md](docs/references/slackdump-cli-notes.md) | slackdump CLI behavior, costs, and gotchas learned the hard way — check before re-deriving |
| [ADRs](docs/adr/) | Architecture decision records |

---

## License

MIT — see [LICENSE](LICENSE) for details.
