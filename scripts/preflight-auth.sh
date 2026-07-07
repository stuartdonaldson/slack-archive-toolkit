#!/usr/bin/env bash
# Pre-flight auth check (bd SlackBackup-d70): probe every workspace the backup
# will touch and report — up front — which ones have an expired session, so a
# nightly run's failures are announced at the top of the log instead of being
# discovered channel-by-channel mid-run (see nightly-backup-digest.sh's comment
# on why it deliberately does not `set -e`).
#
# Purely informational: always exits 0 so it can never abort the nightly run.
# Remediation for any stale workspace is `scripts/auth-refresh` (bd SlackBackup-fac).
#
# Usage: preflight-auth.sh [channels.json]   (default: ./channels.json)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/preflight_helpers.sh"

CHANNELS_FILE="${1:-channels.json}"
SLACKDUMP_BIN="${SLACKDUMP_BIN:-slackdump}"
TOKENS_FILE="${SLACKDUMP_TOKENS:-$HOME/.slackdump-tokens.json}"

echo "----- auth pre-flight $(date -u +%Y-%m-%dT%H:%M:%SZ) -----"

if ! command -v "$SLACKDUMP_BIN" >/dev/null 2>&1; then
    echo "pre-flight: '$SLACKDUMP_BIN' not on PATH — skipping auth check."
    exit 0
fi

# Workspaces the backup targets: prefer channels.json; fall back to the tokens
# file's keys if channels.json is absent/empty.
mapfile -t WORKSPACES < <(preflight_workspaces_from_channels "$CHANNELS_FILE")
if [[ "${#WORKSPACES[@]}" -eq 0 && -f "$TOKENS_FILE" ]]; then
    mapfile -t WORKSPACES < <(jq -r 'keys[]' "$TOKENS_FILE" 2>/dev/null | sort -u)
fi

if [[ "${#WORKSPACES[@]}" -eq 0 ]]; then
    echo "pre-flight: no workspaces found (checked $CHANNELS_FILE and $TOKENS_FILE)."
    exit 0
fi

stale=()
errored=()
for ws in "${WORKSPACES[@]}"; do
    err="$(timeout 90 "$SLACKDUMP_BIN" list channels -member-only -workspace "$ws" 2>&1 >/dev/null)"
    state="$(classify_session "$?" "$err")"
    case "$state" in
        stale)   stale+=("$ws") ;;
        error)   errored+=("$ws") ;;
    esac
done

if [[ "${#stale[@]}" -eq 0 && "${#errored[@]}" -eq 0 ]]; then
    echo "pre-flight: all ${#WORKSPACES[@]} workspace session(s) valid."
    exit 0
fi

if [[ "${#stale[@]}" -gt 0 ]]; then
    echo "pre-flight: ${#stale[@]} workspace(s) need re-auth (session expired):"
    for ws in "${stale[@]}"; do echo "    - $ws"; done
    echo "  Fix: cd $SCRIPT_DIR/auth-refresh && npm run refresh"
fi
if [[ "${#errored[@]}" -gt 0 ]]; then
    echo "pre-flight: ${#errored[@]} workspace(s) failed the probe for other reasons (check network/slackdump):"
    for ws in "${errored[@]}"; do echo "    - $ws"; done
fi

exit 0
