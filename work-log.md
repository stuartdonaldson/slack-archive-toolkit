## 2026-06-22 13:16:40

### Summary:
Implemented the monthly JSON exporter designed in docs/DESIGN-export.md (SlackBackup-ckz, closed). Added scripts/export-monthly.sh (entry point: arg parsing, archive lookup, exit 2 if missing, orchestrates `slackdump convert -f export` then the transform) and scripts/lib/export_transform.sh (range bounding by parent ts, month bucketing, thread nesting, sealed-month idempotency via .last_backup stamp or high-water-mark fallback). Added committed fixtures under scripts/test_fixtures/export-archive/ and scripts/test_export_monthly.sh covering all 6 design test-plan items plus seal-stamp behavior — all passing. Validated the slackdump convert -f export boundary against a real archive DB (built via convert -f database from the fixtures), confirming day-file layout and verbatim field preservation. Updated docs/CONTEXT.md Core Capabilities and reconciled the Non-Goals scope note to admit this read-only export as the first piece of the downstream phase.

### Key Learnings:
slackdump convert -f export requires workspace/session metadata in slackdump.sqlite — a DB built via `convert -f database` from a raw export dir lacks it and convert -f export exits non-zero (though it still writes correct day files). Real `slackdump archive` DBs carry this metadata and convert succeeds. Saved as bd memory slackdump-convert-export-needs-workspace-meta. Follow-up tracked: SlackBackup-026 (write .last_backup stamp in backup.sh).

## 2026-06-22 17:27:04

### Summary:
Ran a full backup + monthly export pass for all 15 tracked channels (4 workspaces) — backups clean, exports landed in ~/slack-exports. Along the way found and fixed three real bugs in scripts/lib/export_transform.sh: (1) `jq --argjson` blowing past ARG_MAX on high-volume months, also silently leaving corrupt 0-byte files behind; (2) a data-loss bug where a month "sealed" by the high-water mark was skipped forever even if a thread in it later got a new reply — fixed by gating skip on content-match, not just seal status; (3) a crash on bot/system messages with no `user` field. Also reworked the export schema per request: each message now carries `display_name` (resolved from slackdump's `users.json`) alongside the raw `user` id, with Slack-API noise (blocks, client_msg_id, team, user_profile, metadata, etc.) stripped out. Added test coverage for all of the above (13 passing cases) and updated docs/DESIGN-export.md. Discovered the entire project tree had never been committed to git (only the bd-init commit existed) and committed it, plus the export fix, plus this session's doc work — no remote configured, so nothing pushed anywhere.

Confirmed canvases and non-image file attachments for the 15 tracked channels are already downloaded as a side effect of `slackdump archive`/`resume` (no new work needed there). Scoped out a much bigger ask — canvas/file harvesting + a channel catalog across ALL channels in the f3* workspaces, not just tracked ones — through plan mode and live spikes against the real Slack API. Found `slackdump search files` is keyword-relevance search only (no `filetype:` modifier, no `OR` operator — `pax OR help` returns fewer results than either term alone), and that `list channels` without `-member-only` is throttle-prone (4m20s / 464 channels, confirmed rate-limited, auto-backoff). Session ran low on quota before implementation, so wrote up the full design instead.

### Key Learnings:
slackdump's `search files` cannot exhaustively enumerate files — it's relevance search, not a listing API; best-effort multi-term-merge is the only way to approximate broad coverage. `list channels -member-only` is cheap (seconds); without it, expensive and rate-limited (minutes). A Slack Canvas is just a FILE row (`mimetype: application/vnd.slack-docs`) with no real edit/revision history exposed via this API path. Captured all of this in new docs/references/slackdump-cli-notes.md (the "don't re-discover this" reference) and docs/DESIGN-files.md (the not-yet-implemented channel-catalog + file-harvesting design), with README.md and CLAUDE.md updated to point at both so they're easy to find next session.

## 2026-06-23 18:09:43

### Summary:
Removed shell scripts already ported to the Python rewrite (backup/register/run-backups/validate/export-monthly/catalog-channels + their tests/libs), keeping only the not-yet-ported files/search scripts and `install-slackdump.sh`. Added a repo-root `./slackbackup` entry point shimming to the `uv1` venv. Audited f3pugetsound's full channel catalog (562 total, 150 member, only 10 tracked) and, on request, registered 28 new channels matching `ai-bro`/`event-*`/`otb*`/`ao*` across all f3* workspaces (49 channels total in channels.json) — recovered from a self-inflicted mid-registration `channels.json` truncation using conversation history. Ran a full backup across all 49 channels; diagnosed `f3pugetsound/all-pax` as a channel slackdump can archive successfully but always returns zero messages for (reproduced twice, not corruption).

Implemented two new export commands: `export digest` (merges the trailing N months across every `f3*`-glob workspace into one chronologically-sorted JSON document, enriching each message with `message_url`/`channel_id`/`posted_at_utc`, no top-level merged author table) and `export users` (full per-workspace user-profile roster, noise-stripped). Both default their output to `~/slack-exports/`. Added best-effort leadership-role inference scanned from the full roster (not just posters) into the digest's `leadership` field, then revised it per `docs/llm-leadership-improvement.md` feedback: deduped by (region, f3_name, position) into a `leadership.by_region` rollup alongside the raw per-profile matches, widened role-keyword coverage well beyond Nantan (Weasel Shaker, 1st/2nd/3rd F, Comz, Site/Region Q, AOQ, SLT, OIC, etc.), and fixed name/region parsing for compact hyphen (`Name-Region`) and parenthetical (`Name (Region Role)`) display-name formats.

### Key Learnings:
- `slackdump convert -f export`'s `users.json` is workspace-scoped (the full cached roster, ~1,800+ users), not filtered to a channel's posters — confirmed empirically, important for both the digest's display-name resolution and the new leadership scan.
- `git rm` is atomic across all listed paths — if any path fails to match/has local modifications, *none* of the files in that invocation are removed, which silently looked like partial success and caused a multi-file restore scramble.
- `slackdump archive` can report success ("Recorded workspace data") while writing a `MESSAGE` table with 0 rows for a channel it has no real access to read messages from — exit code alone doesn't confirm a non-empty archive.
- Deliberately kept `needs_confirmation: true` on deduped `leadership.by_region` entries even though the feedback doc's example showed `false` — the same self-reported display name repeated across a person's per-workspace accounts isn't independent corroboration, just the same unverified claim echoed.

## 2026-06-24 09:07:52

### Summary:
Ported `search messages` from `scripts/search-messages.sh` to Python (`search_logic.py` + `search.py`), now taking an explicit workspace name or glob as a required argument instead of an implicit f3* scan; removed the superseded shell files. Added usage examples and default-output-location notes to every CLI subcommand's `--help` text across all modules (workspace, channel, catalog, backup, export, files, search). Fixed unrendered Slack mrkdwn (`*bold*`, `_italic_`, `~strike~`, `` `code` ``) in the search-results HTML report by rendering it as real HTML tags after escaping, so user content can never be reinterpreted as raw HTML. Diagnosed and fixed a real recurring bug: `backup_channel` was calling `resume` on archives that captured 0 messages, which fails forever because resume reads its continuation point from the archive's own (nonexistent) checkpoint — never self-healing even once a channel got real posts. Fixed by detecting 0-message/unreadable archives and wiping + re-archiving fresh instead of resuming. Verified live against the 9 channels that were stuck (all-pax, 5 event-* channels, 3 new f3northsea channels) — all now exit cleanly. Regenerated the f3* digest (2349 messages, 60 channels, 0 missing archives). Test suite: 130/130 passing.

### Key Learnings:
slackdump's `resume` command determines its continuation point from session/chunk bookkeeping recorded inside the archive's own sqlite file during a prior `archive` run — it is not a property of the live Slack channel. A 0-message archive has no such checkpoint, so `resume` always errors out locally before ever making an API call, regardless of how much real content later appears in the channel. This makes the failure permanent and silent unless the calling code explicitly detects and recovers from the empty-archive case (delete the stale directory, then run a fresh `archive`, never `archive` directly on top of an existing directory since that duplicates data per the documented slackdump quirk).

## 2026-06-24 15:04:54

### Summary:
Added backup logging/visibility and last-post-date tracking: timestamped log lines + per-run summary in `backup_logic.py`, plus catalog fields `registered_at`/`last_posted`/`effective_recency` so multi-channel backup runs process most-recently-active channels first. Exposed the new fields in `catalog show` (split into `last_posted_live` vs `last_posted_cached`/`registered_at`). Then did a full documentation review/rewrite: `docs/DESIGN.md` and `docs/CONTEXT.md` were badly stale (still described an abandoned GitHub Actions/NDJSON/private-repo architecture); rewrote both to match the actual local Python CLI, added a Mermaid data-flow diagram to DESIGN.md showing Slack -> slackdump binary -> this app's modules -> local files, and confirmed by inspection that no code calls the Slack API directly (only via `slackdump.py`). Updated `docs/DESIGN-export.md` with new sections for `export digest`/`export users` (catalog-sourced channel context, file content extraction, leadership-inference vs. slack_roles). Updated `docs/DESIGN-files.md` to correct an inaccurate "Status: implemented" claim — only the catalog was ported to Python; Canvas/file harvesting remains shell-only. Fixed a self-contradicting README intro. Deleted an orphaned stale `docs/DESIGN copy.md`. No code changes in this doc pass; full test suite still 186/186 passing.

### Key Learnings:
Documentation drift in this repo was much worse than expected — CONTEXT.md's Non-Goals section explicitly ruled out features (search/render) that were already shipped, and its Use Cases described a system that was never built. Worth a periodic doc-vs-reality audit rather than waiting for it to be this far gone. Also: this session used TaskCreate for tracking instead of `bd`, which the project CLAUDE.md mandates exclusively — worth defaulting to `bd` for any future multi-step project work tracking.

## 2026-06-24 18:55:46

### Summary:
Built the operational tooling to recover from an interrupted backup and make subsequent runs both observable and fast. Added `backup sync-catalog` to backfill `last_posted`/`registered_at` from local archives with zero API calls (ran it live: 383 channels, 120 got real last_posted, 263 got a registered_at stamp), and a human-readable `catalog list` command (name, last-updated, message count, optional description/topic columns) - required adding a raw `topic` field to the catalog schema alongside the existing folded `description`. Fixed a real bug: `backup_logic._log()` used a bare `print()`, which Python fully block-buffers once stdout is redirected to a file - explains why `tail -f` on the backup log looked stale for minutes at a time. Fixed with `flush=True` plus `PYTHONUNBUFFERED=1` in the nightly script as defense-in-depth. Diagnosed (with the user pushing back twice on my first two wrong explanations) that the real bottleneck during bulk backup isn't archive-vs-resume cost or data volume - it's Slack's rate limit, confirmed empirically (a channel with 0 messages still took 12.7s to archive; durations cluster in tight 13s/40s/70s bands, i.e. 1x/3x/5x a fixed backoff unit) and confirmed the limit is bucketed per-workspace. Implemented `backup_logic._interleave_by_workspace()`, a greedy largest-remaining-queue-first scheduler (same idea as the "task scheduler" problem) so `backup run` alternates across workspaces instead of draining one workspace's rate-limit bucket completely before moving to the next. Ran a full live before/after comparison: pre-interleave 2.53 channels/min vs. interleaved 3.64 channels/min over a full 383-channel run (105.2 min total, 263 archives, 120 resumes, 0 failures) - a real ~44% throughput improvement. Regenerated the full f3* digest afterward and spot-checked catalog-sourced channel context (description/creator/created_at) and Canvas content extraction, both confirmed working. 204 tests passing (was 186 at session start).

### Key Learnings:
Don't trust a plausible-sounding explanation for a performance bottleneck without checking the actual distribution of the data - "archive scales with channel history" sounded right but a single data point (a 0-message channel taking the same 12.7s as everything else) disproved it immediately, and the real driver (rate-limit backoff, quantized into 1x/3x/5x bands) was visible just from `uniq -c` on the duration column. Also: Python silently full-buffers stdout once it's not a tty - any long-running process whose progress is being tailed from a redirected log needs an explicit flush or PYTHONUNBUFFERED, or the log looks broken even though nothing is actually wrong.

## 2026-06-26 15:42:15

### Summary:
Added Slack profile `title` as a leadership signal: `_clean_user()` now emits `title`, and `derive_leadership()` parses comma-separated title segments as independent role entries (each with basis=title, confidence=high). Distinguished AO-scoped vs regional roles in title parsing: Site Q, AOQ, OIC now emit `possible_ao` (workout location) alongside `possible_region`; regional roles (Nantan, Weasel Shaker, Comz Q, etc.) emit only `possible_region`. Wired `export users` into the nightly digest script and updated docs/newsletter-prompt.md with guidance on separating regional vs AO/Site Q roles in leadership snapshots. Fixed two bugs in export_logic.py: guarded None in sort key (`r["f3_name"] or ""`) and updated type annotations to use `AbstractSet[str]` instead of bare `set[str]`.

### Key Learnings:
Profile `title` fields often contain comma-separated multi-role entries (e.g., "Redmond Ridge Site Q, Redmond Comz Q") that should be parsed as independent roles per segment so they group correctly by region in leadership rollups. AO-scoped role detection (Site Q vs regional Comz Q) requires prefix detection — the role name alone doesn't carry the scope; the location segment (e.g., "Redmond Ridge") must map to a known AO to disambiguate.

## 2026-07-03 09:52:40

### Summary:
Investigated why a Slack Canvas ("REGION INFO", F08235A783C) wasn't appearing in regular backups for f3pugetsound. Traced it to channel `shuttered-region-redmond` (C07CW28MTRP), a channel outside `channels.json`'s tracked set, left behind by an f3pugetsound region migration to its own workspace. Confirmed `slackdump archive` does capture channel-level canvases (FILE.MESSAGE_ID IS NULL) for tracked channels regardless of whether they're linked in a message, but untracked channels get nothing.

Built a new general-purpose CLI command, `slackbackup channel-digest run <workspace> <pattern> <out_dir>` (`src/slackbackup/channel_digest.py` + `channel_digest_logic.py`), that archives every channel matching an fnmatch glob and writes a single JSON digest of surviving messages/files/canvases with authors resolved via the workspace roster. Deliberately a manual, on-demand tool - not wired into the nightly backup cadence.

Iterated the output format from markdown to a schema-versioned JSON document (`slack-channel-digest-v2`) matching the project's existing digest conventions (export_logic's schema_version pattern), since the primary consumer is an LLM, not a human skimming a table. Added `merge_digests()` so re-running the command against the same out_dir merges into the existing digest rather than overwriting it - tracks `first_seen_at`/`last_seen_at` per channel/message/file and `content_last_changed_at` per file, so a future re-run can show what's new or changed since the last pass.

