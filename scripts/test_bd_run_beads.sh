#!/usr/bin/env bash
# Tests for scripts/bd-run-beads.py (bd SlackBackup-j7b).
# Fixture-driven: no live bd database, no real claude sessions. A fake `bd`
# serves issue JSON from per-test fixture dirs; a fake `claude` logs its
# invocations and flips the bead's status file to closed (or doesn't, for
# the gate-failure case). Bead ids use a tb- prefix so prompt parsing in
# the fake is unambiguous.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/bd-run-beads.py"

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

assert_contains() {
    local name="$1" needle="$2" haystack="$3"
    if grep -qF -- "$needle" <<<"$haystack"; then
        echo "PASS: $name"
    else
        echo "FAIL: $name" >&2
        echo "  expected to contain: $needle" >&2
        echo "  actual: $haystack" >&2
        FAILED=1
    fi
}

# --- fakes ------------------------------------------------------------------

FAKEBIN="$WORKDIR/fakebin"
mkdir -p "$FAKEBIN"

cat > "$FAKEBIN/bd" <<'FAKE'
#!/usr/bin/env bash
# fake bd: only `bd show <id> --json`, served from $FIXDIR/<id>.{title,status,labels,deps}
set -euo pipefail
[[ "$1" == "show" ]] || { echo "fake bd: unsupported: $*" >&2; exit 1; }
python3 - "$2" <<'PY'
import json, os, sys
fix = os.environ["FIXDIR"]
iid = sys.argv[1]
def read(name, default=""):
    p = f"{fix}/{iid}.{name}"
    return open(p).read().strip() if os.path.exists(p) else default
deps = []
for dep in read("deps").split():
    deps.append({
        "id": dep,
        "status": open(f"{fix}/{dep}.status").read().strip(),
        "dependency_type": "blocks",
        "title": "",
    })
print(json.dumps([{
    "id": iid,
    "title": read("title", iid),
    "status": read("status", "open"),
    "labels": [l for l in read("labels").split(",") if l],
    "dependencies": deps,
}]))
PY
FAKE
chmod +x "$FAKEBIN/bd"

cat > "$FAKEBIN/claude" <<'FAKE'
#!/usr/bin/env bash
# fake claude: prompt arrives on STDIN (the runner must never pass it as a
# positional arg — variadic --allowedTools would eat it). Logs
# "RUN <bead-id> <model>", emits one stream-json result line, then closes
# the bead unless NO_CLOSE.
set -euo pipefail
model=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) model="$2"; shift 2 ;;
        --permission-mode|--allowedTools|--output-format) shift 2 ;;
        *) shift ;;
    esac
done
prompt="$(cat)"
[[ -n "${PROMPT_DUMP:-}" ]] && printf '%s' "$prompt" > "$PROMPT_DUMP"
id="$(grep -oE 'tb-[a-z0-9]+' <<<"$prompt" | head -1)"
[[ -n "$id" ]] || { echo "fake claude: no bead id on stdin" >&2; exit 1; }
echo "RUN $id $model" >> "$CLAUDE_LOG"
echo '{"type":"result","subtype":"success","num_turns":1}'
if [[ -z "${NO_CLOSE:-}" ]]; then
    echo closed > "$FIXDIR/$id.status"
fi
FAKE
chmod +x "$FAKEBIN/claude"

export BD_BIN="$FAKEBIN/bd"
export CLAUDE_BIN="$FAKEBIN/claude"

# fixture helper: mk_bead <fixdir> <id> <title> <status> <labels> <deps...>
mk_bead() {
    local dir="$1" id="$2" title="$3" status="$4" labels="$5"; shift 5
    echo "$title"  > "$dir/$id.title"
    echo "$status" > "$dir/$id.status"
    echo "$labels" > "$dir/$id.labels"
    echo "$*"      > "$dir/$id.deps"
}

line_no() { grep -n -- "$1" <<<"$2" | head -1 | cut -d: -f1; }

# --- case 1+2: diamond topo order, dedupe, model cues (dry-run) --------------
# tb-t depends on tb-a and tb-b; both depend on tb-r.
# tb-a: title cue [haiku-ok]; tb-b: label model:opus AND title cue [haiku]
# (label must win); tb-r, tb-t: default model.

FIX1="$WORKDIR/fix1"; mkdir -p "$FIX1"
mk_bead "$FIX1" tb-r "root fix"                  open ""           ""
mk_bead "$FIX1" tb-a "[haiku-ok] mechanical bit" open ""           "tb-r"
mk_bead "$FIX1" tb-b "[haiku] labelled bit"      open "model:opus" "tb-r"
mk_bead "$FIX1" tb-t "docs at the end"           open ""           "tb-a tb-b"

