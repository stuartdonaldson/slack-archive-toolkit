# CONTEXT — Slack Archive Toolkit

## Introduction & Goals

### Purpose

A local Python CLI (`./slackbackup`) that backs up Slack channel history to a local archive,
using `slackdump` for every Slack-facing operation — no Slack admin access, no app installation,
no cloud infrastructure. On top of the archive, it generates read-only derived products meant
for human or LLM consumption: a cross-workspace digest, bounded per-channel-month exports, a
user-profile roster, and a live cross-workspace message search. Preserves irreplaceable
conversation history against workspace deletion, plan downgrades, or account lockout.

This supersedes an earlier GitHub-Actions/NDJSON/private-archive-repo design (see git history)
which was abandoned before being built out — everything in this document describes the actual
shipped local-CLI architecture.

### Quality Goals

| Priority | Quality Goal | Scenario |
|----------|-------------|----------|
| 1 | Reliability | A backup run completes or fails with a clear, timestamped log entry per channel and a run summary; no silent data loss |
| 2 | Operability | An operator can register a workspace, register channels (individually or by bulk glob), and have a working backup running in well under 30 minutes |
| 3 | Low coupling to slackdump internals | This app reads `slackdump`'s documented, stable boundaries (`convert -f export`, `list channels` JSON) wherever possible, falling back to the internal sqlite schema only where slackdump exposes no other path (e.g. channel-level Canvas files) |

### Stakeholders

| Stakeholder | Expectation |
|-------------|-------------|
| Operator (currently: the author, running this against several F3 workspaces) | Run the CLI locally on a schedule or by hand; get a durable archive plus a digest suitable for feeding an LLM newsletter-generation prompt |
| Forker | Minimal required changes to adapt `channels.json` and the tokens file to a different workspace |

---

## Constraints

### Technical Constraints

- No Slack admin access; no Slack app installation
- Authentication is `slackdump`'s own session model: a per-workspace `xoxc-` token (from
  `~/.slackdump-tokens.json`, not committed) plus a freshly-pasted `xoxd-` browser cookie, fed to
  `slackdump workspace import`
- This app never calls the Slack API directly — confirmed by inspection (no `requests`/
  `urllib`/`httpx` import anywhere in `src/slackbackup/`); every Slack-facing operation is a
  subprocess call to the `slackdump` binary, funneled through `src/slackbackup/slackdump.py`
- `slackdump` binary installed locally (`scripts/install-slackdump.sh` pins and verifies a
  release); not bundled with this repo
- Storage format is `slackdump`'s own native archive (`slackdump.sqlite` per channel); export
  formats are read-only derived products generated on demand, never the primary store

### Organizational Constraints

- No credentials of any kind are ever committed: tokens file and slackdump's own session store
  both live outside the repo (`~/.slackdump-tokens.json`, `~/.cache/slackdump`)
- `channels.json` (repo root) is the only Slack-related state committed to the repo, and it
  holds no secrets — just `{id, name, workspace}` join keys

---

## Core Capabilities

- **Workspace registration** (`workspace register/list`) — imports a session for a workspace
  from a tokens file + pasted cookie.
- **Channel registration** (`channel register/register-matching/list/validate`) — track a
  channel by exact name/id, or bulk-discover every new public channel matching a glob or
  comma-separated selector list across a workspace glob (e.g. nightly `channel
  register-matching 'f3*' '*'` or `channel register-matching 'f3pugetsound,f3kirkland'
  'helpdesk,event-*'`), automatically excluding private, archived, and `shuttered*`-named
  channels.
- **Channel catalog** (`catalog show`) — a persistent, two-tier (fast member-only / explicit
  full) cache of channel metadata (description, creator, created, private/archived flags) plus
  this app's own recency bookkeeping (`registered_at`, `last_posted`) — see `docs/DESIGN-files.md`.
- **Per-channel incremental backup** (`backup run/status`) — archives a channel on first
  contact, resumes incrementally thereafter, auto-heals a channel stuck on an unresumable empty
  archive, processes a multi-channel run most-recently-active-first, and logs timestamped
  progress plus a final summary — see `docs/DESIGN.md`.
