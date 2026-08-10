#!/usr/bin/env bash
# stop-nightly-backup.sh (bd sat-b9b) - verified stop for an in-progress
# nightly-backup-digest.sh run.
#
# Stopping a run today means manually finding and killing three separate
# processes in sequence: the nightly-backup-digest.sh wrapper itself,
# whichever slackbackup stage is currently active (`backup run` or
# `export digest` - the wrapper runs them in sequence), and any orphaned
# slackdump child subprocess (archive/resume/dedupe/convert) that doesn't
# get SIGTERM propagated to it by the wrapper - each kill verified by hand
# via `ps aux | grep`. This script does that in one shot, verified.
#
# It does five things:
#   1. Finds the running wrapper (if any) by its exact script path - see
#      stop_find_wrapper_pid in lib/stop_nightly_helpers.sh for why a plain
#      name match isn't used.
#   2. Walks the FULL process tree under it (wrapper -> backup run/export
#      digest -> slackdump) by parentage (pgrep -P, recursively), captured
#      BEFORE any signal is sent - once a process dies its children are
#      reparented and no longer discoverable via their original parent.
#   3. SIGTERMs the wrapper first, then SIGTERMs anything in the tree still
#      alive after a bounded poll (not a blind `sleep N`).
#   4. SIGKILLs anything still alive after a further bounded grace period.
#   5. Verifies via `ps`/kill -0 that nothing in the tree remains, and scans
#      every `*/.*.lock` file under the archive root, reporting any lock
#      whose pid is still alive as a live holder needing manual attention
#      (should not happen right after this script's own kill pass) - a lock
#      with a dead pid is informational only and is NOT deleted; reclaim
#      happens automatically on next use (channel_lock.py::channel_lock).
#
# Usage:
#   stop-nightly-backup.sh [--wrapper-script <path>] [--archive-root <dir>]
#                           [--grace-seconds <n>] [--poll-interval <n>]
#   stop-nightly-backup.sh --help
#
# Exit codes:
#   0  nothing was running, or the run tree is confirmed fully stopped
#      (SIGTERM alone, or SIGTERM then SIGKILL - either way, verified) and
#      no live lock holder was found.
#   1  a lock file's pid is still alive after the kill pass - needs manual
#      attention (should not normally happen; see message for the pid).
#   2  a process in the tree survived even SIGKILL after the full grace
#      period - needs manual attention.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/stop_nightly_helpers.sh
source "$SCRIPT_DIR/lib/stop_nightly_helpers.sh"

print_help() {
    sed -n '2,/^set -uo pipefail/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

WRAPPER_SCRIPT="$SCRIPT_DIR/nightly-backup-digest.sh"
ARCHIVE_ROOT="$HOME/slack-backups"
GRACE_SECONDS=5
POLL_INTERVAL=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wrapper-script) WRAPPER_SCRIPT="${2:?--wrapper-script needs a value}"; shift 2 ;;
        --archive-root) ARCHIVE_ROOT="${2:?--archive-root needs a value}"; shift 2 ;;
        --grace-seconds) GRACE_SECONDS="${2:?--grace-seconds needs a value}"; shift 2 ;;
        --poll-interval) POLL_INTERVAL="${2:?--poll-interval needs a value}"; shift 2 ;;
        --help|-h) print_help; exit 0 ;;
        *) echo "stop-nightly-backup: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

FORCE_KILLED=0
SURVIVED_KILL=0

echo "----- stop-nightly-backup $(date -u +%Y-%m-%dT%H:%M:%SZ) -----"

WRAPPER_PID="$(stop_find_wrapper_pid "$WRAPPER_SCRIPT")"

if [[ -z "$WRAPPER_PID" ]]; then
    echo "stop-nightly-backup: no run in progress - '$WRAPPER_SCRIPT' is not running. Nothing to stop."
