#!/usr/bin/env bash
# Tests for scripts/lib/stop_nightly_helpers.sh and scripts/stop-nightly-backup.sh
# (bd sat-b9b). Uses real short-lived `sleep` processes standing in for the
# wrapper/backup/slackdump tree so the kill-and-verify logic can be
# exercised without an actual slackbackup run.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/stop_nightly_helpers.sh
source "$SCRIPT_DIR/lib/stop_nightly_helpers.sh"

WORKDIR="$(mktemp -d)"
cleanup() {
    # Best-effort: nothing should still be running by the time we get here,
    # but don't leave stray sleeps behind if a test assertion fails early.
    jobs -p | xargs -r kill -9 2>/dev/null
    rm -rf "$WORKDIR"
}
trap cleanup EXIT

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

assert_true() {
    local name="$1"
    if "${@:2}"; then
        echo "PASS: $name"
    else
        echo "FAIL: $name" >&2
        FAILED=1
    fi
}

assert_false() {
    local name="$1"
    if ! "${@:2}"; then
        echo "PASS: $name"
    else
        echo "FAIL: $name" >&2
        FAILED=1
    fi
}

# --- stop_pid_alive ---

sleep 30 &
LIVE_PID=$!
assert_true "stop_pid_alive: running pid -> alive" stop_pid_alive "$LIVE_PID"
kill -9 "$LIVE_PID" 2>/dev/null
wait "$LIVE_PID" 2>/dev/null
assert_false "stop_pid_alive: reaped pid -> not alive" stop_pid_alive "$LIVE_PID"
assert_false "stop_pid_alive: empty pid -> not alive" stop_pid_alive ""
assert_false "stop_pid_alive: non-numeric pid -> not alive" stop_pid_alive "abc"

# --- stop_process_tree: parent -> child -> grandchild via real sleeps ---

bash -c 'sleep 30 & child=$!; wait "$child"' &
ROOT_PID=$!
# Give the subshell a moment to actually fork its child before we walk it.
for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -n "$(pgrep -P "$ROOT_PID" 2>/dev/null)" ]] && break
    sleep 0.2
done
mapfile -t TREE < <(stop_process_tree "$ROOT_PID")
assert_eq "stop_process_tree: root is first entry" "$ROOT_PID" "${TREE[0]:-}"
assert_eq "stop_process_tree: finds exactly root + 1 child" "2" "${#TREE[@]}"

kill -9 "${TREE[@]}" 2>/dev/null
wait "$ROOT_PID" 2>/dev/null

assert_eq "stop_process_tree: dead root -> empty tree" "" "$(stop_process_tree "$ROOT_PID")"

# --- stop_wait_until_dead: bounded polling, not a blind sleep ---

sleep 30 &
P1=$!
sleep 30 &
P2=$!
START="$(date +%s)"
STILL_ALIVE="$(stop_wait_until_dead 1 1 "$P1" "$P2")"
ELAPSED=$(( $(date +%s) - START ))
assert_eq "stop_wait_until_dead: both still alive when never signalled" \
    "$P1
$P2" "$STILL_ALIVE"
assert_true "stop_wait_until_dead: honours the timeout bound (<=3s for a 1s timeout)" \
    [ "$ELAPSED" -le 3 ]

kill -9 "$P1" "$P2" 2>/dev/null
wait "$P1" "$P2" 2>/dev/null
STILL_ALIVE2="$(stop_wait_until_dead 5 1 "$P1" "$P2")"
assert_eq "stop_wait_until_dead: returns empty once all pids are dead" "" "$STILL_ALIVE2"

# --- stop_find_wrapper_pid ---

FAKE_SCRIPT="$WORKDIR/fake-nightly-backup-digest.sh"
cat > "$FAKE_SCRIPT" <<'EOF'
#!/usr/bin/env bash
sleep 30
EOF
chmod +x "$FAKE_SCRIPT"

assert_eq "stop_find_wrapper_pid: nothing running -> empty" \
    "" "$(stop_find_wrapper_pid "$FAKE_SCRIPT")"

"$FAKE_SCRIPT" &
FAKE_PID=$!
sleep 0.3
assert_eq "stop_find_wrapper_pid: finds the running wrapper's pid" \
    "$FAKE_PID" "$(stop_find_wrapper_pid "$FAKE_SCRIPT")"
kill -9 "$FAKE_PID" 2>/dev/null
wait "$FAKE_PID" 2>/dev/null

# --- stop_parse_lock_file (mirrors channel_lock.py::_read_lock) ---

GOOD_LOCK="$WORKDIR/.good.lock"
printf '12345\n2026-08-09T02:00:00Z\n' > "$GOOD_LOCK"
assert_eq "stop_parse_lock_file: well-formed lock -> pid + since" \
    "$(printf '12345\t2026-08-09T02:00:00Z')" "$(stop_parse_lock_file "$GOOD_LOCK")"

EMPTY_LOCK="$WORKDIR/.empty.lock"
: > "$EMPTY_LOCK"
assert_eq "stop_parse_lock_file: empty file -> nothing" "" "$(stop_parse_lock_file "$EMPTY_LOCK")"

CORRUPT_LOCK="$WORKDIR/.corrupt.lock"
printf 'not-a-pid\n' > "$CORRUPT_LOCK"
assert_eq "stop_parse_lock_file: non-numeric first line -> nothing" "" "$(stop_parse_lock_file "$CORRUPT_LOCK")"

assert_eq "stop_parse_lock_file: missing file -> nothing" "" "$(stop_parse_lock_file "$WORKDIR/.nope.lock")"