- **Monthly export** (`export monthly`) — turn one archived channel into bounded, sealed,
  idempotent per-month JSON files with thread replies nested under their parent — see
  `docs/DESIGN-export.md`.
- **Cross-workspace digest** (`export digest`) — one merged, chronological JSON document
  covering the trailing 180 days by default (or a different N via `--days`) across every
  workspace matching a glob or comma-separated selector list, enriched with
  per-channel context, non-image file/Canvas content, and both inferred leadership roles and
  authoritative Slack account roles — designed as direct LLM input, e.g. for a newsletter
  prompt. Also carries precomputed per-channel and per-workspace activity counts (message/
  reply/participant counts, active-vs-inactive status, most-active channel with a bot-excluded
  variant) so an LLM doesn't have to recount the raw `messages` array for inventory questions —
  see `docs/DESIGN-export.md`.
- **User profile export** (`export users`) — full per-workspace user roster with `slack_roles`
  (admin/owner/bot/etc.) — see `docs/DESIGN-export.md`.
- **Report jobs** (`export digest --jobs 'jobs/*.json'`) — drive one or more digests (each with an
  optional companion user roster) from operator-owned, gitignored `jobs/*.json` files that fully
  specify their own archive root, channels file, workspaces, day window, output path
  (`{as_of}`-templated), and leadership handler — instead of command-line flags. Wired into the
  nightly script; F3 leadership tagging is pluggable per job — see `docs/DESIGN-export.md`.
- **Untracked-channel digest** (`channel-digest run`) — an on-demand tool that archives every
  channel matching an fnmatch glob (e.g. `shuttered-*`) and writes a single merge-aware JSON
  digest of surviving messages/files/orphaned Canvases — for recovering content from channels
  outside `channels.json` (e.g. Canvases stranded by a region migration) — see
  `docs/DESIGN-files.md`.
- **Cross-workspace message search** (`search messages`) — search every registered workspace
  matching a name, glob, or comma-separated selector list for a query, rendered as one HTML
  report, most recent first, linking to each channel/message. The one capability that makes a
  live Slack API call (via slackdump) on every invocation rather than working off a local cache.
- **Canvas/file catalog** — designed (`docs/DESIGN-files.md`) but **not yet ported to Python**;
  the shell implementation (`scripts/fetch-files.sh`, `scripts/build-file-index.sh`) is the only
  one that exists today.

---

## Use Cases

### UC-1: Incremental Backup of a Tracked Channel

Actor: Operator (manually, or via a local scheduled task)

Preconditions:
- The channel's workspace is registered (`workspace register`)
- The channel is listed in `channels.json`

Primary Flow:
1. Operator runs `./slackbackup backup run channels.json <archive-root>`
2. For each channel, the tool checks whether a local non-empty `slackdump.sqlite` archive
   already exists
3. If not, it runs a full `slackdump archive`; if it does, it runs `slackdump resume` to fetch
   only new activity
4. The catalog's `last_posted` for that channel is updated from the archive's own max message
   timestamp, if any messages were found
5. Each channel's outcome and elapsed time is logged with a UTC timestamp; a run summary is
   printed at the end

Alternate Flows:
- A1: The existing local archive has zero messages (an unresumable state) → the tool wipes the
  stale directory and re-archives from scratch rather than failing forever
- A2: One channel's backup fails → the run continues with the remaining channels; the overall
  run reports failure, but partial progress is not lost

Postconditions:
- Each channel's archive reflects all messages up to the time of the run (or is unchanged, if
  the channel failed)
- The catalog reflects each successfully-backed-up channel's real last-post time

Acceptance Criteria:
- A channel with no local archive is fully archived
- A channel with a non-empty local archive is resumed, not re-archived
- A channel run order is most-recently-active first, using real `last_posted` data where
  available and falling back to `registered_at` otherwise
- A failure on one channel does not abort the remaining channels in the run

---

### UC-2: Bulk Discovery of New Public Channels

Actor: Operator (typically via a nightly scheduled task)

Preconditions:
- One or more workspaces matching the workspace glob are already registered

