# Sourced helper: pure-logic pieces of fetch-files.sh, split out so they're
# unit-testable without a live slackdump/API call (mirrors how
# export_transform.sh is split from its caller for the same reason).

# parse_term_file <path> -> one search term per line, blank lines and
# '#'-comments skipped, surrounding whitespace trimmed.
parse_term_file() {
    local file="$1"
    grep -v '^[[:space:]]*#' "$file" | grep -v '^[[:space:]]*$' \
        | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

# candidate_f3_workspaces [tokens-file] -> f3*-prefixed keys from the
# slackdump tokens file (the same file register-workspace.sh reads) — the
# set of workspaces this project considers in scope for file harvesting,
# whether or not they're currently registered with slackdump.
candidate_f3_workspaces() {
    local tokens_file="${1:-${SLACKDUMP_TOKENS_FILE:-$HOME/.slackdump-tokens.json}}"
    [[ -f "$tokens_file" ]] || return 0
    jq -r 'keys[] | select(test("^f3"))' "$tokens_file"
}

# is_workspace_registered <workspace> <registered-list-text> -> exit 0/1
# <registered-list-text> is `slackdump workspace list` output (or a fixture
# of the same shape) — same matching pattern as register-workspace.sh's
# show_status(), tolerant of the "=> " current-workspace marker and the
# optional ".slack.com" suffix.
is_workspace_registered() {
    local ws="$1" registered_list="$2"
    grep -qi -E "^(=> )?[[:space:]]*${ws}(\.slack\.com)?[[:space:]]" <<< "$registered_list"
}
