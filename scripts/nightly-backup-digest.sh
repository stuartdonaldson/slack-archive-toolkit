#!/usr/bin/env bash
# Nightly trigger: backup every tracked channel, then regenerate the f3*
# digest. Invoked by a Windows Scheduled Task running
# `wsl.exe -d Ubuntu -- /home/stuar/proj/SlackArchiver/scripts/nightly-backup-digest.sh`
# at 2am - see README.md "Getting Started" for the manual equivalent.
#
# Deliberately does not `set -e`: a partial backup failure (e.g. an
# expired workspace session, or a channel with an empty archive - see
# SlackBackup-8ew) must not prevent the digest step from running against
# whatever data IS available.
REPO_ROOT="/home/stuar/proj/SlackArchiver"
ARCHIVE_ROOT="$HOME/slack-backups"
LOG_FILE="$HOME/slack-backups/nightly.log"

# Task Scheduler -> wsl.exe runs this non-interactively, so ~/.bashrc/.profile
# are never sourced and PATH is minimal - slackdump (installed to ~/bin by
# scripts/install-slackdump.sh) wouldn't otherwise be found.
export PATH="$HOME/bin:$PATH"

# Defense-in-depth on top of backup_logic._log()'s explicit flush=True:
# Python fully block-buffers stdout once it's not a tty (i.e. redirected
# into this log file), so anything that prints without an explicit flush
# would otherwise sit invisible in the buffer for minutes during a long run.
export PYTHONUNBUFFERED=1

mkdir -p "$ARCHIVE_ROOT"
mkdir -p "$HOME/slack-exports"
{
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) nightly backup+digest starting ====="
    cd "$REPO_ROOT" || exit 1

    # Keep slackdump credentials in sync with Slack's cookie rotation before the
    # backup (bd SlackBackup-5df): headless re-capture from the persistent browser
    # profile so sessions don't silently expire between nightly runs. Non-fatal -
    # a hard logout still needs an interactive `npm run refresh`.
    "$REPO_ROOT/scripts/auth-refresh/keepalive.sh" || echo "----- keepalive exited $? (continuing) -----"

    # Announce any still-expired workspaces up front (bd SlackBackup-d70) rather
    # than discovering them channel-by-channel mid-run. Informational only -
    # always exits 0, so it never blocks the backup below.
    "$REPO_ROOT/scripts/preflight-auth.sh" channels.json

    ./slackbackup backup run channels.json "$ARCHIVE_ROOT"
    echo "----- backup run exited $? -----"

    ./slackbackup export digest --archive-root "$ARCHIVE_ROOT" --channels-file channels.json
    echo "----- digest exited $? -----"

    ./slackbackup export users --archive-root "$ARCHIVE_ROOT" --channels-file channels.json
    echo "----- users export exited $? -----"

    # Per-recipient report jobs (jobs/*.json, gitignored - see .gitignore's
    # comment on that pattern): each job file names its own workspace
    # subset, channels file, and output path. The glob is quoted so the
    # shell passes it through literally - --jobs does its own comma+glob
    # expansion (selector_logic.expand_path_selector), same paradigm as
    # --workspace-glob/--channel selectors elsewhere in this CLI.
    ./slackbackup export digest --archive-root "$ARCHIVE_ROOT" --jobs "$REPO_ROOT/jobs/*.json"
    echo "----- job digests exited $? -----"

    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) nightly backup+digest finished ====="
} >> "$LOG_FILE" 2>&1
