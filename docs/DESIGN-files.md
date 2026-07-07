# DESIGN — Channel Catalog & Canvas/File Harvesting

**Status: split.** The **channel catalog** (second half of this doc) was originally shell
(`scripts/lib/channel_catalog.sh` + `scripts/catalog-channels.sh`) and has since been **ported
to Python** — `src/slackbackup/catalog_logic.py` (CLI: `catalog.py`) — and extended well beyond
the original design (see §Catalog additions since the original design, below). The shell
scripts are gone; the Python module is the only implementation.

**Canvas/non-image-file harvesting** (first half of this doc — `fetch-files.sh`/
`build-file-index.sh`) was implemented as shell only and **has not been ported to Python**.
`src/slackbackup/files.py`'s `fetch`/`index` handlers still raise `NotImplementedError`;
`files_logic.py` implements only the read side (`summarize()` over an already-existing
`index.json`) — the schema below is the contract, regardless of which tool eventually produces
it. Port when the cross-channel file-harvesting use case is actually needed; the design below
remains valid, just unimplemented in the current codebase.

A few implementation-time corrections to the original (shell) design are called out inline below
where they matter; see `docs/references/slackdump-cli-notes.md` for the empirically-verified
facts (channel `description` via the same `-format JSON` call, `tools merge` not being usable on
search-result databases, `FILE.DATA` carrying all file metadata with no separate `MIMETYPE`
column, search-result rows carrying a `CHANNEL_ID` placeholder of `"SEARCH"`).

Tracked as `SlackBackup-6ql` (catalog), `SlackBackup-d02` (fetch-files), `SlackBackup-t2b`
(build-file-index) — all closed (the original shell work; the catalog's later Python port and
extensions were untracked). Companion to `docs/DESIGN.md` (per-channel message backup) and
`docs/DESIGN-export.md` (export pipeline — `export digest` reads the catalog read-only for
per-channel context). See `docs/references/slackdump-cli-notes.md` for the underlying slackdump
behavior/cost facts this design relies on — read that first if anything below seems
under-justified.

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
  kept current by `backup_logic.run()` (the Python port of `run-backups.sh`).
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
  wired into `backup_logic.run()`'s automatic cadence (unlike the channel catalog below).

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

## Channel digest (`channel-digest run`) — implemented

The file-harvesting design above (`fetch-files.sh`/`build-file-index.sh`) remains shell-only and
best-effort. A separate, **implemented** Python command covers the specific case that motivated
it in practice — recovering orphaned channel-level Canvases and residual messages from
**untracked** channels (e.g. `shuttered-*` channels a region migration left behind, whose
standalone Canvas — `FILE.MESSAGE_ID IS NULL` — never migrated with the message history):

```bash
./slackbackup channel-digest run <workspace> <pattern> <out_dir>
# e.g. ./slackbackup channel-digest run f3pugetsound 'shuttered-*' ~/slack-backups/shuttered-digest
```

- `<pattern>` is an fnmatch glob against channel name. Every matching channel is archived (a full
  `slackdump archive`, since these are untracked and have no prior checkpoint), then a single
  JSON digest of surviving messages/files/canvases is written, authors resolved via the workspace
  roster. Unlike a Canvas linked in a message, a channel-level Canvas is captured by `slackdump
  archive` regardless of whether any message references it — but only for a channel that is
  actually archived, which untracked channels never are under the normal backup cadence.
- Output is a schema-versioned document (`slack-channel-digest-v2`,
  `channel_digest_logic.SCHEMA_VERSION`) following the same `schema_version` convention as
  `export_logic`'s digests — the primary consumer is an LLM, not a human skimming a table.
- `merge_digests()` makes a re-run against an existing `out_dir` **merge** rather than overwrite:
  it tracks `first_seen_at`/`last_seen_at` per channel/message/file and `content_last_changed_at`
  per file, so a later pass can show what is new or changed. Merging across a schema-version
  change is refused loudly.
- **Deliberately manual/on-demand** — not wired into the nightly backup cadence, and it writes
  outside the repo (it contains real names/chat content). Implemented in
  `src/slackbackup/channel_digest.py` + `channel_digest_logic.py`. Tracked as `SlackBackup-ie2`
  (closed).

## Channel catalog design

Generalizes the original shell `register-channel.sh`'s `get_channel_list()` /
`~/.cache/register-channel/<workspace>.txt` TTL-cache (900s default) — don't build a
second cache, extend that one.

