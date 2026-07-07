# Sourced helper: pure-logic pieces of preflight-auth.sh (bd SlackBackup-d70),
# split out for unit testing without needing a live slackdump session. Kept in
# sync with scripts/auth-refresh/auth_logic.mjs's classifySession so the bash
# and JS probes agree on what "stale" means.

# classify_session <exit_code> <stderr_text> -> echoes valid | stale | error.
#  - valid: exit 0.
#  - stale: a known expiry / auth-failure signature (re-login will fix it).
#  - error: failed for some other reason (network etc.) - do NOT prompt login.
# Pure function (no I/O beyond echo).
classify_session() {
    local exit_code="$1" stderr="${2:-}"
    if [[ "$exit_code" -eq 0 ]]; then
        echo "valid"
        return
    fi
    # Same signatures as auth_logic.mjs STALE_PATTERNS, case-insensitive.
    if grep -qiE 'authentication details expired|relogin is necessary|ez-login 3000|authentication error|invalid.*(auth|token|cookie)' <<< "$stderr"; then
        echo "stale"
        return
    fi
    echo "error"
}

# preflight_workspaces_from_channels <channels.json> -> distinct workspace
# names, one per line, sorted. Empty output if the file is missing or holds no
# workspace entries. Pure apart from reading the given file.
preflight_workspaces_from_channels() {
    local file="$1"
    [[ -f "$file" ]] || return 0
    jq -r '.[].workspace // empty' "$file" 2>/dev/null | sort -u
}