# --- End-to-end: stop-nightly-backup.sh against a fake wrapper/child tree ---

STOP_SCRIPT="$SCRIPT_DIR/stop-nightly-backup.sh"

# (a) nothing running -> clean report, exit 0.
OUT_A="$("$STOP_SCRIPT" --wrapper-script "$WORKDIR/no-such-wrapper.sh" --archive-root "$WORKDIR/archive-a" 2>&1)"
RC_A=$?
assert_eq "e2e(a): not-running exits 0" "0" "$RC_A"
if grep -qi "not running\|nothing to stop\|no run in progress" <<< "$OUT_A"; then
    echo "PASS: e2e(a): reports nothing was running"
else
    echo "FAIL: e2e(a): expected a clear 'not running' message, got:" >&2
    echo "$OUT_A" >&2
    FAILED=1
fi

# (b) a running fake wrapper -> child tree gets fully killed and verified.
FAKE_WRAPPER="$WORKDIR/fake-wrapper.sh"
cat > "$FAKE_WRAPPER" <<EOF
#!/usr/bin/env bash
sleep 60 &
child=\$!
wait "\$child"
EOF
chmod +x "$FAKE_WRAPPER"

"$FAKE_WRAPPER" &
disown
for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -n "$(stop_find_wrapper_pid "$FAKE_WRAPPER")" ]] && break
    sleep 0.2
done
WRAPPER_PID="$(stop_find_wrapper_pid "$FAKE_WRAPPER")"
mapfile -t PRE_TREE < <(stop_process_tree "$WRAPPER_PID")

ARCHIVE_B="$WORKDIR/archive-b"
mkdir -p "$ARCHIVE_B"
OUT_B="$("$STOP_SCRIPT" --wrapper-script "$FAKE_WRAPPER" --archive-root "$ARCHIVE_B" --grace-seconds 3 2>&1)"
RC_B=$?
assert_eq "e2e(b): stop of a running fake tree exits 0" "0" "$RC_B"

ALL_DEAD=true
for pid in "${PRE_TREE[@]}"; do
    stop_pid_alive "$pid" && ALL_DEAD=false
done
assert_true "e2e(b): every pid in the pre-kill tree is confirmed dead afterwards" \
    [ "$ALL_DEAD" = true ]

if grep -qi "stopped cleanly\|force-killed\|stopped" <<< "$OUT_B"; then
    echo "PASS: e2e(b): prints an unambiguous final status"
else
    echo "FAIL: e2e(b): expected a final status line, got:" >&2
    echo "$OUT_B" >&2
    FAILED=1
fi

# (c) a lock file with a dead pid -> informational only, no live-holder flag.
ARCHIVE_C="$WORKDIR/archive-c/ws1"
mkdir -p "$ARCHIVE_C"
sleep 30 &
DEAD_CANDIDATE=$!
kill -9 "$DEAD_CANDIDATE"
wait "$DEAD_CANDIDATE" 2>/dev/null
printf '%s\n2026-08-01T00:00:00Z\n' "$DEAD_CANDIDATE" > "$ARCHIVE_C/.general.lock"

OUT_C="$("$STOP_SCRIPT" --wrapper-script "$WORKDIR/no-such-wrapper.sh" --archive-root "$WORKDIR/archive-c" 2>&1)"
RC_C=$?
assert_eq "e2e(c): dead-pid lock -> exits 0 (no manual attention needed)" "0" "$RC_C"
if grep -qi "dead\|reclaim\|informational" <<< "$OUT_C"; then
    echo "PASS: e2e(c): dead-pid lock reported informational"
else
    echo "FAIL: e2e(c): expected an informational dead-lock mention, got:" >&2
    echo "$OUT_C" >&2
    FAILED=1
fi
if [[ -f "$ARCHIVE_C/.general.lock" ]]; then
    echo "PASS: e2e(c): dead-pid lock file is left in place (not deleted)"
else
    echo "FAIL: e2e(c): dead-pid lock file was deleted - reclaim-by-liveness owns that, not this script" >&2
    FAILED=1
fi

# (d) a lock file with a still-alive (unrelated) pid -> flagged clearly.
ARCHIVE_D="$WORKDIR/archive-d/ws1"
mkdir -p "$ARCHIVE_D"
sleep 30 &
ALIVE_HOLDER=$!
printf '%s\n2026-08-09T01:00:00Z\n' "$ALIVE_HOLDER" > "$ARCHIVE_D/.general.lock"

OUT_D="$("$STOP_SCRIPT" --wrapper-script "$WORKDIR/no-such-wrapper.sh" --archive-root "$WORKDIR/archive-d" 2>&1)"
RC_D=$?
kill -9 "$ALIVE_HOLDER" 2>/dev/null
wait "$ALIVE_HOLDER" 2>/dev/null

assert_true "e2e(d): live lock holder -> non-zero exit (manual attention)" [ "$RC_D" -ne 0 ]
if grep -qi "live lock holder\|manual attention\|needs attention" <<< "$OUT_D"; then
    echo "PASS: e2e(d): live lock holder flagged clearly"
else
    echo "FAIL: e2e(d): expected a clear live-lock-holder flag, got:" >&2
    echo "$OUT_D" >&2
    FAILED=1
fi

if [[ "$FAILED" -eq 0 ]]; then
    echo "All stop-nightly-backup tests passed."
else
    echo "Some stop-nightly-backup tests FAILED." >&2
    exit 1
fi
