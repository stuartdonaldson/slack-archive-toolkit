#!/usr/bin/env bash
# Nightly trigger: backup every tracked channel, then regenerate the f3*
# digest. Invoked by a Windows Scheduled Task running
# `wsl.exe -d Ubuntu -- /mnt/c/dev/SlackBackup/scripts/nightly-backup-digest.sh`
# at 2am - see README.md "Getting Started" for the manual equivalent.
#
# Deliberately does not `set -e`: a partial backup failure (e.g. an
# expired workspace session, or a channel with an empty archive - see
# SlackBackup-8ew) must not prevent the digest step from running against
# whatever data IS available.
REPO_ROOT="/mnt/c/dev/SlackBackup"
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

#    ./slackbackup backup run channels.json "$ARCHIVE_ROOT"
#    echo "----- backup run exited $? -----"

    ./slackbackup export digest --archive-root "$ARCHIVE_ROOT" --channels-file channels.json
    echo "----- digest exited $? -----"

    ./slackbackup export users --archive-root "$ARCHIVE_ROOT" --channels-file channels.json
    echo "----- users export exited $? -----"

    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) nightly backup+digest finished ====="
} >> "$LOG_FILE" 2>&1
