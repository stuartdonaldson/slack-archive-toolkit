#!/usr/bin/env bash
# fetch-files - best-effort harvesting of files/canvases across all f3*
# workspaces via `slackdump search files`, for channels NOT necessarily
# tracked in channels.json. Does NOT archive chat history for untracked
# channels - search files finds files without indexing a channel's message
# history at all.
#
# `slackdump tools merge` cannot combine these results into one
# per-workspace database (empirically verified - see
# docs/references/slackdump-cli-notes.md "## tools merge": search-result
# databases have an empty CHANNEL table, which merge requires). So each
# search term's result lands in its own directory; build-file-index.sh
# reads FILE rows across all of them directly.
#
# This makes real Slack API calls. Each search is cheap (sub-second per
# term in testing) but not free, so this is a deliberate, occasional/manual
# invocation - it is NOT wired into run-backups.sh's automatic cadence.
#
# Usage:
#   fetch-files.sh <out-archive-root> [--terms-file <path>]
#   fetch-files.sh --help
#
# Loops every f3*-prefixed workspace found in the slackdump tokens file
# (the same file register-workspace.sh reads, default
# ~/.slackdump-tokens.json). A workspace with a token on file but not yet
# registered with slackdump (no usable session) is skipped with a warning
# naming register-workspace.sh as the remedy - never scripted around, since
# registration needs a fresh session cookie pasted from the browser.
#
# Re-running is safe and cheap: a term already fetched for a workspace
# (its output directory already has a slackdump.sqlite) is skipped, not
# re-fetched. Delete the term's directory (or the whole output root) to
# force a refresh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/select_workspace.sh"
source "$SCRIPT_DIR/lib/fetch_files_helpers.sh"

TERMS_FILE_DEFAULT="$SCRIPT_DIR/config/file-search-terms.txt"

print_help() {
    sed -n '2,/^set -euo pipefail/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    print_help
    exit 0
fi

OUT_ROOT="${1:?usage: fetch-files.sh <out-archive-root> [--terms-file <path>] (--help for details)}"
shift

TERMS_FILE="$TERMS_FILE_DEFAULT"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --terms-file) TERMS_FILE="${2:?--terms-file needs a value}"; shift 2 ;;
        *) echo "fetch-files: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

if [[ ! -f "$TERMS_FILE" ]]; then
    echo "fetch-files: terms file not found: $TERMS_FILE" >&2
    exit 1
fi

TERMS="$(parse_term_file "$TERMS_FILE")"
if [[ -z "$TERMS" ]]; then
    echo "fetch-files: no search terms found in $TERMS_FILE" >&2
    exit 1
fi

WORKSPACES="$(candidate_f3_workspaces)"
if [[ -z "$WORKSPACES" ]]; then
    echo "fetch-files: no f3* workspaces found in token file" >&2
    exit 1
fi

REGISTERED="$(slackdump workspace list 2>/dev/null || true)"

while IFS= read -r ws; do
    [[ -z "$ws" ]] && continue
    if ! is_workspace_registered "$ws" "$REGISTERED"; then
        echo "fetch-files: skipping '$ws' — not registered yet (run: register-workspace.sh $ws <cookie>)" >&2
        continue
    fi

    select_workspace_or_die "$ws"

    while IFS= read -r term; do
        [[ -z "$term" ]] && continue
        TERM_DIR="$OUT_ROOT/$ws/$term"
        if [[ -f "$TERM_DIR/slackdump.sqlite" ]]; then
            echo "skipped (exists) $ws/$term"
            continue
        fi
        mkdir -p "$TERM_DIR"
        if slackdump search files -o "$TERM_DIR" "$term" >/dev/null 2>&1; then
            echo "wrote $ws/$term"
        else
            rmdir "$TERM_DIR" 2>/dev/null || true
            echo "empty (search failed) $ws/$term" >&2
        fi
    done <<< "$TERMS"
done <<< "$WORKSPACES"
