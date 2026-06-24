# DESIGN — Channel Catalog & Canvas/File Harvesting

**Status: implemented.** `scripts/lib/channel_catalog.sh` + `scripts/catalog-channels.sh`
(catalog), `scripts/fetch-files.sh` + `scripts/lib/fetch_files_helpers.sh` (search-files
harvesting), and `scripts/build-file-index.sh` + `scripts/lib/file_index_helpers.sh`
(indexing) are all written, tested (49 passing unit/fixture tests across
`scripts/test_catalog_channels.sh`, `scripts/test_fetch_files.sh`,
`scripts/test_build_file_index.sh`), and verified live against real workspace data. A few
implementation-time corrections to this design are called out inline below where they
matter; see `docs/references/slackdump-cli-notes.md` for the empirically-verified facts
(channel `description` via the same `-format JSON` call, `tools merge` not being usable on
search-result databases, `FILE.DATA` carrying all file metadata with no separate
`MIMETYPE` column, search-result rows carrying a `CHANNEL_ID` placeholder of `"SEARCH"`).

Tracked as `SlackBackup-6ql` (catalog), `SlackBackup-d02` (fetch-files), `SlackBackup-t2b`
(build-file-index) — all closed. Companion to `docs/DESIGN.md` (per-channel message
backup) and `docs/DESIGN-export.md` (monthly JSON export). See
`docs/references/slackdump-cli-notes.md` for the underlying slackdump behavior/cost facts
this design relies on — read that first if anything below seems under-justified.

---

## Problem

Two related but distinct asks:

1. **Canvas + non-image file harvesting**: download every Slack Canvas and every
   non-image file attachment across every channel in the `f3*` workspaces — not just
   the 15 channels tracked in `channels.json` — organized for human browsing, **without**
   archiving full chat history for channels that aren't already tracked.
2. **Channel catalog**: an easy, periodically-refreshed list of which channels exist per
   workspace (all public channels, plus any private ones the user is a member of) and,
   where cheaply available, when each last had activity — without re-triggering the
   throttling previously hit when doing this naively.

These share the same underlying primitive (channel enumeration + naming) and the same
cost-asymmetry lesson, so they're designed together.

## Key constraint: no single slackdump command gives "all files, no message history"

- `slackdump archive` finds files completely, but only by indexing a channel's full
  message history — exactly the chat-archiving the user ruled out for untracked
  channels.
- `slackdump search files <term>` finds files without indexing history, but is
  **keyword relevance search, not exhaustive enumeration** — confirmed empirically (see
  `slackdump-cli-notes.md` §search files): no working `filetype:`-only query, no `OR`
  operator, only single-term-at-a-time queries that need to be run separately and
  merged. It can only ever be **best-effort**, never a completeness guarantee.

**Decision:** use both, for different scopes, and merge by file ID:
- **Tracked channels** (`channels.json`, already fully `archive`d/`resume`d): read the
  local `slackdump.sqlite` `FILE` table directly. Complete, free (no API call), already
  kept current by `run-backups.sh`.
