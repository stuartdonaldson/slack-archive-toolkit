#!/usr/bin/env bash
# Unit tests for scripts/lib/fetch_files_helpers.sh — pure logic only, no
# live slackdump/API calls. A separate manual/live smoke test is described
# at the bottom; it is NOT run by this script (mirrors test_multichannel.sh's
# pattern of requiring real arguments for live coverage).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/fetch_files_helpers.sh"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

FAILED=0

assert_eq() {
    local name="$1" expected="$2" actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        echo "PASS: $name"
    else
        echo "FAIL: $name" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        FAILED=1
    fi
}

# --- parse_term_file ---

cat > "$WORKDIR/terms.txt" <<'EOF'
# a leading comment
pax

  convergence
help
# trailing comment
ruck
EOF

assert_eq "parse_term_file skips comments/blanks and trims whitespace" \
    "$(printf 'pax\nconvergence\nhelp\nruck')" \
    "$(parse_term_file "$WORKDIR/terms.txt")"

# --- candidate_f3_workspaces ---

cat > "$WORKDIR/tokens.json" <<'EOF'
{
  "f3pugetsound": "xoxc-aaa",
  "f3kirkland": "xoxc-bbb",
  "f3seattle": "xoxc-ccc",
  "dungeons-of-finn-hill": "xoxc-ddd"
}
EOF

assert_eq "candidate_f3_workspaces returns only f3*-prefixed keys" \
    "$(printf 'f3kirkland\nf3pugetsound\nf3seattle')" \
    "$(candidate_f3_workspaces "$WORKDIR/tokens.json" | sort)"

assert_eq "candidate_f3_workspaces on a missing tokens file returns empty" \
    "" \
    "$(candidate_f3_workspaces "$WORKDIR/does-not-exist.json")"

# --- is_workspace_registered ---

REGISTERED_LIST="$(cat <<'EOF'
Workspaces in "/home/user/.cache/slackdump":

   dungeons-of-finn-hill (file: dungeons-of-finn-hill.bin, last modified: 2026-06-21 07:29:39)
   f3cascades (file: f3cascades.bin, last modified: 2026-06-21 07:45:26)
   f3kirkland (file: f3kirkland.bin, last modified: 2026-06-21 20:40:26)
=> f3pugetsound.slack.com (file: f3pugetsound.slack.com.bin, last modified: 2026-06-20 22:05:56)

Current workspace is marked with ' => '.
EOF
)"

if is_workspace_registered "f3cascades" "$REGISTERED_LIST"; then
    echo "PASS: is_workspace_registered true for a plain registered name"
else
    echo "FAIL: is_workspace_registered should be true for f3cascades" >&2
    FAILED=1
fi

if is_workspace_registered "f3pugetsound" "$REGISTERED_LIST"; then
    echo "PASS: is_workspace_registered true for the current (=>) workspace, suffix form"
else
    echo "FAIL: is_workspace_registered should be true for f3pugetsound (registered as f3pugetsound.slack.com)" >&2
    FAILED=1
fi

if is_workspace_registered "f3seattle" "$REGISTERED_LIST"; then
    echo "FAIL: is_workspace_registered should be false for f3seattle (not in list)" >&2
    FAILED=1
else
    echo "PASS: is_workspace_registered false for an unregistered workspace"
fi

exit "$FAILED"

# --- Manual/live smoke test (not run by this script) ---
# To verify against the real Slack API once:
#   scripts/fetch-files.sh /tmp/fetch-files-smoke
# should: skip any f3* workspace not yet registered (with a warning naming
# register-workspace.sh), and for each registered f3* workspace, write one
# slackdump.sqlite per configured search term under
# /tmp/fetch-files-smoke/<workspace>/<term>/. Re-running immediately after
# should report "skipped (exists)" for every term without making new API
# calls.
