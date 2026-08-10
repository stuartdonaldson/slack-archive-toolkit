# PR #5 Recovery Plan — Calendar Reference, Channel Categories, Convert Without File Copy

Status: Draft — for review
Date: 2026-08-09
Source PR: [#5](https://github.com/stuartdonaldson/slack-archive-toolkit/pull/5) (`aff0b0a`, opened against an ancestor 78 commits behind current `main`; skipped/unmerged)

## Context

PR #5 was submitted by an external contributor (`andreBurnt`) after running the toolkit across six F3
workspaces (95 channels) to build a regional digest. It bundles three fixes that came out of that run.
The branch point (`59455a9`) predates the v6 digest schema, the sat-811 files sidecar work, and the ADR-0007
`topic`/`description` split — main has moved 78 commits since, so the diff no longer applies and GitHub
shows it as conflicting. This document evaluates each of the PR's three intents against current `main` and
recommends how to deliver each one, rather than attempting to merge or rebase the stale diff.

**Recommendation: close PR #5 with a comment pointing at this plan, and deliver the three intents as fresh
work against current `main`** (tracked as separate bd issues — see §Next Steps). A rebase/cherry-pick isn't
worth attempting: `_channel_context` and the digest manifest have been restructured since, and the PR's own
test expectations are written against the pre-v6 schema.

## Intent 1 — Calendar reference in the digest manifest

**Problem (still real):** an LLM render step invented a weekday for a date the source text never stated.
Anchoring `export_scope`'s date range with an explicit date→weekday map lets a render look the fact up
instead of guessing.

**Current state:** `_assemble_digest` (`src/slackbackup/export_logic.py:2068`) already builds `manifest{}`
from `date_from`/`date_to`, which are in scope at that call site. No architectural conflict — this is a
one-key addition to the existing dict at `export_logic.py:2112` (or as a manifest sibling to
`known_limitations`, `export_logic.py:2194`).

**Conflict found:** none functional. The only issue is naming — the PR's key is
`calendar_reference_2026`, hardcoding the year into the field name. Digests aren't bound to 2026;
recommend `calendar_reference` (or `manifest.date_reference`) with no year baked into the key.

**Action:**
- Port `generate_calendar_reference(date_from_str, date_to_str) -> dict[str, str]` as-is (pure stdlib
  `datetime`/`timedelta`, no dependency on anything that moved) into `export_logic.py`, renamed without
  the year suffix.
- Call it once in `_assemble_digest` and add the result under `manifest.calendar_reference`.
- Document the new manifest key in `docs/DESIGN-export.md`'s manifest section and
  `docs/llm-context/uploads/ingestion-contract.md` (schema-restatement rule, CLAUDE.md).
- No schema-version bump needed (additive manifest key, same pattern as other manifest sub-keys) — confirm
  against how `workspace_activity_index` was introduced, but a v6 → v6-additive precedent likely applies;
  flag for a human call if that's wrong.

## Intent 2 — Channel categories (`derive_channel_category` / `is_probably_bot_or_log_channel`)

**Problem (still real):** without a channel category, a render has to hardcode channel-name patterns to
know which channels are the events source vs. the culture source, etc.

**Current state / conflict:**
1. `_channel_context` (`export_logic.py:482`) has been restructured by ADR-0007 (v6): it now returns
   `topic` and `description` as distinct, unmerged fields (`description` = Slack's own `purpose`, not the
   PR's assumed `channel.get("description")`, which was the old pre-v6 merged field). The PR's
   `derive_channel_category(name, description)` call needs to be re-pointed at whichever of `topic`/
   `description` (or both) actually carries the classification signal — a product call, not just a
   rename.
2. **Layering mismatch (the real finding here).** `derive_channel_category`'s patterns
   (`ao-`, `event-`, `1st-f`/`2nd-f`/`3rd-f`, `mumblechatter`, `classifieds`, `nation_bot_logs`, ...) are
   F3-specific naming conventions, not general Slack concepts. `export_logic.py` is explicitly the
   general-purpose engine — region/workspace-specific logic already has a designated extension point:
   `src/slackbackup/handlers/` (see `handlers/__init__.py` docstring and `handlers/f3.py`), used today for
   `annotate_profile`/`build_leadership`. Hardcoding F3 taxonomy into `export_logic.py` would duplicate
   that separation the codebase already made once.
3. This was already anticipated and explicitly deferred in `docs/DESIGN-export.md` §Known Gaps
   (`docs/DESIGN-export.md:966`): *"if added, follow the existing `derive_leadership`-style pattern
   (heuristic value plus a `_basis` field), never an authoritative claim"* — i.e. exactly the handler
   pattern, not a bare function in `export_logic.py`.
4. `is_probably_bot_or_log_channel`'s activity half (`total_message_count > 0 and human total == 0`) can't
   be computed once at gather time the way the PR does it — current architecture recomputes activity
   per-slice for monthly digests (`_channels_for_slice`, `export_logic.py:1801`), after `channel_info` is
   already merged in. A channel could be all-bot-traffic in one month and have a real human post in
   another, so the "probably bot/log" activity signal is a per-slice fact, not a static one, if monthly
   digests are meant to reflect it accurately.

**Action:**
- Extend the handler contract in `handlers/__init__.py` with an optional third function, e.g.
  `classify_channel(name, description, topic) -> tuple[str, str]`, implemented in `handlers/f3.py` with
  the PR's exact pattern table (still a good heuristic set, just moved). No handler configured →
  `export_logic` should omit `channel_category`/`channel_category_basis` entirely (matching how
  `leadership` degrades to an empty section when `handler is None`) rather than emit `"unknown"` for every
  channel in a non-F3 workspace.
- Add `channel_category`/`channel_category_basis` to `_channel_context`'s output only when a handler is
  passed in (needs a handler parameter threaded through the gather functions, same as `build_leadership`
  already receives one).
- Compute `is_probably_bot_or_log_channel`'s activity component in `_channels_for_slice` (where
  `activity_fields`/`activity["_human_total_message_count"]` already live), OR'd with
  `channel_category == "bot_log"` from the static category. Static category alone should still be usable
  standalone (a channel named `*-bot-logs` is a log channel even in a month it happens to be silent).
- Decide (human call): is `channel_category` worth landing without the activity-derived bot flag as a
  first slice, given the layering rework is the larger lift? They can ship together or split into two bd
  issues.

## Intent 3 — `convert -files=false`

**Problem (still real, and cheap to fix):** `export digest`'s call to `slackdump convert -f export` dies
when Slack no longer has the attachment (deleted upstream) that the raw archive still references. The
digest is text-only, so there's no reason `convert` needs to copy file blobs at all.

**Current state:** `convert_export` (`src/slackbackup/slackdump.py:166`) is unchanged in shape (the PR's
one-line diff still applies almost verbatim; the surrounding function only gained a `timeout` parameter
via `_run`, unrelated). Traced all three callers:
- `channel_digest.py:68` (`channel-digest run`) — uses the converted export dir only for `users_map`/day
  files; file content comes from `export_logic._load_channel_files`, which reads `channel_dir`'s
  `slackdump.sqlite` `FILE` table and `__uploads/` directly (`export_logic.py:739`), never from convert's
  output.
- `export.py:193` (`export monthly`) — `export_transform` reads only messages/day files from the converted
  dir; no file-blob dependency.
- `export digest`'s own pipeline never calls `convert_export` directly in the current streaming
  architecture — confirm this at implementation time; if a call site still exists, it falls under the same
  message-only usage as the two above.

**Conflict found:** none. This is the safest, lowest-risk piece of the PR — the sat-811 files sidecar
(content extraction from `__uploads/`) is architecturally independent of `convert -f export`'s own file
copying, so `-files=false` cannot regress it.

**Action:**
- Apply the PR's one-line change directly:
  `["convert", "-files=false", "-f", "export", "-o", str(out_dir), str(channel_dir)]`.
- Update `docs/references/slackdump-cli-notes.md` (per CLAUDE.md: check before re-deriving slackdump CLI
  behavior) with the `-files=false` flag and why it's always passed.
- No flag/opt-in needed per the PR author's own tradeoff note ("exports never copy attachments now") —
  confirmed safe above, since no current consumer relies on convert's file copy. If a future export mode
  wants blobs, add a parameter to `convert_export` then; don't pre-build it now.

## Test/doc fallout common to all three

- `tests/test_export_digest_logic.py`'s two anchor tests the PR touched still exist
  (`test_build_digest_channel_context_is_none_when_catalog_never_warmed`,
  `test_build_digest_missing_archive_is_soft_skip`) but their expected dicts have moved to v6 shape
  (`topic`/`description` split, no bare `description` merge). New field expectations need writing against
  current fixtures, not copied from the PR diff.
- `docs/DESIGN-export.md` §Known Gaps (`:966`) entry for `channel_category` should be removed/resolved once
  Intent 2 ships, and its manifest section extended for `calendar_reference`.
- `docs/llm-context/uploads/ingestion-contract.md` needs the calendar_reference and channel_category fields
  restated (CLAUDE.md's schema-change rule).
- Any schema-version bump decision (manifest-only additive change vs. a new `slack-llm-digest-v7`) is a
  human call, not implied by precedent alone — ADR-0007 bumped to v6 for a rename/removal, not a pure
  addition; verify against an earlier additive-only manifest change (e.g. `workspace_activity_index`'s
  introduction) before deciding.

## Next Steps

1. Tracked as three bd issues (branch `sat-pr5-recovery`), each `--external-ref gh-5`:
   - **sat-rve** — calendar reference manifest key (small, no dependencies)
   - **sat-hds** — `convert -files=false` (small, no dependencies)
   - **sat-tdv** — channel category + bot/log flag via a new `handlers` classify function (larger —
     touches the handler contract, `_channel_context`, `_channels_for_slice`, and both gather-data
     functions)
2. Close PR #5 once the above land (or once enough of them land to cover the PR's intent), commenting with
   a link to this document and the bd issue IDs.
3. Human decision needed before starting sat-tdv: confirm the handler-based design direction above (vs.
   any alternative), and whether `channel_category` should degrade to absent-when-no-handler or to a
   generic `"unknown"` always.