Primary Flow:
1. Operator runs `./slackbackup channel register-matching '<workspace-glob>' '<channel-glob>'`
2. The tool refreshes the full channel catalog tier for each matching, registered workspace
3. For each channel matching the channel glob that is not already tracked, not private, not
   archived, and not named `shuttered*`, the tool appends it to `channels.json` and stamps
   `registered_at` in the catalog

Postconditions:
- `channels.json` contains every newly-discovered, eligible public channel
- Each newly-added channel has a `registered_at` timestamp in the catalog, used as a recency
  fallback by UC-1 until a real backup finds message data

Acceptance Criteria:
- Private channels, archived channels, and `shuttered*`-named channels are never added,
  regardless of glob match
- An already-tracked channel is never added twice
- An unregistered workspace matching the workspace glob is skipped and reported, not an error

---

### UC-3: Cross-Workspace Digest for LLM Consumption

Actor: Operator

Preconditions:
- At least one channel per relevant workspace has already been backed up (UC-1)

Primary Flow:
1. Operator runs `./slackbackup export digest --archive-root <path> [--workspace-glob f3*]
   [--days N]`
2. The tool selects channels matching the workspace glob from `channels.json`, computes the
   date range (the trailing 180 days by default, or the trailing N days if `--days` was given), and
   for each channel with a local archive: converts it via slackdump,
   extracts in-range messages with thread nesting, enriches with channel context from the
   catalog (read-only, no live API call) and non-image file/Canvas content read directly from
   the archive
3. All channels' messages are merged into one chronologically-sorted list across every
   workspace, alongside inferred leadership-role matches
4. Per-channel and per-workspace activity is precomputed (message/reply/participant counts,
   active-vs-inactive status, most-active channel — with a variant that excludes channels whose
   activity is bot-driven, detected via the user roster's `is_bot` flag, not by channel name)

Alternate Flows:
- A1: A selected channel has no local archive → recorded as `status: missing_archive` in the
  output; the run continues for the remaining channels

Postconditions:
- One JSON document is produced, suitable as direct LLM input

Acceptance Criteria:
- Output is a single valid JSON document, not one file per channel/month
- Messages are sorted chronologically across all workspaces, not grouped by workspace
- No top-level merged user/author identity table exists — the same Slack user id is not assumed
  to mean the same person across different workspaces
- A missing archive for one channel does not abort the digest for the remaining channels
- Each channel's activity counts and `activity_status` are derived from the same range-filtered
  messages already in the digest, not recomputed differently or sourced live

---

## Non-Goals

- Real-time backup (cadence is operator-driven — manual or scheduled, never continuous)
- A browsing/rendering UI for archived content beyond the HTML search-results report
- Slack message deletion or modification
- A merged cross-workspace identity/user table (see UC-3 — deliberately out of scope; the same
  Slack user id means different people in different workspaces)
- Building a custom Slack API client — every Slack-facing capability is implemented by calling
  `slackdump`, never by reimplementing what it already does

---

## Glossary

| Term | Definition |
|------|------------|
| slackdump | Third-party CLI tool (https://github.com/rusq/slackdump) that this app calls via subprocess for every Slack-facing operation; owns auth, the Slack API, archive storage, and export-format conversion |
| archive | One channel's durable local backup: a `slackdump.sqlite` database plus downloaded file blobs, at `<archive-root>/<workspace>/<channel>/` |
| catalog | This app's own persistent cache of channel metadata, two-tier (fast member-only / explicit full), at `~/.cache/slackbackup/<workspace>.catalog.json` — see `docs/DESIGN-files.md` |
| `registered_at` / `last_posted` | This app's own recency bookkeeping in the catalog (no Slack-API source) — when a channel was first tracked, and the real last-message time once a backup finds data — used to order multi-channel backup runs |
| digest | The cross-workspace, single-document export meant for LLM consumption, covering the trailing 180 days by default or a different trailing N days via `--days` (`export digest`) — see `docs/DESIGN-export.md` |
| `channels.json` | Repo-root join-key list (`{id, name, workspace}`) of tracked channels — deliberately minimal; richer metadata lives in the catalog, not here |
| tokens file | `~/.slackdump-tokens.json`, a flat `{workspace: xoxc-token}` map the operator maintains by hand; never committed |
