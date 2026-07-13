# Changelog

## ⚠ Draft-skill notice

This file was seeded by a **manual dry run** of the still-draft `changelog-generate` skill
(`~/.claude/skills/changelog-generate/SKILL.md`, status: draft/unverified), not by the finished
skill itself. Coverage was incomplete: only 1 of 17 work-log entries in the source range
(2026-06-10 → 2026-07-11) carried a facing tag; the rest were inferred by hand from free-text
`work-log.md` entries. **Verify against `work-log.md` / git history before relying on this for a
release or announcement.** See `~/.claude/skills/changelog-generate/feedback-log.md` for the
evaluation this run produced.

---

## [Unreleased] — 2026-06-10 to 2026-07-11

### Toward a workspace-agnostic engine

This period's largest architectural change: F3-specific leadership/role inference was extracted
out of the general export engine into a pluggable `handlers/` package (`handlers/f3.py`), selected
via `--leadership-handler` or a job's `leadership_handler` field. The engine itself
(backup/catalog/export/search/registration) has no F3-specific knowledge — a fork targeting a
different community adds a sibling handler module rather than forking the engine. See
`docs/CONTEXT.md` §Purpose "Vision: a workspace-agnostic engine, not an F3 tool" and
`docs/DESIGN-export.md` §Pluggable leadership handlers.

### Added

- `export monthly`, `export digest`, `export users` — bounded per-channel exports, a cross-workspace
  digest, and a full user-roster export, all workspace-agnostic at the engine level
- `search messages` now takes an explicit workspace name/glob argument instead of an implicit
  F3-only scan
- `channel-digest run` — on-demand digest/archive of channels matching a pattern (e.g. recovering
  orphaned content from shuttered channels), generalized (not F3-specific)
- Report jobs (`export digest --jobs 'jobs/*.json'`) — operator-owned, per-recipient digest
  definitions (workspaces, day window, output path, handler), each independently selecting its own
  leadership handler (or none)
- `catalog list` — human-readable channel listing (name, last-updated, message count)
- `handlers/` package and registry (`handlers.get`, `handlers.NAMES`) — the seam that makes the
  above workspace-agnostic; F3's leadership vocabulary is the first and currently only handler
- Tiered backup cadence — active channels backed up nightly, quieter channels on a longer cycle,
  cutting nightly workload

### Changed

- `export digest`/`export users`: `--workspace-glob` renamed to `--workspace`; no longer defaults
  to `f3*` — must be specified explicitly (or supplied per-job via `--jobs`)
- `channel register` now reports *why* a channel was skipped (archived/private/shuttered/already
  registered) instead of silently omitting it; `channel list` flags private channels
- Leadership inference (F3 handler) now also reads the Slack profile `title` field, distinguishing
  AO-scoped roles (Site Q, AOQ, OIC) from regional roles

### Fixed

- Channels that archived zero messages could get permanently stuck (unable to self-heal via
  `resume`); now automatically detected and re-archived from scratch
- Backup logs no longer appear to freeze mid-run (stdout buffering fix)
- Backup throughput improved ~44% by interleaving channels across workspaces instead of draining
  one workspace's rate-limit bucket at a time

### Documentation

- `keepalive.sh` (headless nightly session refresh) prerequisites documented directly in README,
  not just docs/OPERATIONS.md
- `docs/CONTEXT.md`/`docs/DESIGN.md` rewritten to match the actual shipped architecture (previously
  described an abandoned GitHub Actions design)
- Vision statement added making the workspace/community-agnostic engine goal explicit (previously
  implicit in the `handlers/` code, not stated as a goal anywhere)

---

_Developer-facing detail (module refactors, internal scheduling logic, PR/branch history) was
generated but held back from this file as noise for a release-notes audience — ask if you want the
developer-facing pass too._