OUT="$(FIXDIR="$FIX1" "$RUNNER" --dry-run tb-t)"

pr="$(line_no tb-r "$OUT")"; pa="$(line_no tb-a "$OUT")"
pb="$(line_no tb-b "$OUT")"; pt="$(line_no tb-t "$OUT")"
assert_eq "topo: root before both mid beads"   "yes" "$( (( pr < pa && pr < pb )) && echo yes || echo no )"
assert_eq "topo: both mid beads before target" "yes" "$( (( pa < pt && pb < pt )) && echo yes || echo no )"
assert_eq "topo: shared dep appears once"      "1"   "$(grep -c -- tb-r <<<"$OUT")"
assert_contains "cue: title [haiku-ok] -> haiku" "tb-a haiku (title)" "$(awk '/tb-a/{print $2, $3, $4}' <<<"$OUT")"
assert_contains "cue: label beats title cue"     "tb-b opus (label)"  "$(awk '/tb-b/{print $2, $3, $4}' <<<"$OUT")"
assert_contains "cue: default model"             "tb-t sonnet (default)" "$(awk '/tb-t/{print $2, $3, $4}' <<<"$OUT")"

# --- case 3: closed dependency is skipped, not executed ----------------------

FIX2="$WORKDIR/fix2"; mkdir -p "$FIX2"
mk_bead "$FIX2" tb-r "root already done" closed "" ""
mk_bead "$FIX2" tb-a "the actual work"   open   "" "tb-r"

OUT="$(FIXDIR="$FIX2" "$RUNNER" --dry-run tb-a)"
assert_contains "closed dep marked skipped" "skipped (closed)" "$(grep -- tb-r <<<"$OUT")"
assert_contains "open bead still planned"   "tb-a"             "$(grep -v 'skipped' <<<"$OUT")"

# --- case 4: dependency cycle aborts ------------------------------------------

FIX3="$WORKDIR/fix3"; mkdir -p "$FIX3"
mk_bead "$FIX3" tb-x "one half"   open "" "tb-y"
mk_bead "$FIX3" tb-y "other half" open "" "tb-x"

set +e
OUT="$(FIXDIR="$FIX3" "$RUNNER" --dry-run tb-x 2>&1)"
rc=$?
set -e
assert_eq "cycle: non-zero exit" "yes" "$( (( rc != 0 )) && echo yes || echo no )"
assert_contains "cycle: message names the cycle" "cycle" "$OUT"

# --- case 5: execution order, models, and closing gate ------------------------

FIX4="$WORKDIR/fix4"; mkdir -p "$FIX4"
mk_bead "$FIX4" tb-r "root fix"                  open "" ""
mk_bead "$FIX4" tb-a "[haiku-ok] mechanical bit" open "" "tb-r"

export CLAUDE_LOG="$WORKDIR/claude.log"; : > "$CLAUDE_LOG"
FIXDIR="$FIX4" "$RUNNER" --test-cmd true --log-dir "$WORKDIR/logs5" --work-log off tb-a
assert_eq "exec: sessions run dependency-first with cue models" \
    "RUN tb-r sonnet
RUN tb-a haiku" "$(cat "$CLAUDE_LOG")"
assert_eq "exec: beads closed by session" "closed closed" \
    "$(cat "$FIX4/tb-r.status" "$FIX4/tb-a.status" | tr '\n' ' ' | sed 's/ $//')"

