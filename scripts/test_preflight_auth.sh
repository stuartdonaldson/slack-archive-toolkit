#!/usr/bin/env bash
# Tests for scripts/lib/preflight_helpers.sh (bd SlackBackup-d70).
# Fixture-driven: no live slackdump / API calls. Mirrors the classification
# cases in scripts/auth-refresh/test/auth_logic.test.mjs so the bash and JS
# probes agree on what "stale" means.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/preflight_helpers.sh"

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

# --- classify_session: exit code + stderr -> valid | stale | error (AC1) ---

assert_eq "classify: exit 0 clean -> valid" \
    "valid" "$(classify_session 0 "")"
assert_eq "classify: expiry stderr -> stale" \
    "stale" "$(classify_session 1 "authentication details expired, relogin is necessary")"
assert_eq "classify: EZ-Login stderr -> stale" \
    "stale" "$(classify_session 1 "EZ-Login 3000 is not supported on this OS")"
assert_eq "classify: Authentication Error stderr -> stale" \
    "stale" "$(classify_session 1 "004 (Authentication Error): auth error")"
assert_eq "classify: unrelated non-zero -> error" \
    "error" "$(classify_session 2 "network unreachable")"

# --- preflight_workspaces_from_channels: distinct workspaces (AC2) ---

cat > "$WORKDIR/channels.json" <<'JSON'
[
  {"id": "C1", "name": "a", "workspace": "f3pugetsound"},
  {"id": "C2", "name": "b", "workspace": "f3pugetsound"},
  {"id": "C3", "name": "c", "workspace": "f3kirkland"},
  {"id": "C4", "name": "d", "workspace": "f3cascades"}
]
JSON

assert_eq "workspaces: distinct + sorted from channels.json" \
    "f3cascades f3kirkland f3pugetsound" \
    "$(preflight_workspaces_from_channels "$WORKDIR/channels.json" | tr '\n' ' ' | sed 's/ $//')"

assert_eq "workspaces: missing file -> empty" \
    "" \
    "$(preflight_workspaces_from_channels "$WORKDIR/nope.json")"

if [[ "$FAILED" -eq 0 ]]; then
    echo "All preflight_helpers tests passed."
else
    echo "Some preflight_helpers tests FAILED." >&2
    exit 1
fi