Ran it against f3pugetsound's 70 `shuttered-*` channels: 19 had surviving content (mostly orphaned channel-level canvases; a couple with a few residual messages), 0 errors. Digest written to `~/slack-backups/f3pugetsound-shuttered-digest/f3pugetsound-shuttered-digest.json` (outside the repo, since it contains real names/chat content). Tracked as SlackBackup-ie2 (closed). 236 tests passing.

### Key Learnings:
Slack's channel-to-workspace migration moves message history but does not reliably carry a channel's standalone/pinned Canvas with it (no message to migrate along, since channel canvases have FILE.MESSAGE_ID IS NULL) - the source "shuttered-*" channel silently keeps orphaned canvases that never make it to the destination workspace. f3pugetsound's channels.json tracks only about half its channels (232 of 464 in the full catalog cache); anything outside that set gets zero backup coverage, tracked-vs-untracked - not message-vs-canvas - is the actual gap.

## 2026-07-06 08:00:31

### Summary:
Added a self-contained "report job" mechanism on top of `export digest`, driven by operator-owned `jobs/*.json` files (gitignored per `.gitignore`'s existing "Operator's real report/digest job definitions" comment). Each job can now fully specify its own `archive_root`, `channels_file`, `workspaces`, `days`, and `out` (with an `{as_of}` template placeholder), overriding the CLI's `--archive-root`/`--channels-file` fallback flags rather than requiring them. Added `export_logic.load_job()` (validates `type: "digest"`, raises loudly on unsupported types), `export_logic.expand_job_path()` (`~`/`$VAR` expansion for any path read out of a job file), and `export_logic.resolve_job_out()` (applies `{as_of}` templating then `expand_job_path`). Added `selector_logic.expand_path_selector()` as shared comma+glob-to-filesystem-paths logic, mirroring the existing `matches_selector`/`split_selector_list` paradigm already used for workspace/channel selectors - a literal (non-glob) path that matches nothing is passed through as-is so a typo surfaces as a clear "file not found" rather than silently vanishing, while a genuinely-empty wildcard match is dropped. Wired `export digest --jobs '<comma-separated globs>'` into the CLI (quoted so the shell doesn't expand the glob itself) and updated `scripts/nightly-backup-digest.sh` to forward `--jobs "$REPO_ROOT/jobs/*.json"` after the existing blanket digest/users export, with all job-file parsing living in Python rather than bash/jq. Verified end-to-end against the real `jobs/f3-nation.json` (added an `archive_root` field to it) running with zero `--archive-root`/`--channels-file` flags on the command line at all.

### Key Learnings:
This project's selector paradigm (comma-separated list + glob, `matches_selector`/`split_selector_list` in `selector_logic.py`) generalizes cleanly from "filter a known candidate list" (workspaces/channels) to "expand actual filesystem paths" (job files) - same split-on-comma step, just `glob.glob()` instead of `fnmatch.fnmatch()` per part, with `glob.has_magic()` needed to distinguish a legitimately-empty wildcard match from a typo'd literal path.

## 2026-07-06 13:09:07

### Summary:
Extended the report-jobs mechanism (from the earlier session on 2026-07-06) so a job can now also deliver a companion user-profiles file, and refactored all F3-specific leadership logic out of `export_logic.py` into an isolated, pluggable handler. Added `src/slackbackup/handlers/` package: `handlers/f3.py` holds every F3-specific regex/title-parsing/leadership-rollup function moved verbatim from `export_logic.py` (title patterns, AO-scoping, tenure-modifier detection, region names, `derive_leadership`, `_build_leadership_by_region`), exposed through a two-function handler protocol (`annotate_profile(display_name, title)` for per-user tagging, `build_leadership(profiles_doc)` for the digest's aggregate rollup); `handlers/__init__.py` is a small registry (`handlers.get(name)`, `handlers.NAMES`) so a future non-F3 region/workspace can register a sibling module without touching the export engine. `export_logic.build_user_profiles(..., handler=None)` now optionally tags each profile with `derived_leadership`, defaulting to no tagging (general-purpose, unchanged default behavior); `export_logic.build_digest(..., handler=<f3 by default>, profiles_doc=None)` delegates the whole `leadership` section to the handler (empty structure when `handler=None`) and accepts a precomputed `profiles_doc` to avoid re-converting every workspace's archive twice. `export.py`'s `export digest` gained `--leadership-handler` (defaults to `f3` for a plain/manual run, preserving the README/newsletter-prompt.md workflow that already depends on `leadership.by_region` being populated by default); jobs get their own `leadership_handler` field (default: none - opt-in, since a job may target a non-F3 workspace like `dungeons-of-finn-hill`) and a new `users_out` field - when present, a companion user-profiles JSON (tagged if a handler applies) is written alongside the digest from one shared `build_user_profiles` call. Updated `jobs/f3-nation.json` and `jobs/f3-pugetsound.json` with `users_out` + `leadership_handler: "f3"`; `jobs/dungeon-fh.json` gets `users_out` only. Moved the ~20 F3 pattern-matching unit tests (`test_derive_leadership_*`) into a new `tests/test_f3_handler.py` importing `handlers.f3` directly; `test_export_digest_logic.py` keeps the general `build_digest`/`build_user_profiles` integration tests untouched, since the default handler preserves prior output exactly (all 240 tests passing, zero test-behavior changes needed for the integration tests). Verified end-to-end against real archived data (f3kirkland, via a scratch job file): the `users_out` file carries per-profile `derived_leadership` tags and the digest's `leadership.by_region` matches prior inline-logic output exactly.

### Key Learnings:
When extracting embedded domain-specific logic (F3's leadership inference) out of a general-purpose engine into a pluggable handler, defaulting the *library-level* function's handler parameter to the concrete handler (not None) preserves every existing direct-caller test unchanged, while still making the seam real and overridable - the "isolate but don't force a default-off regression" tradeoff only needed to bite at the CLI/job layer, where the two entry points (manual command vs. job file) legitimately want different defaults: manual command defaults to "f3" (matches the historically F3-only documented workflow), job files default to "none" (since a job might target an unrelated workspace, tagging it with F3-specific regex would just produce noise).

## 2026-07-07 11:40:40

### Summary:
Evaluated and resolved the four Copilot review comments on PR #4 (feat/preflight-auth-check).
- Dismissed #1 (`scripts/preflight-auth.sh:44` "backwards" stderr redirect) as a false positive — `2>&1 >/dev/null` correctly captures stderr and discards stdout; verified empirically before replying.
- Fixed #2: added `"high": 3` to `_CONFIDENCE_RANK` in `handlers/f3.py` so title-derived high-confidence roles upgrade a rollup group (and a medium can no longer downgrade a high).
- Fixed #3: `_groups_to_list` now derives `is_current` from the resolved status (former→False, current→True when status=="current", else None) instead of a fixed per-bucket value.
- Fixed #4: corrected "Weazel Shaker"/"Commz Q" → "Weasel Shaker"/"Comz Q" in `docs/newsletter-prompt.md` to match canonical `handlers/f3.py` patterns.
- Added rollup test `test_build_digest_title_high_role_wins_confidence_and_currency` covering #2 and #3. Full suite: 250 passed.
- Posted threaded replies to all four Copilot comments via the GitHub API.

### Key Learnings:
- Copilot cited `export_logic.py:656/723`, but that leadership code has been refactored into the still-untracked `src/slackbackup/handlers/f3.py`. The version currently pushed to PR #4 still has this code in `export_logic.py`, so the fixes won't surface on the PR until the untracked `handlers/` package (plus related pending changes) is committed and pushed. Did not commit — the fix depends on untracked code intertwined with a larger uncommitted refactor; left the commit decision to the user.
- `2>&1 >/dev/null` (order matters) is the correct idiom to capture stderr while discarding stdout inside command substitution; `>/dev/null 2>&1` is the genuinely-backwards form.

## 2026-07-07 14:01:55

### Summary:
Implemented SlackBackup-2ut (tiered backup cadence) end-to-end and closed the issue.
- Added `BACKUP_CADENCE_TIERS` (single editable `(min_age_weeks, cadence_days)` constant) and a pure `should_check_tonight(entry, record, today)` filter in `backup_logic.py`: cadence keyed off `last_posted` age (active nightly, 8–12wk every 2d, >12wk/empty every 10d), deterministic stagger via stable `sha1(channel_id)` hash, `last_checked` downtime backstop. Skips are a pure catalog lookup — channel sqlite is never opened.
- Added `catalog_logic.record_check()` to stamp `last_checked`/`last_action` per channel per run without touching `last_posted`.
- Wired the filter into `backup_logic.run()` (new `today` param for frozen-date testing; `-full` bypasses cadence); run summary now reports a not-due skip count.
- Follow-up per user request: per-channel log lines now carry a per-workspace progress counter `[X/Y in <workspace>]` (both the "backing up" and cadence "skipping" lines).
- Tests: cadence tiers/boundaries, stagger coverage-within-cadence, backstop, run skip/record/full-bypass, progress counter, and `record_check`. 272 tests pass.
- Docs: updated DESIGN.md (module responsibilities, catalog fields, orchestration) and OPERATIONS.md (new "Tiered cadence" nightly-backup subsection).

### Key Learnings:
- Python's built-in `hash()` is salted per-process (PYTHONHASHSEED), so it can't drive a stable per-channel due-night — used `int(sha1(channel_id).hexdigest(), 16) % cadence_days` so a channel's staggered night is identical across runs/processes.
- Steady-state simulation over the issue's real channel distribution confirmed the AC numerically: dormant/empty load ~34 checks/night (target ~35) while all 188 active channels stay nightly, and no single night processes a whole tier.
- Cadence is keyed strictly off `last_posted` (real message age), not archive-file mtime (which churns nightly from resume/wipe) and not `registered_at` — so empties/never-posted correctly fall through to the oldest tier instead of looking fresh.
- Not committed: the working tree carries substantial unrelated in-progress work and the branch is `feat/preflight-auth-check` (not this feature); left the landing decision (new branch off main vs. current branch vs. user-staged) to the user.

## 2026-07-07 17:13:57

### Summary:
Reviewed the last two weeks of work against the docs and reconciled the drift, then landed the whole branch. Found three features shipped on `feat/preflight-auth-check` but undocumented/stale in the docs and fixed all of them in one docs-only commit (`f2d1232`): (1) report jobs (`export digest --jobs`) — new §Report jobs in DESIGN-export.md with the full job-field table, plus a Core-Capabilities bullet, README digest note, and DESIGN.md module-inventory row; (2) `channel-digest run` — new §Channel digest in DESIGN-files.md, Core-Capabilities bullet, README subsection, DESIGN.md module row; (3) the pluggable leadership-handler refactor — new §Pluggable leadership handlers in DESIGN-export.md and corrected the stale attribution that still placed `derive_leadership`/`_build_leadership_by_region` in `export_logic.py` (they moved verbatim to `handlers/f3.py`). Also added `selector_logic.py` and `handlers/` to DESIGN.md's Level-1 module table. Confirmed the already-documented items (auth pre-flight/keep-alive, tiered cadence) needed no change.

Committed only the 5 doc files (left the unrelated untracked files — slackdumpbot/, f3-culture.md, f3-it-infrastructure docs — alone), pushed to update the existing open PR #4, then rewrote PR #4's title and body: the branch had grown far past its "auth pre-flight" title, so the description now covers all four pieces (auth, tiered cadence, export/channel refactor, docs). Merged PR #4 into main with a merge commit (`b596988`, preserving all 7 commits) per user's choice, synced local main, and deleted the merged branch locally + remotely with a prune.

Finally investigated and removed the stray local `master` branch: it was the original pre-public history (no shared ancestor with main — main was re-rooted as a squashed commit before going public). Verified nothing salvageable — obsolete PLAN-bd.md init stub, the purged-PII channels-T*.txt channel-ID dumps, and old shell scripts superseded by the Python rewrite — then force-deleted it (local-only, never on remote). Repo now clean: only main remains, in sync with origin/main.

### Key Learnings:
- `git merge-base A B` returning empty (unrelated histories) piped to `xargs git log` silently runs against HEAD instead of nothing — misleading. Two branches with no common ancestor is the tell that one was re-rooted (here: main squashed to a fresh initial commit to purge PII before going public), so the pre-squash line survives only as a detached local branch.
- A long-lived feature branch can silently accumulate scope far past its name/PR-title; before merging, reconcile the PR's title+body to the actual commit set so main's merge history isn't misleading. Doc-vs-code drift check caught three shipped-but-undocumented features on the same branch.

## 2026-07-08 02:58:00

### Summary
Debugged and fixed `channel register` bulk-path asymmetry: comma-separated or glob-based channel registration was silently skipping archived/private channels with zero feedback to the operator. Implemented per-channel skip reason reporting (`"archived"`, `"private"`, `"shuttered-name"`, `"already-registered"`), added `[private]` indicator to `channel list`, updated docs (UC-2 in CONTEXT.md), and extended test coverage.

### Changes
- `src/slackbackup/channel_logic.py`: `register_matching()` now returns `"skipped": [{id, name, workspace, reason}]` (glob-matched channels report why they weren't added; non-matching channels silently omitted); `list_for_workspace()` adds `"private"` field to each row
- `src/slackbackup/channel.py`: `_register()` prints per-channel skip reason; summary line includes skip count; `_list()` appends ` [private]` suffix for private channels; updated CLI help text
- `docs/CONTEXT.md`: UC-2 wording updated to reflect skip reasons are now reported, not silent
- `tests/test_channel_logic.py`: 6 test functions extended/added to verify skip reasons and private flag (9 new assertions); all 273 tests passing

### Root Cause (Investigation)
Both `social` and `new-channel` on f3northsea are flagged `is_archived: true` in Slack's metadata. Bulk/comma path filters out archived/private/shuttered/already-registered channels by design (per docstring), but only accumulated `"added"`, losing visibility into *why* a glob-matched channel didn't get registered. Single-name/ID path does no such filtering — hence ID-based registration succeeded while name-based failed.

### Verification
- `pytest tests/test_channel_logic.py -v`: 35/35 pass
- `pytest tests/`: 273/273 pass
- Manual: `./slackbackup channel register f3northsea 'social,new-channel'` now prints `skipped social (C09TFHFHPQR) in f3northsea — archived` and `skipped new-channel (C09SM7AJ89M) in f3northsea — archived`, plus summary `0 new channel(s), 2 skipped, across 1 workspace(s)` instead of bare `0 new channel(s)`
- Manual: `./slackbackup channel list f3northsea` shows ` [private]` suffix for private member-only channels (verified with synthetic test)

### Design Notes
- Skip reasons have priority order (private > archived > shuttered-name > already-registered) so a channel reports exactly one reason
- Non-glob-matching channels never appear in `skipped` (glob can span hundreds; only report actual matches)
- Catalog already carries `is_private` field via `_channel_fields()`; no schema change needed


## 2026-07-08 15:04:17

### Summary:
Investigation + design session (no code changes this session). Reviewed nightly.log
state and worked through the tiered-cadence bootstrap and digest-consolidation designs.

- **nightly.log review:** Confirmed the 2026-07-08 run is the first executing under the
  tiered-cadence code (it has the new `[X/Y in workspace]` progress markers; the
  2026-07-07 summary line lacks the `not-due skip(s)` field, so it ran an older build).
  Zero not-due skips this run is *correct* — `last_checked` was unpopulated everywhere,
  and `should_check_tonight` treats `last_checked=None` as unconditionally due (retention
  backstop). Staggering activates on the next run once `last_checked` is seeded. Verified
  against the catalog cache (149/464 f3pugetsound stamped mid-run).
- **Ordering confirmed:** `run()` sorts by `effective_recency` desc (most-active-first,
  real `last_posted` else `registered_at`), then `_interleave_by_workspace` round-robins
  across workspaces to spread per-workspace rate-limit load.

### Design Decisions:
- **Cadence bootstrap:** Keep two fields with two jobs — `last_posted` drives the tier
  (data recency), `last_checked` gates due-ness (run recency). Do NOT collapse to
  `last_data`: a stale channel's last-post date never moves, so gating on it would either
  re-pull nightly or risk retention. Correct seed = `last_posted`←MAX(ts),
  `last_checked`←today (only where an archive exists; leave None for never-archived so
  they get a real first pull). Seeding `last_checked` from an *old* date (posting/oldest)
  trips the backstop and forces a full sweep — the trap to avoid. Empty channels: None →
  already maps to oldest (>12wk) tier, no synthetic date needed. Durable fix: add
  `last_checked` seeding to `sync_catalog_from_local` so cold starts skip the 128-min sweep.
- **Digest concurrency:** `export digest` is read-only against archives (converts into a
  `tempfile.TemporaryDirectory`), safe to run alongside a live backup. `channel-digest`
  runs its own `slackdump archive` and DOES contend — manual/rescue tool only.
- **channel-digest vs export digest:** Agreed they are effectively mergeable —
  `channel-digest` ≈ `export digest` with archive-first + catalog-glob selection + scratch
  raw-dir + no-cadence-write + channel schema. Four flags to fold, with one hard
  constraint: on-demand/rescue pulls must NOT leak into nightly cadence bookkeeping
  (`channel-digest` bypasses `backup_one` today, so it never stamps last_posted/last_checked).

### Key Learnings:
- The `~13s/channel` cost is slackdump's own per-channel API/rate-limit work, not a sleep
  we control — the only lever on nightly runtime is staggering (pull fewer channels), not
  faster individual pulls.

## 2026-07-09 12:39:45

### Summary:
Renamed and relocated repository from /mnt/c/dev/SlackBackup to /home/stuar/proj/SlackArchiver (folder renamed SlackBackup -> SlackArchiver). Merged scattered Claude Code history dirs into the new location and
rewrote the matching ~/.claude.json project references. Performed by the
move-to-proj tool, not an interactive session.

## 2026-07-11 06:08:56
_session 61e1e06e-492e-4ed4-bed2-5e9dd8861fd5 · v3 · 07-11_

### Objective 1: Explain where the nightly script's `~/slack-exports/f3-digest` file comes from
Rationale: User noticed `scripts/nightly-backup-digest.sh` produced an `f3-digest` file in addition to a digest per `jobs/*.json` and couldn't find `f3-digest` specified in any job file — needed to know if it was redundant config drift or intentional.
Outcome [internal]: Traced to `export digest`'s non-`--jobs` code path (`src/slackbackup/export.py`): `--workspace-glob` defaulted to `"f3*"` and `--out` defaulted to the literal `~/slack-exports/f3-digest-<as-of>.json`, both hardcoded, not derived from `channels.json`. This was a separate catch-all digest across every `f3*` workspace, distinct from the per-recipient job digests.

### Objective 2: Rename `--workspace-glob` to `--workspace` on `export digest`/`export users`, remove its `"f3*"` default
Rationale: "adding -glob is excess specification, it should just be a --workspace parameter, and there should be no default you should have to specify the workspace." The investigation in Objective 1 surfaced this hardcoded default as the root design smell.
Outcome [user-facing]: `export digest` and `export users` now take `--workspace` (still glob/comma-selector syntax); `export users` requires it, `export digest` requires it unless `--jobs` is given — matching the existing `--archive-root` required-unless-jobs pattern. Updated help/epilog text, README.md, docs/CONTEXT.md, docs/DESIGN-export.md.
Outcome [developer-facing]: Added a regression test (`test_digest_direct_path_requires_workspace_when_no_jobs`) via red→green TDD; kept the argparse `dest="workspace_glob"` so internal call sites and existing tests needed no further churn. All 274 tests pass. Tracked and closed as bd `SlackBackup-8k5`.
Outcome [user-facing]: Updated `scripts/nightly-backup-digest.sh` to pass `--workspace 'f3*'` explicitly on its digest/users calls so the flag change didn't break the nightly run (the user subsequently removed that catch-all digest/users step from the nightly script themselves, separately from this session's work).

### Objective 3: Clarify `keepalive.sh` prerequisites and reference it explicitly from README  [accreted]
Transition: New question raised once the nightly-script rename work was done, about a different script (`scripts/auth-refresh/keepalive.sh`) referenced in that same file.
Rationale: User wanted the headless session-refresh helper's prerequisites documented and confirmed visible from the top-level README, not just docs/OPERATIONS.md.
Outcome [internal]: Enumerated keepalive's prerequisites (Node.js on PATH or via nvm fallback, one-time `npm install` for `@playwright/test`, pre-existing Chromium cache, `SLACKDUMP_AUTH_PROFILE`/`SLACKDUMP_TOKENS`/`SLACKDUMP_BIN` env vars, and a prior interactive `npm run refresh` login since `--keepalive` can only extend an existing session, never establish one).
Outcome [user-facing]: README.md's §Authorization callout now explicitly names `scripts/auth-refresh/keepalive.sh` and notes it's already wired into the nightly script, alongside the existing pointer to docs/OPERATIONS.md for full detail.

## 2026-07-11 21:49:57
_session bb14c476 · v3 · 07-11_

### Objective 1: Reconcile the bd board with the actual code — close stale, implemented, and non-actionable issues
Rationale: The user suspected the tracker had drifted from reality — "look at 'bdls --ready' it looks like many of these have already been implemented" and, later, "i still see several issues claimed an in progress, what about those?" Goal was to verify each open/in-progress issue against committed code and close what no longer represents real work, so nothing hangs around indefinitely: "i don't want things hanging around indefinitely."
Outcome [internal]: Closed 7 issues after per-issue code verification. Ready queue: 026 and 4my done (see Obj 2), 8ew rejected as external (Slack returns 0 messages for the admin-restricted all-pax channel — a permissions issue, not tooling; the resume-from-empty consequence already had a shipped workaround). In-progress queue: fac, jqb, t8i, d70 were all stale — implemented and committed (c5e8f5f, 0bfe94d, the Python channel-register rewrite, e47b74e/PR#4 respectively) but never marked closed. bd board now clear except dependency-blocked issues.

### Objective 2: Complete the two ready-queue issues that turned out to be real unfinished work
Rationale: Reconciliation surfaced two issues that weren't actually done, and the user directed completing them rather than deferring: "if there is value we should just go ahead and do it." 026: the exporter read a <channel-dir>/.last_backup seal stamp that nothing ever wrote, so it always fell back to the message high-water mark and rewrote a quiet channel's last active month on every run. 4my: README was otherwise fork-ready but lacked the one documented deliverable, slackdump-view browse commands.
Outcome [user-facing]: README gained a "Browse the archive locally" section documenting `slackdump view <archive-root>/<workspace>/<channel>` (read-only local viewer, no token).
Outcome [developer-facing]: Added backup_logic._write_last_backup() — a git-durable UTC stamp (content, not mtime) written after every successful archive/resume path (full, first-archive, wipe+re-archive, resume); helper mkdirs defensively so the test fakes that don't create dirs still exercise it. Two tests added; full suite 276 passing.
Outcome [internal]: Updated docs/DESIGN-export.md §Sealing signal and the gaps table to mark the seal stamp implemented (both had tracked it as an unimplemented follow-up).

### Key Learnings:
bd's auto-export tries to `git add .beads/issues.jsonl` on every close, which is gitignored here — emits a harmless "paths are ignored" warning each time; the close is still recorded in the bd DB.

## 2026-07-13 14:25:09
_session d4f24abb · v3 · 07-13_

### Objective 1: v2 design review and improvements for LLM use of digest output
Rationale: The digest must "preserve and organize evidence rather than make unreliable semantic inferences" — Slack users continue discussions through new top-level messages, so the extractor's job is to keep enough chronological and source context for a downstream LLM to infer those links, never to guess them itself. Recommendations were required to be grounded in the whole repo, not isolated field changes.
Outcome [internal]: Design recommendation delivered, grounded by sampling real archives: reactions on ~20% of messages, edited on ~7%, and Slack message unfurls (quoted url/author/text of an earlier message — the only explicit cross-message reference evidence Slack records) all silently dropped by _clean(); plus a correctness gap — a thread whose parent predates the export window is entirely absent even when its replies are recent.
Outcome [developer-facing]: 8 execution-ready beads filed (SlackBackup-7jn/efk/s1n/4ao/lwx/ugs/tdq + pex backlog) with file/line specs, acceptance criteria, dependency wiring, and model routing cues ([haiku-ok] title tags; model:haiku label on s1n) sized so Sonnet/Haiku could execute them standalone.

### Objective 2: bd-run-beads — reusable runner executing beads in clean sessions with the appropriate model, including work-log capture  [accreted]
Transition: with the beads filed, the question became cost-effective execution: "i'd like a general purpose script that can be reused, and uses cues such as the model in the title or model in the label ... give it the bead to implement and it would sort through the dependencies to get the right order."
Rationale: Deterministic orchestration shouldn't cost model tokens (a Haiku /loop orchestrator was rejected); one fresh small-context session per bead is cheaper than one long session, and sequential execution is required anyway since a dependency tree touches the same files. Hard external gates (tests pass, bead actually closed) make cheap models safe. After the first real run: "we should also make sure the output and progress is logged with sufficient info to support debugging and troubleshooting." For capture: "i don't want to re-implement that skill to do this, i want to reuse it" — so the worker session invokes /work-log itself (single-objective session = the skill's no-confirmation case, and its mechanical session-id capture points at the transcript that did the work).
Rejected: initial bash implementation — ported to Python after "is bash the right tool to use for this or would python be better?"; the bash version already delegated every JSON read to embedded python3 heredocs. The black-box test suite (fake bd/claude via BD_BIN/CLAUDE_BIN) validated the port unchanged.
Outcome [user-facing]: scripts/bd-run-beads.py — resolves transitive blocks-dependencies deps-first (deduped, cycle-detected), routes models label > title-tag > --default-model, dry-run plan, restartable (closed beads skip), per-run debug logs under .bd-run-beads/ (run.log, per-bead stream-json transcripts, stderr, test-gate output, live tool-call/cost progress), --work-log auto|on|off with a warn-only capture check.
Outcome [developer-facing]: scripts/test_bd_run_beads.sh, 30 fixture-driven assertions; beads SlackBackup-j7b/dbp/tct closed across three commits.
Outcome [user-facing]: The digest-v2 tree ran end-to-end through the tool: 7/7 beads completed in separate worker sessions (commits 8891e36..d30421b, schema now slack-llm-digest-v2 + ADR 0001), pushed.
Open: the 7 worker sessions predate the work-log integration, so they are unlogged (backfill candidate via extract_context.py digest); /code-review over the accumulated digest-v2 diff (29cf818..d30421b) still pending; SlackBackup-hjo (stale .venv shims from the repo move) open.

### Key Learnings:
claude CLI: --allowedTools is variadic and swallows a trailing positional prompt — deliver headless prompts via stdin; -p with --output-format stream-json requires --verbose.
After a repo move, venv shims keep absolute shebangs to the old path: executable-but-dead. Probe test commands (pytest --collect-only, exit 0 or 5) instead of trusting -x.

## 2026-07-13 10:57:11
_session c6b06d84 · v3 · 07-13 · backfilled_

### Objective 1: Digest v2: include threads whose replies fall in scope (fix cross-period thread blindness) — SlackBackup-7jn
Rationale: `select_messages_in_range()` admitted a thread only when the parent ts fell inside the export window, so a thread parented before the window that received in-window replies was entirely absent from the digest — revived/long-running conversations vanished. The monthly exporter already handled the analogous late-reply case; the digest never did.
Outcome [user-facing]: A thread is now included when the parent OR at least one reply has ts in range; when only replies are in range the full thread is emitted with `in_scope: false` on the parent record. `_channel_activity()` excludes `in_scope: false` parents from root_message_count, participant sets, and first/last timestamps.
Outcome [developer-facing]: Tests updated in tests/test_export_digest_logic.py; full suite 279 passing. Committed `8891e36`, closed, not pushed (per run-scoped instruction).

## 2026-07-13 11:39:46
_session 6c3f789d · v3 · 07-13 · backfilled_

### Objective 1: Digest v2: per-channel seq giving deterministic flat chronological order — SlackBackup-4ao
Rationale: Digest messages nest replies under parents and sort top-level entries by root ts, so the true channel timeline isn't directly readable. A per-channel monotonic sequence number gives a deterministic flat reconstruction without duplicating records — needed for a downstream LLM to infer relationships between top-level continuation messages.
Outcome [developer-facing]: `build_digest()` flattens each channel's emitted records (every root plus nested reply), sorts ascending by ts, and assigns `seq = 1..N` in place; `manifest.counting_rules` documents seq semantics. Full suite 279 passing. Committed `4aaec03`, closed, not pushed.

## 2026-07-13 11:41:22
_session 6d8bac57 · v3 · 07-13 · backfilled_

### Objective 1: Digest v2: preserve reactions, edited, subtype, and unfurl evidence on digest messages — SlackBackup-efk
Rationale: `_clean()` reduced messages to ts/user/display_name/text/files, silently dropping evidence verified present in real archives — reactions (~20% of sampled messages), edited flags (~7%), subtype, and Slack unfurls (the only explicit cross-message reference evidence Slack records). Scope guard: `export_month` shares `_clean()` and must not change monthly output, since new fields would churn every sealed month file.
Outcome [developer-facing]: Added `_clean(msg, users_map, evidence=False)` keyword param; `evidence=True` passed only from `select_messages_in_range()`, so `export_month` is untouched. Full suite 286 passing. Committed `5755eaa`, closed, not pushed.

## 2026-07-13 11:43:13
_session 21515257 · v3 · 07-13 · backfilled_

### Objective 1: Digest v2: channel_url, message-file ids, and message anchors on channel files — SlackBackup-lwx
Rationale: Three additive joins needed so digest consumers can link back into Slack and correlate message-attached files with the channel-level files list, distinguishing message attachments from standalone channel Canvases.
Outcome [developer-facing]: Added `digest_channel_url()` helper (channel_url on every channels[] entry); `_clean()` files projection now keeps file `id`; `_load_channel_files()` selects MESSAGE_ID and emits `message_ts` when non-null (null means a standalone Canvas), deduping in favor of MESSAGE_ID-anchored rows. 6 new tests; full suite 292 passing. Committed `25240dd`, closed, not pushed.

## 2026-07-13 11:48:25
_session d5c7eb2a · v3 · 07-13 · backfilled_

### Objective 1: Digest v2: thread_ts on replies and Pacific-local timestamps — SlackBackup-s1n
Rationale: Two mechanical additive fields needed so a reply record is self-describing once extracted from its nesting, and so timestamps read in the workspace's local time without requiring the downstream LLM to convert UTC.
Outcome [developer-facing]: `_enrich_for_digest()` now threads `parent_ts` through recursion so every reply carries `thread_ts` equal to its parent's ts (root messages do not); added `_format_local_pacific()` (zoneinfo, stdlib) producing `posted_at_local` on every message and reply, including correct DST offset (-08:00 Jan, -07:00 Jul). Full suite 294 passing. Committed `283c13c`, closed, not pushed.

## 2026-07-13 11:51:30
_session ca180a40 · v3 · 07-13 · backfilled_

### Objective 1: Digest v2: mentions/links extraction and per-workspace user_index — SlackBackup-ugs
Rationale: Message text keeps raw Slack tokens — `<@U123>` mentions are unresolvable inside the digest with no id-to-name map, and `<url|label>` links need parsing — so deterministic extraction was needed without ever modifying the text field itself.
Outcome [developer-facing]: `_extract_mentions`/`_extract_links` parse `<@U...>` and `<url>`/`<url|label>` tokens, wired into `_clean()` under the `evidence=True` seam; link `type` resolves to `slack_message` (with target_channel_id/target_ts), `slack_file`, or `external`. `_collect_referenced_ids`/`_build_user_index` build a per-workspace `user_index` scoped to ids actually referenced (never merged across workspaces or the full roster). Full suite 304 passing. Committed `2e4bfef`, closed, not pushed.

## 2026-07-13 11:55:57
_session a22afff8 · v3 · 07-13 · backfilled_

### Objective 1: Docs+ADR: digest v2 schema in DESIGN-export.md, slack-ingestion.md prompt update — SlackBackup-tdq
Rationale: Documentation needed to catch up once all six implementation beads landed — the shipped `slack-llm-digest-v2` schema, the additive-evolution design decision, and the LLM-facing ingestion prompt all still described v1.
Outcome [internal]: docs/DESIGN-export.md now documents the shipped schema field-for-field (in_scope, evidence fields, thread_ts, posted_at_local, seq, channel_url/message anchors, mentions/links, user_index) and marks the Known Gaps row for v1's missing evidence as resolved. New docs/adr/0001-digest-v2-additive-evidence.md records the additive-evolution decision (rejected: flat message-array redesign, prompt-side-only fixes).
Outcome [developer-facing]: docs/slack-ingestion.md now points at `posted_at_local` instead of asking the LLM to convert UTC, and documents the new evidence fields. Full suite 304 passing. Committed `d30421b`, closed, not pushed.

## 2026-07-13 19:35:00
_session e5706656 · v3 · 07-13_

### Objective 1: Finish digest v3 condensation (green phase of SlackBackup-vv0)
Rationale: Prior session left red-phase tests uncommitted (3 failing by design); "the following is the final work from a prior session, finish this off please and test it." v3 drops `posted_at_utc` (redundant with `posted_at_local`'s offset and `ts`) and writes the digest compact — measured v2 waste was ~26% indent whitespace plus ~1.0 MB of redundant timestamps. `message_url` deliberately kept per ADR-0001: the LLM must never construct a `p<ts>` link.
Outcome [user-facing]: Digest now emits `schema_version: slack-llm-digest-v3`, compact-serialized, without `posted_at_utc`; `export_month`/`users_out` stay pretty-printed.
Outcome [developer-facing]: `_enrich_for_digest`/`build_digest`/`_run_digest` updated; `counting_rules.posted_at_local` note added; docs/adr/0002-digest-v3-condensation.md written (adr-quality-check passed); DESIGN-export.md v3 section + resolved-gaps row; slack-ingestion.md v2→v3. All 3 red tests green, suite green.

### Objective 2: Cross-workspace mention index + Block Kit mention fix  [accreted]
Transition: User interrupted the final real-digest verification run with a new spec — a compact per-PAX mention index — and decided via Q&A to fold it into the still-uncommitted v3 change ("Fold index into v3", top-level digest key, "Stay at v3").
Rationale: "Make it easy to answer: where a PAX is mentioned … without duplicating message text or precomputing every possible report." Identity unification restricted to deterministic evidence (email, exact/variant-normalized F3 name, real-name/username support); conflicting evidence flagged `ambiguous`, never merged — this narrows ADR-0001's "all merging is LLM-side" boundary, recorded as ADR-0003. SlackBackup-rie (Block Kit backblasts lose their *PAX*: mentions because extraction only read `msg.text`) was pulled in as a prerequisite: the spec's own sample message (ao-heritage-park ts 1783887179.871339) is the confirmed rie bug case.
Rejected: Persisting raw emails for matching — `_clean_user` has always stripped them deliberately; instead profiles gain `email_hash` (truncated SHA-256, one-way), the only email-derived value in any output.
Outcome [user-facing]: Digest gains top-level `mentions` index (aliases/accounts/match_confidence/workspaces→channels→message_ts, ts-only); bot-posted Block Kit backblasts now contribute their PAX mentions.
Outcome [developer-facing]: `build_mentions_index` + `_block_texts` + `_normalize_name`/`_match_name`/`_identity_conflict` in export_logic.py; `email_hash` in `_clean_user`; 15 new red-phase tests written first, then green (suite: 320 passed); ADR-0003; DESIGN-export.md §Mentions index + sample JSON + gap rows; slack-ingestion.md identity guidance now defers cross-workspace merging to the index's confidence flags.
Open: Real-archive regeneration/verification and the single v3 commit + bead close-out (1sx/vv0/du5/rie) deferred to SlackBackup-1cw (sonnet-ok) — the regen run was declined twice this session, so nothing is committed yet.

### Key Learnings:
Raw slackdump `S_USER` rows carry `profile.email` for nearly every user (1941/1943 in f3kirkland) even though every exported document strips it — deterministic cross-workspace matching is possible without ever persisting an address.

## 2026-07-13 20:24:29
_session 03e6fde0-b969-4bbb-af83-c2e03b453248 · v3 · 07-13_

### Objective 1: bd-run-beads: move commit/close from the headless session into the runner
Rationale: A headless run in another repo (RankChoiceVoting) stalled because git commit isn't on any allowlist a `-p` session can approve, so the session finished work but couldn't commit or close its bead, stranding the rest of the dependency tree's beads. Privileged bookkeeping (git commit, bd close) had to move out of the model session, which cannot be trusted to gate its own unattended actions, and into the runner, which enforces it after its own gates pass.
Outcome [developer-facing]: `session_prompt()` now opens with an explicit "this session is unattended" statement and ends with a step forbidding commit/push/close, instead of instructing the session to do them. After a session exits 0 and the test gate passes, the runner itself computes tree-changed/bead-closed state via `git status --porcelain` (excluding `--log-dir` via a pathspec when the log dir is inside the repo), and either: skips (already closed, tree unchanged), dies naming the bead and transcript (no-op: tree unchanged and bead still open), or runs `git add -A` + `git commit -m "<title> (<id>)"` + `bd close <id>` itself and re-verifies the close. Added a pre-loop dirty-tree guard (refuses to start if the tree has changes outside `--log-dir`, unless `--allow-dirty`, which logs a sweep warning). `scripts/test_bd_run_beads.sh` reworked: fake `bd` now supports `close` and tolerates `update`; fake `claude` no longer touches bd/git, it just drops a `work-<id>.txt` marker (or nothing, under `NO_CHANGES=1`) to simulate a session's file changes; execution/gate/dirty-guard cases now run inside real temp git repos via a new `mk_repo` helper. All 41 assertions pass (`./scripts/test_bd_run_beads.sh`).
## 2026-07-14 03:30:00
_session 36115d1f · v3 · 07-14_

### Objective 1: bd-run-beads default --allowedTools and npm test detection (SlackBackup-y3l)
Rationale: Unattended sessions need a permission allowlist that covers exactly the commands the session prompt mandates, without requiring every caller to pass --allowed-tools by hand; and JS/TS projects should get npm test auto-detected the same way Python projects get pytest, without ever running the full suite as a detection probe.
Outcome [developer-facing]: --allowed-tools default changed from "" to None so an unset flag now computes Bash(bd:*), Bash(git add/status/diff/log/rev-parse:*), plus Bash(<test_cmd>:*) when a test gate is active; an explicit value (including "") is still used verbatim. detect_test_cmd() gained an npm-first candidate (package.json declares scripts.test and npm is on PATH) ahead of the existing pytest candidates, detected via presence checks only, never by executing npm test.
Outcome [developer-facing]: Added fake-claude ARGS_DUMP capture plus three new test cases to scripts/test_bd_run_beads.sh covering the default allowlist contents, explicit passthrough, and npm auto-detection; ./scripts/test_bd_run_beads.sh passes (57 assertions).

## 2026-07-14 03:35:00
_session fd027cf8 · v3 · 07-14_

### Objective 1: bd-run-beads: permission-denial reporting, BLOCKED/HANDOFF protocol, recovery messaging (SlackBackup-ccs)
Rationale: Follow-on to SlackBackup-daq/-y3l; the RankChoiceVoting run.log evidence showed an unattended session denied git commit six times then said it would "wait for approval" (meaningless headless), and the runner only reported "session ended without closing the bead" — failures needed to be self-describing with a human handoff path.
Outcome [developer-facing]: session_prompt() now instructs the worker session to record a `bd update --notes="HANDOFF: ..."` and end its final message with a `BLOCKED: <reason>` line instead of retrying denied commands or waiting; run_session() parses each stream-json event once, tracks tool_use id -> command brief, detects denied tool_result blocks (matching "requires approval" and shell-safety rejection text) and logs them live as "permission denied: <command>", and returns (rc, session_id, result_text, denials).
Outcome [developer-facing]: main()'s per-bead loop gates on a BLOCKED line in the final result text before any git operation (leaving the tree uncommitted and the bead open), and every bead-failure path (session rc, test gate, BLOCKED, no-op, close verification) now calls a new print_recovery_block() that reports bead id/status, staged+unstaged change count, collected permission denials, a "claude --resume <session-id>" hint, and the rerun-resumes-here note.
Outcome [developer-facing]: test_bd_run_beads.sh's fake claude gained DENY_ONCE=1 (emits a denied git-commit tool_use/tool_result pair) and BLOCKED=1 (emits a BLOCKED result line) modes, plus a fixed session_id for --resume assertions; added cases covering live denial logging in an otherwise-successful run, BLOCKED failing the bead pre-commit with the reason echoed, and the recovery block's shape on an existing failure path. All 66 assertions pass.

## 2026-07-13 21:08:08
_session 13ee7ff1-b801-4f80-9476-0e8222cbedb9 · v3 · 07-13_

### Objective 1: Finish and verify SlackBackup-du5 (digest v3 mention index), then close out the whole v3 change
Rationale: du5's code/tests/docs were already complete in the working tree from a prior session, but the final AC ("real digest regen shows the index present and well-formed") and the commit/close-out were explicitly deferred to a separate bead (1cw) marked safe for a Sonnet session. Picking up du5 meant finishing that deferred verification rather than re-doing implementation.
Outcome [developer-facing]: Verified against real archives — regenerated f3-pugetsound (17.2MB vs 22.6MB v2 baseline, 15998 messages/383 channels), dungeon-fh, and f3-nation digests; confirmed schema_version v3, no `posted_at_utc` field anywhere, `mentions` index well-formed (642 entries: 631 high, 11 ambiguous, correct structure), the known Block Kit backblast (f3kirkland ao-heritage-park, ts 1783887179.871339) now carries all 14 mentions and is indexed, and zero raw email leakage across 13,087 user profiles (all carry `email_hash`). Full suite green (320 tests).
Outcome [user-facing]: Digest consumers (the newsletter LLM prompt) get a smaller v3 digest file plus a top-level cross-workspace mention index for "where/when is this PAX mentioned" queries.
Outcome [internal]: Committed all v3 work as one commit (cc5f2db) and closed five beads together — SlackBackup-1sx, vv0, du5, rie, 1cw — since they were all facets of the same uncommitted change.
## 2026-07-18 00:00:00
_session aaba9b40 · v3 · 07-17_

### Objective 1: Filter due channels before the backup loop, not during it
Rationale: The cadence-based skip logic ran inside the per-channel processing loop, so skipped channels still occupied a slot in the recency sort, cross-workspace interleaving, and per-workspace X/Y progress counters — making progress counts and interleave spacing inaccurate for the channels actually being backed up. Moving the `should_check_tonight` filter to a pre-pass, before sort/interleave, keeps those downstream calculations scoped to only the channels really processed.
Outcome [developer-facing]: `run()` in src/slackbackup/backup_logic.py now filters entries for cadence-due status first, then sorts by recency and interleaves only the due set; progress counters (`ws_totals`/`ws_seen`) and interleave order reflect only processed channels. Total-channel count in the final summary log preserved via a `total_entries` count captured before filtering. All 47 backup-related tests pass unchanged.

## 2026-07-22 10:11:22
_session ba389005 · v3 · 07-18→07-22_

### Objective 1: Add `--workspace`/`--channel` subset selectors to `backup run`
Rationale: Started from "what's a quick way to update one or more channels and regenerate the f3pugetsound digest only?" — the only path was a hand-filtered channels.json or knowing channel IDs. Developer chose the durable fix: "yes do the enhancement to backup", and clarified the channel selector's shape mid-implementation — "the channel should be able to use wildcards and comma separated channel names". Filters apply before the catalog warm-up and cadence/recency pipeline (digest `--workspace` semantics); both AND together; an explicit selector matching nothing raises rather than silently backing up zero channels.
Outcome [user-facing]: `backup run channels.json <root> --workspace f3pugetsound --channel '1st-f,mumble*'` now backs up a subset; empty match exits 1 with a clear message; omitting both is byte-identical to prior behavior.
Outcome [developer-facing]: `backup_logic.run()` gained `workspace_selector`/`channel_selector` via `selector_logic.matches_selector`; 5 new tests; `docs/CONTEXT.md` capability note. SlackBackup-0z2 (closed). Full suite 325 passed.

### Objective 2: Audit the nightly log for correctness and performance options  [accreted]
Transition: developer redirected to operations once the code change landed — "look at the ~/slack-backups/nightly log and see if everything worked as expected and if there are any options you see for improving performance".
Rationale: Establish whether the unattended backup+digest is healthy and where the wall-clock time actually goes before proposing any optimization.
Outcome [internal]: 2026-07-21 run was functionally clean — 391 channels, 0 failures, all 3 digests regenerated with 0 missing archives. Surfaced one defect (keepalive.sh exit 126, see Obj 3) and quantified the performance profile: ~229 of 264 processed channels cluster at a fixed ~13s floor (≈68% of the 74-min backup), processing is strictly sequential despite per-workspace rate limits, and f3pugetsound is ~47% of the work. Recommended cross-workspace parallelism (~2.4× estimated) as the main lever; per-channel-floor investigation as a measured second.
Open: parallelism enhancement recommended but not filed or implemented.

### Objective 3: Fix keepalive.sh and reset auth  [accreted]
Transition: the log audit found keepalive.sh had been failing `Permission denied` (exit 126) for 12 nights; developer directed the fix + a live auth reset — "fix keepalive.sh and run it so we reset our auth".
Rationale: The headless auth keep-alive never ran, so sessions survived only by cookie longevity — one rotation from a stranded backup. Restore the exec bit (git-tracked mode) and run it to prove the path.
Outcome [user-facing]: `keepalive.sh` exec bit restored (staged `100644→100755`); ran clean (exit 0), cookie still valid, 8/8 profile-present workspaces re-registered; preflight confirmed all 9 valid. f3nation (absent from the browser profile) then registered manually from a pasted token+cookie — developer supplied the `xoxd-` cookie in-chat despite the caution, so a credential-rotation reminder was issued.
Open: f3nation is a separate identity from the shared-cookie set — whether the account is the same was left unresolved here.

### Objective 4: Add a targeted workspace selector to refresh-auth  [accreted]
Transition: onboarding f3nation into the persistent profile via `npm run refresh` meant clicking ENTER through all 9 workspaces; developer wanted it scoped — "can you do an npm refresh on f3nation specifically? i don't want to have to manually login again to each workspace".
Rationale: refresh-auth had only all-or-stale modes. Positional workspace name(s) now scope the run and force just those open regardless of probe state, folding a single workspace into the profile so headless keep-alive picks it up thereafter — without touching the other 8.
Outcome [user-facing]: `npm run refresh -- f3nation` refreshes only the named workspace(s); names normalize like the CLI (case/`https://`/`.slack.com`); unknown name exits 1 before any browser. README documented.
Outcome [developer-facing]: pure `selectWorkspaces()`/`normalizeWorkspace()` in `auth_logic.mjs` (5 new tests, 18 total pass); CLI wiring in `refresh-auth.mjs` verified live up to the browser boundary. SlackBackup-b31 (closed).
Open: a dry-run keep-alive showed the profile now parses 9 teams (was 8) and would register f3nation with the *shared* cookie — validity of that for f3nation is unverified; a controlled real-keepalive+preflight test was offered, not yet run. Nothing from this session is committed or pushed.

### Key Learnings:
slackdump imposes a fixed ~13s per-channel floor on archive/resume independent of new-message volume — the dominant cost of a multi-channel backup, not data transfer.
keepalive keys off the *parsed* team count in the persistent Chromium profile's `localConfig_v2` (`parseXoxcTokens`), not a raw leveldb substring match — the profile string can linger for a workspace that no longer parses as a team; the authoritative check is `node refresh-auth.mjs --keepalive --dry-run`.
## 2026-07-23 00:00:00
_session 99a0714d · v3 · 07-23_

### Objective 1: Split the f3pugetsound digest job into one document per calendar month
Rationale: The nightly f3pugetsound job produces one complete merged digest across all workspaces/channels; the user wanted it broken down by month instead, with the constraint that "as new content is added, replies may come in the following month, so a reply belongs in the month where the original message started."
Outcome [developer-facing]: Added `export_logic.build_monthly_digests` + `partition_messages_by_month`, refactoring `build_digest`'s body into shared `_gather_digest_data`/`_assemble_digest` phases so both entry points reuse the same channel-loading and assembly logic. A message's month is decided by its thread root's ts, not its own ts, so a reply landing in a later calendar month stays nested under its parent in the parent's month file rather than getting its own entry or being double-counted.
Outcome [user-facing]: New `export digest --split-by-month` CLI flag and job-file `split_by_month` field; `out`/`--out` must contain a literal `{month}` placeholder, validated up front (`load_job`/`_digest`) to avoid one file being silently overwritten every month.
Outcome [developer-facing]: 16 new tests (bucketing rule including the cross-month-reply fixture case, per-month activity recomputation, CLI wiring, job validation); full suite 337 passed. `docs/DESIGN-export.md` gained a "Monthly digest splitting" section.
Outcome [internal]: `jobs/f3-pugetsound.json` (gitignored operator config) switched to `split_by_month: true` with `out` now containing `{month}`, so the actual nightly job matches the request.
## 2026-07-23 12:00:00
_session 99a0714d · v3 · 07-23_

### Objective 1: Render CHANGELOG.md for the period since the last cut
Rationale: User asked to "update changelog" following the split-by-month digest work. The draft `changelog-generate` skill's coverage check found the 2026-07-11→07-23 range 100% v3-tagged (a first — the seed dry run was 1/17), so the render proceeded without inferring any facing tags, unlike the prior partial-coverage section already in the file.
Outcome [user-facing]: New `## [Unreleased] — 2026-07-11 to 2026-07-23` section prepended to CHANGELOG.md (digest v2→v3 evolution, `--split-by-month`, backup/export selectors, keepalive.sh fix), each section now carrying its own inline `_Coverage: ..._` line instead of one file-wide caveat.
Outcome [internal]: Logged the run to `~/.claude/skills/changelog-generate/feedback-log.md` per the skill's draft-usage protocol (signal: works-as-designed, provisional pending user reaction).

### Objective 2: Generate the f3pugetsound monthly digest  [accreted]
Transition: Immediate follow-on request once the split-by-month feature and changelog were done — verify the feature against the real archive.
Rationale: Prove `export digest --split-by-month` end-to-end against the actual `jobs/f3-pugetsound.json` job (updated earlier this session to `split_by_month: true`), not just the unit-test fixtures.
Outcome [user-facing]: `./slackbackup export digest --archive-root ~/slack-backups --jobs 'jobs/f3-pugetsound.json'` produced 5 monthly digest files (2026-03 through 2026-07) plus the companion user-profiles file in `~/slack-exports/` — 0 missing archives across all 7 workspaces / 383 channels in every month.
## 2026-07-28 10:35:00
_session 5547f9d2 · v3 · 07-28_

### Objective 1: Diagnose and fix the nightly backup failure
Rationale: User reported nightly backups weren't happening and pointed at `~/slack-backup/nightly.log` (a typo for the real path). `~/slack-backups/nightly.log` showed three straight failed nights (07-26 through 07-28): both `backup run` and `export digest` crashed at import time with `ModuleNotFoundError: No module named 'pypdf'`. Root cause was two-layered: `pypdf` had been added as an `import` in `export_logic.py` (uncommitted, part of the file-content-extraction work — see Objective 2) without ever being installed anywhere the nightly Scheduled Task could reach, and the `./slackbackup` entry point's shebang ran under "whatever `python3` is first on PATH" rather than this project's own venv. Developer pushed back on my first fix (prefixing the nightly script's calls with `uv run --project`) — "shouldn't slackbackup be running from the correct virtual environment?" — which pointed at the right layer: fix the entry point itself, not every caller of it.
Rejected: wrapping only `scripts/nightly-backup-digest.sh`'s two `./slackbackup` invocations with `uv run --project`. Works for that one script but leaves the same trap for any other invocation (manual runs, other tooling).
Outcome [developer-facing]: `./slackbackup`'s shebang is now `#!/usr/bin/env -S uv run --project /home/stuar/proj/SlackArchiver python3`, so it always resolves this project's own venv (and its dependencies) regardless of caller PATH. Verified against a stripped-down PATH matching the Scheduled Task's environment. Nightly script's PATH also gained `~/.local/bin` so the shebang's own `uv` can be found. Full suite (347 tests) green.
Outcome [internal]: Committed as 4bea0a4 and pushed to origin/main.

### Objective 2: Backfill work-log/CHANGELOG for accumulated uncommitted feature work  [accreted]
Transition: developer asked to "look at the other changes and update the work log and changelog then commit" — a large amount of prior work (multiple untracked sessions) had accumulated in the working tree with no log entries and was never committed.
Rationale: `git diff` on the remaining tracked files showed real completed feature work with tests already passing, not work-in-progress scaffolding: attached-file content extraction (PDF via `pypdf`, docx/pptx/xlsx via stdlib `zipfile` + regex over OOXML text runs) so an LLM digest reader gets a document's substance, not just its filename/link; images are now included in a channel's `files[]` (metadata + `local_path` only, no extraction) instead of being filtered out entirely; and `export monthly`/`export digest`/`export users` all gained a `~/slack-backups` default for `--archive-root` (and `--out` defaults accordingly) so the common case no longer needs the flag spelled out every time. A companion doc, `docs/slt-report.md`, was added as a new LLM prompt template (Senior Leadership Team report) alongside the existing newsletter/FNG/culture prompt docs, and `docs/slack-ingestion.md` gained a "Slack Message Formatting" section (no Markdown tables, prefer short bulleted lists) for content meant to be pasted back into Slack.
Outcome [user-facing]: `export monthly --archive-root`/`export digest --archive-root`/`export users --archive-root` are now optional (default `~/slack-backups`); a channel's Canvas/file listing includes images (with `local_path` when the blob was downloaded) alongside PDFs/Office docs/plain text, and PDF/docx/pptx/xlsx attachments now carry extracted `content` text in the digest. New `docs/slt-report.md` prompt template for SLT reports; `docs/slack-ingestion.md` documents Slack-safe formatting conventions.
Outcome [developer-facing]: `export_logic.py` gained `_extract_pdf_text`/`_extract_zip_xml_text`/`_extract_file_content` dispatch and `_resolve_local_path`; `_load_channel_files` no longer filters out `image/*`. 19 new tests across content extraction, local_path resolution, and the existing monthly-split assembly path. `pypdf` is now a declared `pyproject.toml`/`uv.lock` dependency (the gap that caused Objective 1's failure).
Outcome [internal]: A live-archive survey (2026-07-24, 483 channel databases) informed scoping extraction to PDF/docx/pptx/xlsx (46 files, ~31 MB) rather than images/video (5,539 images/12.3 GB, 243 videos/6.8 GB, would need a vision/audio model, out of scope) — noted in `docs/DESIGN-export.md` but not previously captured in this log since the originating session(s) predate this entry and were never logged.
Open: rationale for this objective is reconstructed from the code diff and docs, not from the original developer's own words — no prior work-log entry or session transcript exists for this work to quote from.

### Key Learnings:
`env -S uv run --project <path> python3` in a shebang line resolves a project's own venv (installing/syncing it on demand if needed) even when the invoking shell's PATH has no reference to that project at all — a more robust fix than requiring every caller to remember `uv run --project`.
## 2026-08-06 15:55:00
_session f28e2c4f · v3 · 08-06_

### Objective 1: sat-811 — digest v4 files_out sidecar (OOM fix), ship and verify
Rationale: A real f3-pugetsound digest run (383 channels) OOM-killed; measurement showed extracted file/Canvas text was ~55% of digest bytes and duplicated verbatim into every monthly file. Moving that content into a separate cumulative `files_out` sidecar (schema v4) removes the dominant memory/duplication term without a pipeline rewrite. Shipping this required pushing the branch, opening PR #6, running a full merge-gate review, fixing what it found, then proving the fix against the actual channel that OOM'd, and finally bringing the LLM-ingestion instructions up to date with the new schema so the sidecar is actually usable downstream.
Rejected: keeping two ingestion docs (the incrementally-patched v3→v4 `slack-ingestion.md` and a separately-drafted `slack-ingestion-v4.md` rewrite) — the draft was better organized but had two factual errors against the real schema (`archive_status` values, an unneeded `message_ts` normalization step) and had dropped the original's canvas-currency asymmetry warning; merged into one corrected canonical doc instead of shipping either as-is.
Outcome [developer-facing]: PR #6 opened and pushed through 4 follow-up commits — 2 Copilot-flagged encoding/error-handling fixes, then a 3-reviewer merge-gate (Architect+Quality+Process Monitor composite, Code Reviewer, Security — all APPROVED WITH NOTES, 0 blocking) that surfaced `merge_files_out` silently dropping files no longer in a run's scan; fixed to be additive (a file that ages out via a narrower selector, 90-day Slack retention, or a transiently missing archive is carried forward, not lost) and covered with regression tests (370 passing).
Outcome [internal]: filed bd sat-pqf to track the Security reviewer's prompt-injection-via-extracted-content finding as a follow-up, not a blocker.
Outcome [user-facing]: verified the fix against production data — f3pugetsound (383 channels, the job that previously OOM-killed) and f3nation/dungeon-fh all regenerated cleanly with the v4 sidecar; also ran targeted re-backups for f3pugetsound `disc-it,all*` and f3nation `tech*` (0 failures) ahead of the regen.
Outcome [developer-facing]: rewrote `docs/slack-ingestion.md` onto the better-organized v4 draft's structure (schema enumeration, identity rules, source priority, activity-counting fields, ingestion-validation checklist), corrected its 2 factual gaps, and folded the original's canvas-currency ranking/asymmetry warning back in; `slack-ingestion-v4.md` scratch file removed.
Open: PR #6 merge still awaiting explicit user go-ahead — reviewed, hardened, and verified, but not yet merged.

## 2026-08-07 10:47:48
_session automated (bd-run-beads sat-ejk) · v3 · 08-07_

### Objective 1: Build and land the canonical LLM context pack, then retire the legacy documents it replaces
Rationale: Slack-derived LLM guidance (ingestion behavior, domain context, prompts, query policy) was scattered across seven standalone docs with no validation and no integration into the actual export pipeline; the pack consolidates these into docs/llm-context/ as the single canonical source, with the ingestion contract kept in sync with the digest/profile/sidecar schema per CLAUDE.md's cross-reference rule.
Outcome [developer-facing]: docs/llm-context/ created with ingestion-contract.md, f3-domain-context.md, query-policy.md, session-preamble.md, project-instructions.md, prompts/, augmentations/, and scripts/lookup_profile.py; DESIGN.md/DESIGN-export.md/DESIGN-files.md/OPERATIONS.md updated to reference it (commit 9f203b0).
Outcome [internal]: Validation run against fixtures matching the real digest-v4/files-v1/profiles-v1 schemas (no live matched digest/profile/sidecar or ChatGPT session was reachable headless) — 10/12 scenarios pass outright, 2 pass with a documented caveat; recorded in docs/llm-context/VALIDATION-RESULTS.md (commit 1d72f61).
Outcome [user-facing]: scripts/nightly-backup-digest.sh and README.md updated to point at the new pack; CLAUDE.md gained the doc-authority note for the ingestion contract (commit e898686).
Outcome [developer-facing]: Seven legacy files deleted outright (docs/slack-ingestion.md, docs/report-queries.md, docs/f3-culture.md, docs/newsletter-prompt.md, docs/fng-getting-started-prompt.md, and the 2026-06-30 f3-it-infrastructure augmentation .md/.json) — each had a complete canonical replacement in docs/llm-context/, so no archival copy was kept (commit 21187cc).
Provenance: sessions a72a42ac-58fc-4e68-9bd3-a9fef441e919, fa6175a5-0f5b-4810-94ee-a1fca993df54, 48b5cfa3-a84a-4c5b-8ac0-1c89e1f158ac, 9117fc1e-52dc-4159-be7d-ec4b14d44739 (beads sat-ejk.2–.5).

### Objective 2: Emit digest consistency metrics
Rationale: The export pipeline lacked a way to detect drift between a digest and its files/profile sidecars at generation time; consistency metrics make schema/content mismatches visible instead of silent.
Outcome [developer-facing]: src/slackbackup/export_logic.py extended (+109 lines) to compute and emit digest consistency metrics, with 149 lines of new coverage in tests/test_export_digest_logic.py; docs/DESIGN-export.md and docs/llm-context/ingestion-contract.md updated to document the metrics as part of the schema contract (commit 365b02c).
Provenance: session 46e5f565-0962-4cb4-aa82-bd313b596d93 (bead sat-ejk.6).

### Key Learnings:
Unattended bd-run-beads execution of a 5-bead chain (sat-ejk.2–.6) completed end-to-end for $7.94 total across ~24.5 minutes of session time, with no human intervention required between beads.

## 2026-08-07 09:35:00
_session fe2d1751 · v3 · 08-07_

### Objective 1: sat-svu — streaming digest architecture (sat-811 Phase 2), find and fix the real OOM cause
Rationale: sat-svu was scoped as conditional ("if the f3-pugetsound re-run still OOMs or comes close, implement...") on top of ADR-0004's Phase 1 fix, which the work-log had recorded as "regenerated cleanly" with no RSS number captured. Measured it live before committing to the rewrite: it still OOM-killed, at ~4.5 GB RSS - worse than the original 2.3 GB - confirming the gate condition and that Phase 1 alone hadn't fixed it.
Rejected: assuming the month-sharded spill alone (the design's originally-sketched fix) would resolve it. Implemented `gather_and_shard_digest_data`/`write_monthly_digests` (per-channel-month ndjson spill, streamed `files_out` entries, `--spill-dir`/`--resume`) and re-ran against the same job - it OOM-killed again, at the *same* channel (`f3cascades/ao-stray-balls`, position 50/383) as both prior runs. That determinism pointed away from cross-channel accumulation and toward a single-channel spike: `_extract_file_content`'s fallback branch called `path.read_text()` on every unsupported-mimetype file (images, video) before checking the mimetype, discarding the result anyway - that channel's archive holds a 503 MB `.MOV`. Fixed by checking mimetype before touching the file's bytes.
Outcome [developer-facing]: `export_logic.py` gains a streaming code path (`gather_and_shard_digest_data`, `write_monthly_digests`, `_load_month_messages`, spill-path helpers) used automatically by `export.py`'s `--split-by-month` jobs, plus `--spill-dir`/`--resume` CLI flags and matching job fields; the non-monthly `build_digest` path is unchanged. `_extract_file_content` reordered to classify mimetype before any read. 9 new tests (spill layout, per-channel flush-before-next-conversion proof via a spy `convert_fn`, streaming-vs-in-memory parity on a 3-channel x 3-month fixture, resume/skip semantics, files_out-from-spill, and a `Path.read_text`-must-not-be-called regression test for the mimetype fix) - 387 passing.
Outcome [user-facing]: `export digest --jobs jobs/f3-pugetsound.json` (the job that has OOM-killed on every prior architecture) verified end-to-end against real archived data: 383 channels, 4,726 files, all 6 monthly digests written, peak RSS 164 MB (was 2.3 GB / 4.5 GB / 2.9 GB across the three prior measurements), exit 0.
Outcome [internal]: ADR-0005 records both root causes and the measured before/after; `docs/DESIGN-export.md` gains a "Scalability - month-sharded spill" subsection. sat-svu closed with all 4 acceptance criteria met.

## 2026-08-07 09:50:00
_session fe2d1751 · v3 · 08-07_

### Objective 1: Fix a pre-existing test that pollutes the real ~/slack-exports directory
Transition: user flagged it directly - "there are two f3-digest files in the ~/slack-exports/ file either created by the nightly script or by your recent work. those have no meaningful data in them as they are too short. their presence indicates something is not right."
Rationale: `test_digest_split_by_month_default_out_includes_month_placeholder` exercises the `--out`-less direct digest path, which falls through to `export.DEFAULT_EXPORTS_DIR` (`~/slack-exports` on a real machine) since the test never monkeypatched that constant - a bug that predates this session, not introduced by the sat-svu work, but only surfaced now because that test ran repeatedly during sat-svu's verification passes.
Outcome [developer-facing]: Test now monkeypatches `export.DEFAULT_EXPORTS_DIR` to a tmp path and asserts the digest lands there (and explicitly that it does *not* land in the real `~/slack-exports`), instead of only asserting the fake's call count. Full suite re-run twice after the fix with no further pollution (387 passing both times).
Outcome [user-facing]: Deleted the two stray junk files it had already written (`f3-digest-2026-07-01-2026-{04,05}.json`, empty-stub content, not real digest data - confirmed before deleting).

## 2026-08-07 18:07:54
_session b849271c · v3 · 08-07_

### Objective 1: Establish a durable place and pattern for dated, non-Slack regional-F3 augmentation data, starting with the SOTN call transcript
Rationale: The LLM-context migration plan (sat-ejk) had flagged the untracked `docs/sotn-2026-07-30.md` transcript and left the augmentation refresh/growth question open. User: "as new sotn calls are held, we will add those to the augmentation data as additional information, all dated" and "we just need to have a place for and pattern for dealing with additional data that is relevant to inquiries about regional F3 information that may come from sources outside of slack" — the ask was the general pattern, not just this one file.
Rejected: Deleting `MIGRATION-PLAN.md`/`REVIEW-2026-08-06.md` outright once the migration looked "done" — checked cross-references first and found live docs (`CLAUDE.md`, `OPERATIONS.md`, `README.md`, `validation-set.md`, `VALIDATION-RESULTS.md`) still cite them by Phase/finding anchor, so they stay as frozen provenance records; only the still-open size-budget/cadence/owner decision and the (now-resolved) SOTN item were addressed. Proposed graduating the Markdown-first pack Decision into a proper ADR and filing a bd issue for the still-open budget question, but did not execute either — awaiting confirmation.
Outcome [developer-facing]: New cumulative augmentation `docs/llm-context/augmentations/sotn-transcripts.md` (append-a-dated-entry-per-call pattern, distinct from the existing single-snapshot roster files) plus `augmentations/sources/` for raw transcripts; `augmentations/README.md` now documents both augmentation shapes generally. `docs/llm-context/MIGRATION-PLAN.md` marks the SOTN open decision resolved (`sat-oxl`, closed) and reframes the still-open size-budget question against real ongoing augmentation growth rather than a one-time migration snapshot.
Outcome [developer-facing]: `scripts/nightly-backup-digest.sh`'s per-file `cp` allow-list replaced with an `rsync -a --delete --exclude ...` deny-list mirror of `docs/llm-context/`, so a new augmentation/prompt file is picked up automatically without a script edit; verified via `rsync -n` dry run.
Open: Whether to actually write the proposed ADR (Markdown-first context-pack decision) and file a bd issue for the size-budget/cadence/owner question — proposed, not yet executed.

### Objective 2: Slim the Slack file sidecar to stop accumulating routine unsupported-media records  [accreted]
Transition: Unrelated, explicitly scoped new request from the user mid-session ("Refactor the Slack file sidecar generation...").
Rationale: The v4 `files_out` sidecar's additive merge kept a permanent record for every JPG/PNG/MP4/etc with no extracted text, growing without bound; `has_content: false` in the digest also didn't explain itself without a sidecar join. Confirmed the exact keep/drop rule with the user via AskUserQuestion before coding (mimetype-class based: keep content_extracted/tombstone always, keep no_blob/unsupported_type only for non-ordinary-media files) rather than guessing.
Outcome [user-facing]: `export digest` output schema bumped to `slack-llm-digest-v5`/`slack-llm-files-v2` — digest file references now carry `archive_status` directly so `has_content: false` is self-explanatory; sidecar drops routine image/video/audio no_blob/unsupported_type records (and self-prunes them from a pre-v5 sidecar on merge) while keeping content_extracted/tombstone and exceptional non-media failures; `(workspace, channel_id, id)` join key and cumulative/additive merge semantics for kept records unchanged.
Outcome [developer-facing]: `_is_ordinary_unsupported_media`/`_sidecar_worth_keeping` added to `export_logic.py`; `_compute_consistency` gains `file_archive_status_counts`; 20 new/updated tests (red confirmed before implementing, 401/401 green after); `docs/DESIGN-export.md`, `docs/DESIGN.md`, `docs/llm-context/ingestion-contract.md`, `docs/llm-context/project-instructions.md` updated; new `docs/adr/0006-digest-v5-archive-status-slim-sidecar.md`. Tracked as `sat-4uf`, closed.