run_dirs=("$WORKDIR/logs5"/*)
assert_eq "logs: exactly one run dir" "1" "${#run_dirs[@]}"
assert_eq "logs: run.log written" "yes" \
    "$( [[ -s "${run_dirs[0]}/run.log" ]] && echo yes || echo no )"
assert_eq "logs: per-bead transcripts written" "yes" \
    "$( [[ -f "${run_dirs[0]}/tb-r.stream.jsonl" && -f "${run_dirs[0]}/tb-a.stream.jsonl" ]] && echo yes || echo no )"
assert_contains "logs: run.log records completion" "beads completed" \
    "$(cat "${run_dirs[0]}/run.log")"

# --- case 6: session that fails to close its bead stops the run ---------------

FIX5="$WORKDIR/fix5"; mkdir -p "$FIX5"
mk_bead "$FIX5" tb-r "root fix"        open "" ""
mk_bead "$FIX5" tb-a "never reached"   open "" "tb-r"

: > "$CLAUDE_LOG"
set +e
OUT="$(FIXDIR="$FIX5" NO_CLOSE=1 "$RUNNER" --test-cmd true --log-dir "$WORKDIR/logs6" tb-a 2>&1)"
rc=$?
set -e
assert_eq "gate: unclosed bead -> non-zero exit" "yes" "$( (( rc != 0 )) && echo yes || echo no )"
assert_contains "gate: names the offending bead" "tb-r" "$OUT"
assert_eq "gate: run stopped before second bead" "RUN tb-r sonnet" "$(cat "$CLAUDE_LOG")"

# --- case 7: failing test command stops the run -------------------------------

FIX6="$WORKDIR/fix6"; mkdir -p "$FIX6"
mk_bead "$FIX6" tb-r "root fix" open "" ""

: > "$CLAUDE_LOG"
set +e
OUT="$(FIXDIR="$FIX6" "$RUNNER" --test-cmd false --log-dir "$WORKDIR/logs7" tb-r 2>&1)"
rc=$?
set -e
assert_eq "gate: failing tests -> non-zero exit" "yes" "$( (( rc != 0 )) && echo yes || echo no )"
assert_contains "gate: reports test failure" "test" "$OUT"

# --- case 9/10: work-log step reuses the skill; on/off; warn-only gate --------
# With --work-log on, the session prompt gains an "invoke the work-log skill"
# step placed BEFORE the commit step (so the entry lands in the bead's own
# commit), and a session that doesn't grow work-log.md draws a run.log
# warning but never fails the run. With off, neither appears.

FIX8="$WORKDIR/fix8"; mkdir -p "$FIX8"
mk_bead "$FIX8" tb-r "root fix" open "" ""

: > "$CLAUDE_LOG"
OUT="$(cd "$WORKDIR" && FIXDIR="$FIX8" PROMPT_DUMP="$WORKDIR/prompt9.txt" \
    "$RUNNER" --test-cmd true --log-dir "$WORKDIR/logs9" --work-log on tb-r 2>&1)"
PROMPT="$(cat "$WORKDIR/prompt9.txt")"
assert_contains "work-log on: prompt invokes the skill" "work-log skill (/work-log)" "$PROMPT"
wl_line="$(line_no "work-log skill" "$PROMPT")"
commit_line="$(line_no "Commit the changes" "$PROMPT")"
assert_eq "work-log on: skill step precedes commit step" "yes" \
    "$( (( wl_line < commit_line )) && echo yes || echo no )"
run9=("$WORKDIR/logs9"/*)
assert_contains "work-log on: unchanged work-log.md draws warning" \
    "no work-log entry detected" "$(cat "${run9[0]}/run.log")"
assert_eq "work-log on: warning does not fail the run" "closed" "$(cat "$FIX8/tb-r.status")"

echo closed > "$FIX8/tb-r.status.reset" && echo open > "$FIX8/tb-r.status"
: > "$CLAUDE_LOG"
OUT="$(cd "$WORKDIR" && FIXDIR="$FIX8" PROMPT_DUMP="$WORKDIR/prompt10.txt" \
    "$RUNNER" --test-cmd true --log-dir "$WORKDIR/logs10" --work-log off tb-r 2>&1)"
assert_eq "work-log off: prompt has no skill step" "" \
    "$(grep -o 'work-log' "$WORKDIR/prompt10.txt" || true)"
run10=("$WORKDIR/logs10"/*)
assert_eq "work-log off: no warning logged" "" \
    "$(grep -o 'no work-log entry detected' "${run10[0]}/run.log" || true)"

# --- case 8: auto-detect must not pick a broken .venv pytest shim -------------
# Simulates a repo whose .venv predates a directory move: the shim exists and
# is executable, but its shebang interpreter is gone. Detection must probe and
# fall through to a working candidate (or disable) instead of trusting -x.

PROJ="$WORKDIR/proj"; mkdir -p "$PROJ/.venv/bin" "$PROJ/src"
printf '#!/nonexistent/python\n' > "$PROJ/.venv/bin/pytest"
chmod +x "$PROJ/.venv/bin/pytest"
touch "$PROJ/pyproject.toml"

FIX7="$WORKDIR/fix7"; mkdir -p "$FIX7"
mk_bead "$FIX7" tb-r "root fix" open "" ""

OUT="$(cd "$PROJ" && FIXDIR="$FIX7" "$RUNNER" --dry-run tb-r 2>&1)"
gate_line="$(grep 'test gate:' <<<"$OUT")"
assert_eq "detect: broken .venv shim rejected" "" "$(grep -o '.venv/bin/pytest' <<<"$gate_line" || true)"

# ------------------------------------------------------------------------------

if (( FAILED )); then
    echo "FAILURES" >&2
    exit 1
fi
echo "ALL PASS"
