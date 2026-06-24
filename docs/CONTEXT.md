# CONTEXT — Slack Backup

## Introduction & Goals

### Purpose

Automated backup of Slack channel history to a private Git repository using GitHub Actions and slackdump. Preserves irreplaceable conversation history against workspace deletion, plan downgrades, or account lockout without requiring Slack admin access or app installation.

### Quality Goals

| Priority | Quality Goal | Scenario |
|----------|-------------|----------|
| 1 | Reliability | Backup completes or fails with a clear log entry; no silent data loss |
| 2 | Operability | A developer forks, configures secrets, edits channels.json, and has a working backup in under 30 minutes |
| 3 | Portability | Any GitHub user can fork and operate the system with a different workspace and channel set |

### Stakeholders

| Stakeholder | Expectation |
|-------------|-------------|
| Developer / Operator | Fork, configure, and run without reading source code |
| Compliance user | Durable, timestamped, auditable export of channel history |
| Forker | Minimal required changes to adapt to a different workspace |

---

## Constraints

### Technical Constraints

- No Slack admin access; no Slack app installation
- Authentication via slackdump wiz cookie-based session file only
- GitHub Actions free tier (2,000 minutes/month for public repos)
- slackdump binary fetched at runtime; no pre-installed dependency assumed
- Output format is NDJSON (slackdump native); no format conversion

### Organizational Constraints

- Public repo holds no credentials and no backup data
- Private archive repo holds all backup output and state (last_ts.txt)
- Secrets stored exclusively as GitHub repository secrets

---

## Core Capabilities

- Incremental daily backup of configured Slack channels (new messages only)
- Manual full re-sync of complete channel history on demand
- Multi-channel backup from a single configuration file
- Credential isolation: public workflow repo contains no tokens or session data
- Read-only monthly JSON export: turn an archived channel into bounded, per-month `<workspace>-<channel>-yyyy-mm.json` files with thread replies nested under their parent, for downstream consumption (see docs/DESIGN-export.md)
- Channel catalog (fast member-only + explicit full-public tiers, with description and tracked-channel last-posted info) — see docs/DESIGN-files.md
- Canvas/non-image-file harvesting across all channels in a workspace, not just tracked ones, unified into one deduplicated index — see docs/DESIGN-files.md
- Cross-workspace message search: search every registered f3* workspace for a query and render results as one HTML report, most recent first, linking to each channel and message

---

## Use Cases

### UC-1: Daily Incremental Backup

Actor: Scheduler

Preconditions:
- SLACK_SESSION_FILE, PRIVATE_REPO_PAT, and ARCHIVE_REPO secrets are configured
- Private archive repo exists and is accessible via PAT
- channels.json lists at least one channel

Primary Flow:
1. Scheduler triggers workflow at 2AM UTC
2. Workflow reads last_ts.txt for each channel from private archive repo
3. Workflow fetches only messages newer than last recorded timestamp
4. Workflow writes backups/channel-YYYYMMDD.ndjson to private archive repo
5. Workflow updates last_ts.txt with new high-water mark
6. Workflow commits and pushes changes to private archive repo

Alternate Flows:
A1: No new messages since last_ts.txt → workflow exits without commit

Postconditions:
- New messages are archived in private repo
- last_ts.txt reflects the timestamp of the most recent fetched message

Acceptance Criteria:
- Only messages with timestamp > last_ts.txt value are fetched
- Output file is named `backups/<channel-slug>-YYYYMMDD.ndjson`
- last_ts.txt is updated after each successful channel backup
- No commit is made when no new messages exist for any channel

Constraints:
- last_ts.txt is the authoritative state marker; its absence triggers a full dump
- Session credentials are never written to the private archive repo

---

### UC-2: Manual Full Re-sync

Actor: Operator

Preconditions:
- Same secrets as UC-1
- Workflow supports workflow_dispatch trigger with `full_resync` boolean input

Primary Flow:
1. Operator triggers workflow_dispatch with full_resync=true
2. Workflow ignores last_ts.txt for all channels
3. Workflow dumps complete channel history via slackdump
4. Workflow writes full-backup-YYYYMMDD.ndjson per channel to private archive repo
5. Workflow commits and pushes to private archive repo

Postconditions:
- Complete channel history is archived
- last_ts.txt is not modified

Acceptance Criteria:
- last_ts.txt value is ignored when full_resync=true
- Output file is named `backups/<channel-slug>-full-YYYYMMDD.ndjson`
- last_ts.txt is not updated or overwritten

Constraints:
- Full re-sync does not alter incremental backup state

---

### UC-3: Multi-Channel Backup

Actor: Scheduler or Operator

Preconditions:
- channels.json lists two or more channels with id and name fields

Primary Flow:
1. Workflow reads channels.json
2. Workflow iterates over each channel entry
3. Workflow performs backup (incremental or full) for each channel independently
4. Workflow creates a separate ndjson file per channel
5. Workflow commits all new files to private archive repo in a single commit

Alternate Flows:
A1: One channel backup fails → remaining channels are still processed; failure is logged; exit code reflects partial failure

Postconditions:
- One ndjson file per channel is committed to private archive repo
- Channels that failed are identified in workflow log

Acceptance Criteria:
- One ndjson output file per channel, named with the channel slug from channels.json
- All channels in channels.json are attempted regardless of individual failures
- A single commit is made containing all successfully backed-up channels

Constraints:
- channels.json is the sole channel configuration source; no hardcoded channel IDs in workflow

---

## Non-Goals

- Real-time or near-real-time backup (minimum cadence is daily)
- Search, browse, or render interface for backup content
- Slack message deletion or modification
- Direct Message or group DM backup
- Slack app or bot installation

**Scope note:** Searching, browsing, and analyzing the archived data remain deliberate non-goals — those belong to a separate, later phase/project that consumes this archive as input. The read-only monthly JSON export (docs/DESIGN-export.md) is the first, bounded piece of that downstream phase delivered here: it is a structural transform of the archive (range-bound, month-bucketed, thread-nested), not a search or render interface, and it never modifies the archive.

---

## Glossary

| Term | Definition |
|------|------------|
| slackdump | Open-source CLI tool that exports Slack data using browser session cookies; no admin access required |
| NDJSON | Newline-delimited JSON; one JSON object per line; slackdump's native output format |
| last_ts.txt | State file in private archive repo storing the Unix timestamp of the most recently archived message per channel |
| session file | Output of `slackdump wiz`; contains browser cookie credentials; base64-encoded for GitHub secret storage |
| archive repo | Private GitHub repository holding all backup ndjson files and last_ts.txt state; never public |
| channel slug | Human-readable channel name (e.g. `team-chat`) from channels.json; used in output filenames |
