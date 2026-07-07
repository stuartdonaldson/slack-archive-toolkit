# slackdump CLI — operational notes

Consolidated, hard-won knowledge about the `slackdump` binary (v4.4.0) gathered while
building this project's backup/export/file-harvesting tooling. Purpose: avoid
re-discovering the same gotchas, costs, and command behavior in a future session.
Organized by topic so a specific question ("how do I list channels without getting
throttled?") can be answered by Ctrl-F rather than re-reading the whole thing.

This is a **reference**, not a design doc — it doesn't say what *this project* does,
only what `slackdump` itself does/supports/costs. See `docs/DESIGN.md` (backup),
`docs/DESIGN-export.md` (monthly export), `docs/DESIGN-files.md` (channel catalog +
file/canvas harvesting) for how this project uses these facts.

---

## Workspace registration & sessions

- `slackdump workspace list` shows what's actually registered (has a cached, usable
  session) — this is **separate** from `~/.slackdump-tokens.json` (this project's own
  flat `{workspace: xoxc-token}` file, used only as input to `./slackbackup workspace
  register`). Having a token on file does **not** mean the workspace is usable yet.
- Registering a workspace (`slackdump workspace import`, wrapped by
  `./slackbackup workspace register` — see README.md's "Getting Started") needs **both**
  the `xoxc-` token *and* a fresh `xoxd-`
  session cookie pasted from the browser — the cookie is never persisted by this
  project (by design, it's sensitive and short-lived), so re-registering after a
  session expires always needs the user to fetch a new cookie manually. This can't be
  scripted around.
- Workspace naming is inconsistent between sources: `slackdump workspace list` may show
  a workspace as `f3pugetsound.slack.com` even though everywhere else in this project
  (`channels.json`, `~/.slackdump-tokens.json`) it's just `f3pugetsound`.
  `scripts/lib/select_workspace.sh`'s `select_workspace_or_die` already handles this by
  trying both forms — reuse it; don't assume either form works everywhere.
- `slackdump <command> -workspace <name>` overrides the "current" workspace for one
  invocation; `slackdump workspace select <name>` changes it persistently. Both accept
  either naming form via the same fallback logic above (only `select_workspace_or_die`
  encodes the *retry*, though — a raw `-workspace` flag will just fail if you guess the
  wrong form).

## `archive` / `resume` (per-channel, full history)

- `archive` is **only safe against an empty/new directory** — re-running it over an
  existing archive appends a duplicate chunk on top rather than overwriting (confirmed:
  message count doubled, every thread-root row 4x). Always: no existing
  `slackdump.sqlite` → `archive`; existing → `resume`.
- `resume -dedupe` has a **confirmed data-loss bug**: it deletes thread-root
  (`IS_PARENT=1`) message rows (verified by diffing against an independent fresh
  archive — 9/9 thread parents missing in a 55-message test channel). **Never use
  `-dedupe`.** Accept duplicate rows across resume cycles instead.
- `archive`/`resume` exit **0** and write a 0-message archive for a not-found or
  inaccessible channel ID — there is no non-zero exit code to detect a bad channel ID.
  Don't rely on exit code alone to validate `channels.json` entries.
- File attachments (`-files`, default **true**) and avatars (`-avatars`, default
  **false**) download as a side effect of `archive`/`resume` — no extra step needed.
  This includes **Slack Canvases** (see FILE table section below) — canvases are just a
  special file, not a separate slackdump concept.
- `archive`/`resume` against a single named channel does **not** require listing or
  touching any other channel in the workspace — cost scales with that one channel's
  message history, not workspace size.

## `convert -f export`

- Requires the source `slackdump.sqlite` to carry workspace/session metadata. A DB
  built via `convert -f database` from a raw Slack-export directory **lacks** this
  metadata, so `convert -f export` on it exits non-zero ("failed to get the workspace
  info: no data found") — even though it still writes correct day-file output. A DB
  built by a real `archive`/`resume` run has the metadata and exits 0. If you need a
  fixture for testing the export boundary, it must come from a real `archive`, not a
  `convert`-rebuilt one.
- Always writes a `users.json` (id → name/real_name/profile.display_name mapping) and a
  `channels.json` alongside the per-day message files — useful for resolving ids to
  human-readable names without a separate API call.

## `search files <query>` / `search messages` / `search all`

**This is keyword relevance search, not exhaustive enumeration.** Confirmed empirically
against the real `f3pugetsound` workspace:

| Query | Results |
|---|---|
| `filetype:quip` (alone) | **0** |
| `filetype:pdf` (alone) | **0** |
| `pax` | 28 |
| `help` | 18 |
| `ruck` | 9 |
| `ao` | 18 |
| `convergence` | 6 |
| `health` | 3 |
| `pax OR help` | **6** (fewer than either alone!) |
| `Regional` (an actual canvas title word) | 18, correctly including canvases + PDFs |

Conclusions:
- **`filetype:` modifier does not work standalone** — needs to be paired with real
  query text, at minimum in this CLI's invocation of the search endpoint. Don't rely on
  it to filter by type; filter the *results* by `mimetype`/`filetype` afterward instead
  (the FILE table carries both).
- **`OR` is not a boolean operator** — it's matched as a literal word, narrowing
  results (implicit AND across every term including "or" itself). There is **no
  multi-term-OR query**. To approximate "any of these N words," run **N separate
  single-term searches** and merge/dedupe the results (e.g. by file ID, or via
  `slackdump tools merge` into one target database) — not one combined query.
- Consequently, `search files` can only ever give **best-effort, not exhaustive**,
  coverage of a workspace's files. It's good for "probably most of them, cheaply,
  without indexing every channel's full history" — not for a completeness guarantee.
  For channels you already fully `archive`/`resume`, the local `slackdump.sqlite` FILE
  table is the complete, free source — don't use search for those.
- Search results land in the same `FILE`/`SEARCH_FILE`/`CHANNEL` schema as `archive`
  output, so downstream FILE-table queries work unchanged regardless of which command
  produced the database.
- Each search is cheap and fast (sub-second per query in testing) — the expense in this
  tool is `list channels` (below), not `search`.

## `list channels`

- **The per-invocation workspace flag is `-workspace <name>`, NOT `-w`.** `list channels`
  rejects `-w` with `flag provided but not defined: -w` (exit 2) — there is no short
  alias, and the flag goes *after* the subcommand (`slackdump list channels
  -member-only -workspace f3cascades`), not before it. On an expired session this same
  call exits **4** and prints `authentication details expired, relogin is necessary` to
  stderr — which is exactly how `scripts/preflight-auth.sh` detects stale workspaces.
- **`-member-only` is cheap.** Returned 52 channels for `f3pugetsound` in a couple of
  seconds, no rate-limit errors.
- **Without `-member-only` (i.e. "all public channels") is expensive and throttle-
  prone.** Same workspace, same call otherwise: **464 channels, 4m20s wall-clock,
  hit Slack's rate limit twice** (`got rate limited, sleeping, retry_after: 30s`).
  slackdump **auto-retries with the server's `retry_after` backoff** — it does not need
  custom backoff code wrapped around it, but it does mean a "full" channel listing is a
  multi-minute, occasional operation, not something to run on every backup invocation.
- This is almost certainly the root cause of "registering a channel by name took a long
  time and got throttled" in past sessions: looking up a channel that's public but not
  yet joined requires the expensive un-filtered listing as a fallback, since the cheap
  member-only cache won't contain it.
- `slackdump list channels` text output columns are only `ID`, `Arch` (archived y/n),
  `What` (channel name with `#`/lock-emoji prefix) — **no last-activity/last-message
  timestamp is available from this command**, at any cost tier. Getting last-posted-ts
  for a channel you don't otherwise archive would require a *separate, per-channel*
  API call (e.g. fetch latest message) — i.e. one call **per channel**, the same
  expensive-call-multiplied-by-channel-count pattern as the throttling above, just
  worse (400+ calls instead of 1). For channels you already `archive`/`resume`, this is
  free instead: `SELECT MAX(ts) FROM MESSAGE` locally, no API call at all.
- `scripts/register-channel.sh` already wraps the cheap member-only call with a
  plaintext, TTL-based cache (`~/.cache/register-channel/<workspace>.txt`, default
  900s) — reuse that pattern (and ideally that exact cache) rather than building a
  second one; see `docs/DESIGN-files.md` for how the channel catalog generalizes it.

## `FILE` table / Slack Canvases

(Schema as written by `archive`, `resume`, and `search files` — documented internal,
subject to change in future slackdump versions; treat as a convenience for ad hoc
inspection, not something downstream tooling should hard-couple to without re-checking.)

- A Slack **Canvas** is just a `FILE` row: `mimetype = 'application/vnd.slack-docs'`,
  `mode`/`filetype = 'quip'`, `pretty_type = 'Canvas'`. There is no separate
  "canvas" concept in slackdump's data model.
- `FILE.MESSAGE_ID IS NULL` → a **channel-level** canvas (the channel's pinned/standalone
  canvas, not attached to any message). Non-null → attached to that message (could be a
  thread reply too).
- The same file ID can appear as **multiple rows** (one per `CHUNK_ID`, i.e. once per
  backup/search pass that (re)discovered it) with identical `DATA`/size — this is *not*
  a content revision history, just repeated discovery. `LOAD_DTTM` per row is the
  closest thing to "when did we last see this file," not "when was it last edited."
- **Slack's file/canvas metadata exposes no real edit/revision history** through this
  API path — only a single `created`/`timestamp` (upload time). True canvas version
  history would require Slack's separate Canvas API, which slackdump doesn't use here.
- Downloaded file bytes land in `<archive-dir>/__uploads/<file-id>/<original-filename>`
  — already present and human-readable (canvases are saved as `.../Canvas` containing
  raw `<div class="quip-canvas-content">...` HTML).
- Non-image filtering is simply `mimetype NOT LIKE 'image/%'` — canvases are never
  image-mime, so "all canvases and non-image attachments" collapses to that one filter.

## `tools merge`

`slackdump tools merge [-check] <target dir> <source1> [source2 ...]` — merges
multiple archive/search-result databases from the **same workspace** into one
target. Empirically verified (SlackBackup-d02):

- **Target must already exist** (`<target dir>` is a directory with its own
  `slackdump.sqlite`, same shape as an `archive`/`search files -o` output dir —
  not a bare `.sqlite` path). `-check` runs a dry-run compatibility check
  without merging.
- **Does not deduplicate.** The tool's own help says so explicitly and
  recommends `slackdump tools dedupe` afterward if sources may overlap.
- **Fails on `search files` result databases**: `merging source "<dir>":
  getting channels: no data found`. Root cause confirmed by inspecting the
  schema — `search files` output has a `CHANNEL` table (same schema as
  `archive` output) but it's always **empty** (0 rows); `search files` only
  populates `FILE`/`SEARCH_FILE`, never `CHANNEL`. `tools merge` requires a
  non-empty source `CHANNEL` table to merge, so it can never combine two
  `search files` result databases, no matter the workspace.
- **Conclusion**: `tools merge` is not usable for combining
  `fetch-files.sh`'s per-search-term result databases. Don't attempt it.
  `fetch-files.sh` keeps each term's result directory separate;
  `build-file-index.sh` reads `FILE` rows across all of them directly instead
  of relying on one merged per-workspace database.

## General cost/risk summary

| Operation | Cost | Throttle risk |
|---|---|---|
| `archive`/`resume` one channel | scales with that channel's history only | low |
| `search files <term>` | sub-second per term | low |
| `list channels -member-only` | seconds | low |
| `list channels` (no member-only) | **minutes** (4m20s / 464 channels observed) | **high** — expect rate-limit backoff |
| per-channel "latest message" lookup, repeated across many channels | 1 API call × channel count | **high** if channel count is large |
