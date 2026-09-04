# DESIGN — DM / Group-DM Backup and Digest

Companion to `docs/DESIGN.md` (channel backup) and `docs/DESIGN-export.md` (export/digest
pipeline). Covers `dm register-matching`/`dm validate` (`dm_logic.py`) and how a DM/group-DM
conversation flows through the *existing*, unmodified backup and export pipelines via a
separate tracked-list file.

## Why DMs were excluded until now

`slackdump.py`'s `list_channels()` has always deliberately filtered DM conversations out of
every channel listing (see its own docstring): a plain 1:1 DM (`is_im`, blank name, `D`-prefixed
id) and a group DM (`is_mpim`, Slack-given name `mpdm-<user>--<user>--...-N`, embedding every
participant's real username) are both privacy-sensitive in a way an ordinary channel is not —
this project's git history was squashed once already to purge an earlier era's DM-id→user-id
mapping files (`channels-T*.txt`, see `docs/DESIGN.md`'s Solution Strategy). Adding DM backup
support is therefore a deliberate, scoped reversal of that exclusion, not just a new feature —
the design below keeps the same PII discipline (separate storage, gitignored, never mixed into
`channels.json`) rather than relaxing it.

## Solution Strategy: a second tracked-list file, not a flag

`channels.json` is `[{id, name, workspace}, ...]` — deliberately minimal, and consumed by
`backup_logic.run()` and `export_logic.select_channels()`/`build_digest()` with **no awareness
of what a "channel" actually is** beyond that shape. Rather than add an `is_dm`/`type` field to
`channels.json` and thread a filter through every consumer (backup, catalog, every digest job),
DM/group-DM conversations are tracked in a **separate file, `dms.json`, in the identical shape**.

This means:

- `backup_logic.run()`, `export_logic.select_channels()`, `export_logic.build_digest()`,
  `export_logic.build_user_profiles()` — **zero code changes**. Point any of them at `dms.json`
  instead of `channels.json` and they archive/export DM conversations exactly as they would
  channels, because nothing in that pipeline ever branches on the concept "channel" vs. "DM".
- Every *existing* digest (channel-driven, reading `channels.json`) is unaffected by
  construction — a DM conversation can never appear in it, because it's never in `channels.json`
  in the first place. There is no new exclusion filter to write or to get wrong.
- The one genuinely new capability — the `f3-dm-digest`, a **single document merging every
  workspace's DMs** — is just an `export digest` job (`jobs/f3-dm-digest.json`) whose
  `channels_file` is `dms.json` and whose `workspaces` is `["*"]`. No export-side code exists
  for it beyond that job file; `export_logic.select_channels()` already filters by workspace
  glob only (never by channel name), so a `*` glob against `dms.json` naturally spans every
  workspace's tracked DMs into one merged digest — exactly what `export digest` already does for
  channels across a multi-workspace glob.

What *is* new: `slackdump.py`'s `list_dms()` (the complement of `list_channels()`'s filter) and
`dm_logic.py` (discovery/registration/pruning, the DM counterpart of `channel_logic.py`).

## `dm_logic.py`

`register_matching(workspace_glob, dms_file, include_group=True)` mirrors
`channel_logic.register_matching()`'s add/prune shape, minus the parts that don't apply to DMs
(no private/archived/`shuttered*` concepts, no full-tier catalog):

- **Discovery** always uses the cheap **member-only** tier (`slackdump.list_dms()`) — a DM/group
  DM only exists in a listing you're already a member of by definition, so there is no
  "un-joined public DM" to discover the way `register_matching` discovers public channels via
  the expensive full-tier scan. No rate-limit risk, no separate cache needed.
- **Naming**: `channel_logic.validate()`/`save()`/`load()` are reused unchanged for `dms.json` —
  same `{id, name, workspace}` shape — which means every entry needs a non-empty `name` (it also
  doubles as the archive directory slug, `backup_logic.channel_dir()`). A group DM already has a
  usable Slack-given name (`mpdm-...`); a 1:1 DM's raw name is always blank, so it's synthesized
  as `dm-<other-user-id>` from the `user` field Slack's `is_im` entries always carry.
- **Pruning**: a tracked DM absent from a fresh listing (conversation closed, or removed from a
  group DM) is pruned as `"removed"`/`"missing"` — unlike channel pruning, there's no
  truncated-scan caveat to check first, because the member-only listing is a complete membership
  snapshot, not a scan that can plausibly come back partial.
- **`include_group`**: `--no-group` on the CLI tracks 1:1 DMs only, for an operator who wants the
  lower-PII-exposure subset (a group DM's name alone reveals every participant).

## Storage: `dms.json`, gitignored

Same location convention as `channels.json` (repo root), same reason for being gitignored — see
`.gitignore`'s comment on `dms.json`, which notes the *higher* PII sensitivity (a 1:1 entry's
name embeds one user id; a group entry's name embeds every participant's username, unlike
`channels.json` which the DM/group-DM filtering above exists specifically to keep out of).

## Backup and export — reused, not extended

```
./slackbackup dm register-matching 'f3*' --dms-file dms.json
./slackbackup backup run dms.json ~/slack-backups              # same backup_logic.run()
./slackbackup export digest --channels-file dms.json --workspace '*' --out f3-dm-digest.json
```

The nightly job (`scripts/nightly-backup-digest.sh`) runs `dm register-matching` and
`backup run dms.json` right after their channel equivalents, then the existing
`export digest --jobs jobs/*.json` step picks up `jobs/f3-dm-digest.json` (gitignored, like every
other real job file) automatically — no separate digest invocation needed.

`jobs/f3-dm-digest.json`:

```jsonc
{
  "type": "digest",
  "channels_file": "dms.json",
  "workspaces": ["*"],
  "days": null,
  "out": "~/slack-exports/f3-dm-digest-{as_of}.json",
  "users_out": "~/slack-exports/f3-dm-users-{as_of}.json",
  "files_out": "~/slack-exports/f3-dm-files-{as_of}.json",
  "leadership_handler": "none"
}
```

`leadership_handler: "none"` — the F3 leadership-title regex handler has no reason to run over
DM content, and jobs already default to `none` unless a job opts in (see
`docs/DESIGN-export.md` §Pluggable leadership handlers).

## Test plan

**Unit** (`tests/test_slackdump.py`, `tests/test_dm_logic.py`):

1. `list_dms()` extracts `is_im` and `is_mpim`/`mpdm-`-named entries that `list_channels()`
   filters out, from the same raw listing (one subprocess call shared via `_list_raw()`).
2. `list_dms(include_group=False)` excludes group DMs.
3. `list_dms()` always requests the member-only tier.
4. `dm_logic.register_matching()` discovers new 1:1/group DMs, synthesizes a 1:1 DM's name from
   its `user` field, skips already-tracked entries, prunes entries missing from a fresh listing,
   and skips unregistered workspaces — same shape as `channel_logic.register_matching()`'s own
   test suite.

**Not separately tested** (by design, not a gap): `backup_logic.run()` and
`export_logic.build_digest()`/`select_channels()` against `dms.json` — these paths are already
covered against `channels.json` by their own test suites, and nothing in this feature adds a new
branch to either function for them to exercise differently.