- **Everything else** in the same workspace: `search files` with a curated list of
  broad terms (starting point: `pax`, `convergence`, `help`, `ruck`, `ao`, `health` —
  extend this list freely; it's just config, not code), one query per term, merged and
  deduped by file ID. Explicitly best-effort — will miss files that don't match any
  term. This tradeoff was discussed and accepted by the user as "not expensive, not
  frequent, good enough."

## File harvesting design

### `scripts/fetch-files.sh <out-archive-root>` (new)

- Loops the **registered** `f3*` workspaces — registering one needs a fresh session
  cookie, see `./slackbackup workspace register` / README.md's "Getting Started".
  `dungeons-of-finn-hill` is excluded (not an `f3*` workspace).
- Per workspace, runs `slackdump search files <term>` once per configured term into
  `<out-archive-root>/<workspace>/<term>/`, then `slackdump tools merge` (verify its
  semantics first — untested in this project, see cli-notes) to combine per-term result
  databases into one per-workspace database. Kept separate from `~/slack-backups` (the
  tracked per-channel archives) since it's a different kind of artifact.
- This step makes real Slack API calls; re-running it is cheap (each search is
  sub-second) but not free, so it's a deliberate, occasional/manual invocation — not
  wired into `run-backups.sh`'s automatic cadence (unlike the channel catalog below).

### `scripts/build-file-index.sh <out-files-dir> <index.json>` (new)

For **both** sources (tracked-channel archives under `~/slack-backups`, and the
search-result databases under the new `fetch-files.sh` output root):
- Query `FILE` rows with `mimetype NOT LIKE 'image/%'` (covers canvases for free — see
  cli-notes §FILE table).
- Resolve `CHANNEL_ID` → channel name via the channel catalog (below) — not a fresh
  `slackdump list channels` call.
- Dedupe by file `ID` across both sources; compute `first_seen`/`last_seen` as
  `min`/`max(LOAD_DTTM)` across all rows for that ID (the agreed substitute for "edit
  history," since Slack's file API exposes no real revision history — see cli-notes).
- For each unique file, **copy** (not move) the already-downloaded blob from
  `.../__uploads/<file-id>/<original-filename>` into
  `<out-files-dir>/<workspace>/<channel>/<filename>__<file-id>.<ext>` (sanitized for
  filesystem safety).
- Append one record per file to `<index.json>`: file id, workspace, channel, filename,
  title, mimetype, filetype, size, created (upload ts), message context (channel canvas
  vs. message-attached + ts), permalink, local path, first_seen, last_seen.
- Idempotent re-run: a file already present in the index is skipped (no re-copy);
  stdout convention follows `export_transform.sh`'s existing
  `wrote`/`skipped`/`empty` style.

## Channel catalog design

Generalizes `scripts/register-channel.sh`'s existing `get_channel_list()` /
`~/.cache/register-channel/<workspace>.txt` TTL-cache (900s default) — don't build a
second cache, extend that one.

**Two tiers, different cadence:**

| Tier | Call | Cost | Refresh trigger |
|---|---|---|---|
| Fast | `list channels -member-only ...` | seconds | Automatically, once per `run-backups.sh` run (cache TTL makes same-day reruns free) |
| Full | `list channels` (no `-member-only`) | minutes, rate-limited (slackdump self-backs-off) | Explicit, separate command only — never automatic |

- The **full** tier is also the fallback `register-channel.sh` should consult when a
  channel-by-name lookup misses the fast cache (a public channel the user hasn't
  joined) — this was very likely the cause of the "registering by name took forever"
  experience referenced this session, since the old code had no fast/full split and
  effectively had to do the expensive thing inline.
- **Last-content-posted** is part of the catalog, but cost-asymmetric:
  - **Free** for tracked channels: `MAX(ts)` from the local archive, no API call.
  - **Not included by default** for everything else — would cost one API call *per
    channel* (hundreds of calls for the full tier), the same throttling pattern just
    worse. If ever wanted, it must be its own explicit, separately-invoked operation
    (self-throttled or accepting imposed Slack backoff), never folded into the regular
    catalog refresh.
- Output should replace the stale, manually-generated `channels-T*.txt` files currently
  committed in the repo root (one per workspace team ID, e.g. `channels-T78NKT50E.txt`
  = `f3pugetsound`) — those were ad hoc one-off dumps, not a maintained artifact.

## Non-goals (for both pieces)

- No message/chat history archiving for channels not already in `channels.json`.
- No attempt at true Slack canvas edit/revision history — not exposed by this API
  path; first-seen/last-seen is the agreed substitute.
- No per-channel last-activity lookup for untracked channels by default — explicit
  opt-in only, due to the per-channel API call cost.
- Not modifying `channels.json` or the existing per-channel backup/export scripts.

## Open items — resolved during implementation

- `slackdump tools merge` was verified empirically and turned out **not usable**:
  search-result databases have an always-empty `CHANNEL` table (`search files` never
  populates it), and `tools merge` requires a non-empty source `CHANNEL` table —
  fails with `getting channels: no data found`. Adopted fallback: `fetch-files.sh`
  keeps each search term's result directory separate; `build-file-index.sh` reads
  `FILE` rows across all of them directly. Full details in
  `docs/references/slackdump-cli-notes.md` §`tools merge`.
- Search term list lives in `scripts/config/file-search-terms.txt` (starting list:
  `pax`, `convergence`, `help`, `ruck`, `ao`, `health`) — editable config, not code.
- bd issues filed and closed: `SlackBackup-6ql`, `SlackBackup-d02`, `SlackBackup-t2b`.
- `fetch-files.sh` detects unregistered `f3*` workspaces from the slackdump tokens file
  and skips them with a warning naming `./slackbackup workspace register <name>
  <fresh-cookie>` as the remedy — not scripted around, per the original constraint.
- Channel `description` (not in the original design) was added to the catalog: both
  tiers call `list channels -format JSON` instead of the default Text format, so
  `topic`/`purpose` come from the same single API call already being made.
