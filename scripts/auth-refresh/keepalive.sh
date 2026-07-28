#!/usr/bin/env bash
# Headless auth keep-alive wrapper (bd SlackBackup-5df).
#
# Runs `refresh-auth.mjs --keepalive` to re-capture the current Slack session from
# the persistent browser profile and re-register every workspace, keeping slackdump
# in sync with Slack's cookie rotation so sessions don't silently expire between
# nightly runs. Split out as a wrapper because the nightly job runs under Windows
# Task Scheduler with a minimal PATH where `node` (installed via nvm) isn't found.
#
# Non-fatal by contract: the caller (nightly-backup-digest.sh) treats a non-zero
# exit as informational and continues. Interactive re-auth (`npm run refresh`) is
# still needed after a hard logout (password change / forced sign-out).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve a node binary: prefer one already on PATH, else the newest nvm install.
NODE_BIN="$(command -v node || true)"
if [[ -z "$NODE_BIN" ]]; then
    NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null | sort -V | tail -n1)"
fi
if [[ -z "$NODE_BIN" ]]; then
    echo "keepalive: node not found (checked PATH and ~/.nvm/versions/node/*/bin)" >&2
    exit 127
fi

exec "$NODE_BIN" "$SCRIPT_DIR/refresh-auth.mjs" --keepalive "$@"