else
    mapfile -t TREE < <(stop_process_tree "$WRAPPER_PID")
    echo "stop-nightly-backup: found running wrapper pid $WRAPPER_PID with ${#TREE[@]} process(es) in its tree:"
    ps -o pid,ppid,stat,etime,cmd --forest -p "$(IFS=,; echo "${TREE[*]}")" 2>/dev/null \
        || printf '  pid %s\n' "${TREE[@]}"

    echo "stop-nightly-backup: sending SIGTERM to wrapper pid $WRAPPER_PID ..."
    kill -TERM "$WRAPPER_PID" 2>/dev/null || true
    stop_wait_until_dead "$GRACE_SECONDS" "$POLL_INTERVAL" "$WRAPPER_PID" >/dev/null

    mapfile -t STILL_ALIVE < <(stop_wait_until_dead 0 "$POLL_INTERVAL" "${TREE[@]}")
    if [[ "${#STILL_ALIVE[@]}" -gt 0 ]]; then
        echo "stop-nightly-backup: sending SIGTERM to ${#STILL_ALIVE[@]} remaining process(es): ${STILL_ALIVE[*]}"
        kill -TERM "${STILL_ALIVE[@]}" 2>/dev/null || true
        mapfile -t STILL_ALIVE < <(stop_wait_until_dead "$GRACE_SECONDS" "$POLL_INTERVAL" "${STILL_ALIVE[@]}")
    fi

    if [[ "${#STILL_ALIVE[@]}" -gt 0 ]]; then
        FORCE_KILLED=1
        echo "stop-nightly-backup: ${#STILL_ALIVE[@]} process(es) ignored SIGTERM - sending SIGKILL: ${STILL_ALIVE[*]}"
        kill -KILL "${STILL_ALIVE[@]}" 2>/dev/null || true
        mapfile -t STILL_ALIVE < <(stop_wait_until_dead "$GRACE_SECONDS" "$POLL_INTERVAL" "${STILL_ALIVE[@]}")
    fi

    if [[ "${#STILL_ALIVE[@]}" -gt 0 ]]; then
        SURVIVED_KILL=1
        echo "stop-nightly-backup: WARNING - still alive even after SIGKILL: ${STILL_ALIVE[*]} (needs manual attention)" >&2
    else
        echo "stop-nightly-backup: verified - no process in the wrapper's tree remains."
    fi
fi

# --- Lock scan: informational for dead pids, flagged for live ones. Every
# lock is a sibling of the channel dir it protects, named ".<channel>.lock"
# (channel_lock.py::lock_path_for) - one level below each workspace dir
# under the archive root, hence the `*/.*.lock` glob depth.
LIVE_LOCK_HOLDERS=()
DEAD_LOCK_COUNT=0

if [[ -d "$ARCHIVE_ROOT" ]]; then
    while IFS= read -r -d '' lock_file; do
        parsed="$(stop_parse_lock_file "$lock_file")"
        [[ -n "$parsed" ]] || continue
        pid="${parsed%%$'\t'*}"
        since="${parsed#*$'\t'}"
        if stop_pid_alive "$pid"; then
            LIVE_LOCK_HOLDERS+=("$lock_file (pid $pid, since ${since:-unknown})")
        else
            DEAD_LOCK_COUNT=$((DEAD_LOCK_COUNT + 1))
            echo "stop-nightly-backup: informational - $lock_file has dead pid $pid (since ${since:-unknown}); will be reclaimed automatically on next use, not deleted here."
        fi
    done < <(find "$ARCHIVE_ROOT" -mindepth 2 -maxdepth 2 -name '.*.lock' -print0 2>/dev/null)
    echo "stop-nightly-backup: lock scan complete under $ARCHIVE_ROOT - $DEAD_LOCK_COUNT dead lock(s), ${#LIVE_LOCK_HOLDERS[@]} live lock(s)."
else
    echo "stop-nightly-backup: archive root '$ARCHIVE_ROOT' does not exist - skipping lock scan."
fi

echo "----- stop-nightly-backup summary -----"
if [[ "${#LIVE_LOCK_HOLDERS[@]}" -gt 0 ]]; then
    echo "STATUS: live lock holder(s) found - needs manual attention:"
    printf '  - %s\n' "${LIVE_LOCK_HOLDERS[@]}"
    exit 1
fi
if [[ "$SURVIVED_KILL" -eq 1 ]]; then
    echo "STATUS: manual attention needed - a process survived SIGKILL, see warnings above."
    exit 2
fi
if [[ "$FORCE_KILLED" -eq 1 ]]; then
    echo "STATUS: force-killed - one or more processes ignored SIGTERM and required SIGKILL, but the run is now fully stopped and verified."
    exit 0
fi
echo "STATUS: stopped cleanly - nothing was running, or everything stopped via SIGTERM, verified, no live lock holders."
exit 0
