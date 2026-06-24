#!/usr/bin/env bash
# search-messages - search for messages matching a query across every
# registered f3* workspace and render the results as one HTML page, most
# recent message first, each result linking to its channel and to the
# message itself in Slack.
#
# Usage:
#   search-messages.sh [--out <file.html>] <query terms...>
#   search-messages.sh --help
#
# Loops every f3*-prefixed workspace found in the slackdump tokens file
# (same source as fetch-files.sh / register-workspace.sh). A workspace with
# a token on file but not yet registered with slackdump is skipped with a
# warning naming register-workspace.sh as the remedy - never scripted
# around, since registration needs a fresh session cookie from the browser.
#
# This makes a live Slack API call per workspace every run (no caching -
# unlike fetch-files.sh, this is meant to answer "what's out there right
# now", not build a maintained archive). `slackdump search messages` treats
# multiple query words as an implicit AND (no OR operator) - see
# docs/references/slackdump-cli-notes.md.
#
# `SEARCH_MESSAGE` already carries CHANNEL_ID, CHANNEL_NAME, TS, and a ready
# permalink in its DATA blob - no channel-catalog lookup needed here (unlike
# build-file-index.sh's handling of `search files`' CHANNEL_ID placeholder).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/select_workspace.sh"
source "$SCRIPT_DIR/lib/fetch_files_helpers.sh"
source "$SCRIPT_DIR/lib/message_search_helpers.sh"

print_help() {
    sed -n '2,/^set -euo pipefail/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

OUT="./search-results.html"
QUERY_PARTS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h) print_help; exit 0 ;;
        --out) OUT="${2:?--out needs a value}"; shift 2 ;;
        *) QUERY_PARTS+=("$1"); shift ;;
    esac
done

if [[ "${#QUERY_PARTS[@]}" -eq 0 ]]; then
    echo "search-messages: no query given (--help for usage)" >&2
    exit 1
fi
QUERY_LABEL="${QUERY_PARTS[*]}"

WORKSPACES="$(candidate_f3_workspaces)"
if [[ -z "$WORKSPACES" ]]; then
    echo "search-messages: no f3* workspaces found in token file" >&2
    exit 1
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
RESULTS_JSONL="$WORKDIR/results.jsonl"
: > "$RESULTS_JSONL"

REGISTERED="$(slackdump workspace list 2>/dev/null || true)"

while IFS= read -r ws; do
    [[ -z "$ws" ]] && continue
    if ! is_workspace_registered "$ws" "$REGISTERED"; then
        echo "search-messages: skipping '$ws' — not registered yet (run: register-workspace.sh $ws <cookie>)" >&2
        continue
    fi

    select_workspace_or_die "$ws"
    echo "search-messages: searching '$ws' for: $QUERY_LABEL" >&2

    RESULT_DIR="$WORKDIR/$ws"
    if ! slackdump search messages -o "$RESULT_DIR" "${QUERY_PARTS[@]}" >/dev/null 2>&1; then
        echo "search-messages: search failed for '$ws'" >&2
        continue
    fi

    sqlite3 -json "$RESULT_DIR/slackdump.sqlite" "
        SELECT CHANNEL_ID AS channel_id, CHANNEL_NAME AS channel_name, TS AS ts,
               TXT AS txt, json_extract(DATA, '\$.permalink') AS permalink
        FROM SEARCH_MESSAGE
    " | jq -c --arg ws "$ws" '.[] | . + {workspace: $ws}' >> "$RESULTS_JSONL"
done <<< "$WORKSPACES"

RESULTS_JSON="$(jq -c -s '.' "$RESULTS_JSONL")"
render_messages_html "$RESULTS_JSON" "$QUERY_LABEL" > "$OUT"

echo "search-messages: wrote $(jq 'length' <<< "$RESULTS_JSON") result(s) to $OUT"