**Two tiers, different cadence:**

| Tier | Call | Cost | Refresh trigger |
|---|---|---|---|
| Fast | `list channels -member-only ...` | seconds | Automatically, once per `backup_logic.run()` invocation (cache TTL makes same-day reruns free) |
| Full | `list channels` (no `-member-only`) | minutes, rate-limited (slackdump self-backs-off) | Explicit, separate command only — never automatic |

- The **full** tier is also the fallback a name-based lookup (`channel_logic.register`) consults when a
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
- This catalog has since replaced the stale, manually-generated `channels-T*.txt` files that
  used to be committed in the repo root (one per workspace team ID, e.g.
  `channels-T78NKT50E.txt` = `f3pugetsound`) — those were ad hoc one-off dumps, not a maintained
  artifact, and have been deleted.

## Non-goals (for both pieces)

- No message/chat history archiving for channels not already in `channels.json`.
- No attempt at true Slack canvas edit/revision history — not exposed by this API
  path; first-seen/last-seen is the agreed substitute.
- No per-channel last-activity lookup for untracked channels by default — explicit
  opt-in only, due to the per-channel API call cost.
- Not modifying `channels.json` or the existing per-channel backup/export scripts.

## Catalog additions since the original design

The Python port (`catalog_logic.py`) kept the two-tier fast/full cache design unchanged but
extended the per-channel schema and added a bulk-registration feature the original design did
not anticipate:

### Schema additions

Beyond `member`/`name`/`description` (the original design), each cached channel now also
carries:

| Field | Source | Purpose |
|-------|--------|---------|
| `is_private`, `is_archived` | Mirrored from Slack's own `list channels -format JSON` (same call, no extra cost) | Lets `register_matching` (below) exclude private/archived channels from bulk discovery |
| `creator`, `created` | Same call | Channel context surfaced in `export digest` (see `docs/DESIGN-export.md`) |
| `registered_at` | **This app's own bookkeeping** — stamped once, idempotently, by `channel_logic.register`/`register_matching` the moment a channel is first tracked | Fallback recency signal for backup ordering (see `last_posted` below) |
| `last_posted` | **This app's own bookkeeping** — set by `backup_logic.backup_channel` after a backup that actually found message data; left unset if the archive stayed empty | Real recency signal once available; `catalog_logic.effective_recency` prefers this over `registered_at` |

`registered_at`/`last_posted` have no Slack-API source at all — they exist purely so
`backup_logic.run()` can process a multi-channel run most-recently-active-first (real data) or
most-recently-discovered-first (no data yet), rather than in arbitrary `channels.json` order.

### Bulk registration (`channel_logic.register_matching`)

Generalizes the original single-channel `register()` to glob-based discovery: e.g.
`register_matching("f3*", "*", ...)` registers every new, public, non-archived channel across
every registered `f3*` workspace — intended to run nightly so newly-created public channels
(the original motivating case: `disc-it` going unnoticed in `f3pugetsound`) get picked up
automatically instead of requiring a human to notice and run `channel register` by name.

Three real bugs were found and fixed while building this, all in the shared `list_channels()`
call both registration and the catalog depend on — fixed centrally in
`src/slackbackup/slackdump.py` so no caller sees them again:

- **Plain DM leakage** — `list channels`, even with `-member-only`, returns plain
  direct-message conversations (`is_channel: false`, blank name, `D`-prefixed id). Filtered out.
- **Multi-person DM leakage (privacy-sensitive)** — group DMs come back with `is_channel: true`
  despite being a DM, a `C`-prefixed id, and a name that **embeds every participant's real
  username** (e.g. `mpdm-bgawthrop--stuart.donaldson--chris.knowlton-1`). Filtered out by name
  pattern (`mpdm-*`) — this would otherwise have been a real PII leak into `channels.json` and
  any catalog cache.
- **`shuttered*`-named channels** — this F3 community's own naming convention for a closed-out
  AO, which Slack's own `is_archived` flag does **not** reliably reflect (confirmed empirically:
  most `shuttered-*` channels in a real workspace were not actually archived). `register_matching`
  filters by name prefix (case-insensitive) in addition to the `is_private`/`is_archived` checks.

A bulk run against real data initially picked up ~720 channels including private ones and the DM
leaks above before these fixes landed; after fixing all three, a clean re-run against the same
workspace produced the expected ~380 legitimate public channels.

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
