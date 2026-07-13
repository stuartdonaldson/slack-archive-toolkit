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
