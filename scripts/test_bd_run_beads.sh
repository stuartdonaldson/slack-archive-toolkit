#!/usr/bin/env bash
# Tests for scripts/bd-run-beads.py (bd SlackBackup-j7b, -daq).
# Fixture-driven: no live bd database, no real claude sessions. A fake `bd`
# serves issue JSON from per-test fixture dirs and records `close` calls; a
# fake `claude` logs its invocations and simulates work by dropping a marker
# file in cwd (unless NO_CHANGES=1). The runner itself now owns git
# commit/bd close, so execution cases run inside a real temp git repo.
# Bead ids use a tb- prefix so prompt parsing in the fake is unambiguous.
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
# fake bd: `show <id> --json` served from $FIXDIR/<id>.{title,status,labels,deps};
# `close <id>` writes closed to the status fixture; `update` is tolerated (no-op).
set -euo pipefail
case "$1" in
    show)
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
        ;;
    close)
        echo closed > "$FIXDIR/$2.status"
        ;;
    update)
        : # tolerated no-op (e.g. --claim)
        ;;
    *)
        echo "fake bd: unsupported: $*" >&2; exit 1 ;;
esac
FAKE
chmod +x "$FAKEBIN/bd"

cat > "$FAKEBIN/claude" <<'FAKE'
#!/usr/bin/env bash
# fake claude: prompt arrives on STDIN (the runner must never pass it as a
# positional arg — variadic --allowedTools would eat it). Logs
# "RUN <bead-id> <model>", emits one stream-json result line, then simulates
# work by dropping a marker file work-<id>.txt in cwd, unless NO_CHANGES=1.
# It never touches bd or git — the runner owns commit/close now.
set -euo pipefail
model=""
allowed_tools=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) model="$2"; shift 2 ;;
        --allowedTools) allowed_tools="$2"; shift 2 ;;
        --permission-mode|--output-format) shift 2 ;;
        *) shift ;;
    esac
done
[[ -n "${ARGS_DUMP:-}" ]] && printf '%s' "$allowed_tools" > "$ARGS_DUMP"
prompt="$(cat)"
[[ -n "${PROMPT_DUMP:-}" ]] && printf '%s' "$prompt" > "$PROMPT_DUMP"
id="$(grep -oE 'tb-[a-z0-9]+' <<<"$prompt" | head -1)"
[[ -n "$id" ]] || { echo "fake claude: no bead id on stdin" >&2; exit 1; }
echo "RUN $id $model" >> "$CLAUDE_LOG"
echo '{"type":"result","subtype":"success","num_turns":1}'
if [[ -z "${NO_CHANGES:-}" ]]; then
    : > "work-$id.txt"
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

# repo helper: mk_repo <dir> — a git repo with one commit, ready for the
# runner's dirty-tree guard and its own commits.
mk_repo() {
    local dir="$1"
    mkdir -p "$dir"
    git -C "$dir" init -q
    git -C "$dir" config user.email test@example.com
    git -C "$dir" config user.name "Test"
    echo "seed" > "$dir/README"
    git -C "$dir" add README
    git -C "$dir" commit -q -m "initial"
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

# --- case 5: execution order, models, and runner-side commit/close -----------

REPO5="$WORKDIR/repo5"; mk_repo "$REPO5"
FIX4="$WORKDIR/fix4"; mkdir -p "$FIX4"
mk_bead "$FIX4" tb-r "root fix"                  open "" ""
mk_bead "$FIX4" tb-a "[haiku-ok] mechanical bit" open "" "tb-r"

export CLAUDE_LOG="$WORKDIR/claude.log"; : > "$CLAUDE_LOG"
(cd "$REPO5" && FIXDIR="$FIX4" "$RUNNER" --test-cmd true --log-dir .bd-run-beads --work-log off tb-a)
assert_eq "exec: sessions run dependency-first with cue models" \
    "RUN tb-r sonnet
RUN tb-a haiku" "$(cat "$CLAUDE_LOG")"
assert_eq "exec: beads closed via runner-invoked bd close" "closed closed" \
    "$(cat "$FIX4/tb-r.status" "$FIX4/tb-a.status" | tr '\n' ' ' | sed 's/ $//')"
assert_eq "exec: a commit exists per bead, each naming the bead id" "2" \
    "$(git -C "$REPO5" log --oneline | grep -cE '\(tb-(r|a)\)')"
assert_eq "exec: working tree clean after run (log dir excluded)" "" \
    "$(git -C "$REPO5" status --porcelain -- . ':(exclude).bd-run-beads')"

run_dirs=("$REPO5/.bd-run-beads"/*)
assert_eq "logs: exactly one run dir" "1" "${#run_dirs[@]}"
assert_eq "logs: run.log written" "yes" \
    "$( [[ -s "${run_dirs[0]}/run.log" ]] && echo yes || echo no )"
assert_eq "logs: per-bead transcripts written" "yes" \
    "$( [[ -f "${run_dirs[0]}/tb-r.stream.jsonl" && -f "${run_dirs[0]}/tb-a.stream.jsonl" ]] && echo yes || echo no )"
assert_contains "logs: run.log records completion" "beads completed" \
    "$(cat "${run_dirs[0]}/run.log")"

# --- case 6: no-op guard — a session that changes nothing and doesn't close
# its bead fails the run, naming the bead; a dependent bead is never reached.

REPO6="$WORKDIR/repo6"; mk_repo "$REPO6"
FIX5="$WORKDIR/fix5"; mkdir -p "$FIX5"
mk_bead "$FIX5" tb-r "root fix"      open "" ""
mk_bead "$FIX5" tb-a "never reached" open "" "tb-r"

: > "$CLAUDE_LOG"
set +e
OUT="$(cd "$REPO6" && FIXDIR="$FIX5" NO_CHANGES=1 "$RUNNER" --test-cmd true --log-dir .bd-run-beads tb-a 2>&1)"
rc=$?
set -e
assert_eq "no-op guard: unchanged & unclosed bead -> non-zero exit" "yes" "$( (( rc != 0 )) && echo yes || echo no )"
assert_contains "no-op guard: names the offending bead" "tb-r" "$OUT"
assert_eq "no-op guard: run stopped before second bead" "RUN tb-r sonnet" "$(cat "$CLAUDE_LOG")"
assert_eq "no-op guard: no commit created" "1" "$(git -C "$REPO6" log --oneline | wc -l | tr -d ' ')"
assert_eq "no-op guard: bead left open" "open" "$(cat "$FIX5/tb-r.status")"

# --- case 7: failing test command stops the run -------------------------------

REPO7="$WORKDIR/repo7"; mk_repo "$REPO7"
FIX6="$WORKDIR/fix6"; mkdir -p "$FIX6"
mk_bead "$FIX6" tb-r "root fix" open "" ""

: > "$CLAUDE_LOG"
set +e
OUT="$(cd "$REPO7" && FIXDIR="$FIX6" "$RUNNER" --test-cmd false --log-dir .bd-run-beads tb-r 2>&1)"
rc=$?
set -e
assert_eq "gate: failing tests -> non-zero exit" "yes" "$( (( rc != 0 )) && echo yes || echo no )"
assert_contains "gate: reports test failure" "test" "$OUT"
assert_eq "gate: no commit created on test failure" "1" "$(git -C "$REPO7" log --oneline | wc -l | tr -d ' ')"

# --- case 8: dirty-tree guard --------------------------------------------------
# A pre-existing change outside --log-dir blocks the run unless --allow-dirty
# is passed; log-dir contents never count as dirty.

REPO8="$WORKDIR/repo8"; mk_repo "$REPO8"
echo "stray change" >> "$REPO8/README"
FIX9="$WORKDIR/fix9"; mkdir -p "$FIX9"
mk_bead "$FIX9" tb-r "root fix" open "" ""

: > "$CLAUDE_LOG"
set +e
OUT="$(cd "$REPO8" && FIXDIR="$FIX9" "$RUNNER" --test-cmd true --log-dir .bd-run-beads tb-r 2>&1)"
rc=$?
set -e
assert_eq "dirty guard: refuses to start" "yes" "$( (( rc != 0 )) && echo yes || echo no )"
assert_contains "dirty guard: mentions --allow-dirty" "--allow-dirty" "$OUT"
assert_eq "dirty guard: no session run" "" "$(cat "$CLAUDE_LOG")"

: > "$CLAUDE_LOG"
OUT="$(cd "$REPO8" && FIXDIR="$FIX9" "$RUNNER" --test-cmd true --log-dir .bd-run-beads --allow-dirty tb-r 2>&1)"
assert_contains "dirty guard: --allow-dirty proceeds" "RUN tb-r sonnet" "$(cat "$CLAUDE_LOG")"
assert_contains "dirty guard: warns pre-existing changes will be swept" "swept" "$OUT"
assert_contains "dirty guard: stray change swept into the bead's commit" "README" \
    "$(git -C "$REPO8" show --stat HEAD)"

REPO8B="$WORKDIR/repo8b"; mk_repo "$REPO8B"
mkdir -p "$REPO8B/.bd-run-beads/oldrun"
echo "stale log" > "$REPO8B/.bd-run-beads/oldrun/run.log"
FIX9B="$WORKDIR/fix9b"; mkdir -p "$FIX9B"
mk_bead "$FIX9B" tb-r "root fix" open "" ""

: > "$CLAUDE_LOG"
OUT="$(cd "$REPO8B" && FIXDIR="$FIX9B" "$RUNNER" --test-cmd true --log-dir .bd-run-beads tb-r 2>&1)"
assert_contains "dirty guard: pre-existing log-dir content is excluded" \
    "RUN tb-r sonnet" "$(cat "$CLAUDE_LOG")"

# --- case 9/10: work-log step reuses the skill; on/off; warn-only gate --------
# With --work-log on, the session prompt gains an "invoke the work-log skill"
# step placed BEFORE the "do not commit" instruction. The prompt never asks
# the session to commit, push, or close — that's the runner's job now. A
# session that doesn't grow work-log.md draws a run.log warning but never
# fails the run.

REPO9="$WORKDIR/repo9"; mk_repo "$REPO9"
FIX8="$WORKDIR/fix8"; mkdir -p "$FIX8"
mk_bead "$FIX8" tb-r "root fix" open "" ""

: > "$CLAUDE_LOG"
OUT="$(cd "$REPO9" && FIXDIR="$FIX8" PROMPT_DUMP="$WORKDIR/prompt9.txt" \
    "$RUNNER" --test-cmd true --log-dir .bd-run-beads --work-log on tb-r 2>&1)"
PROMPT="$(cat "$WORKDIR/prompt9.txt")"
assert_contains "prompt: states the session is unattended" "unattended" "$PROMPT"
assert_contains "prompt: forbids commit/push/close" "Do not commit" "$PROMPT"
assert_eq "prompt: no commit instruction remains" "" \
    "$(grep -o 'Commit the changes' "$WORKDIR/prompt9.txt" || true)"
assert_eq "prompt: no close instruction remains" "" \
    "$(grep -o 'Close it: bd close' "$WORKDIR/prompt9.txt" || true)"
assert_contains "work-log on: prompt invokes the skill" "work-log skill (/work-log)" "$PROMPT"
wl_line="$(line_no "work-log skill" "$PROMPT")"
forbid_line="$(line_no "Do not commit" "$PROMPT")"
assert_eq "work-log on: skill step precedes do-not-commit instruction" "yes" \
    "$( (( wl_line < forbid_line )) && echo yes || echo no )"
run9=("$REPO9/.bd-run-beads"/*)
assert_contains "work-log on: unchanged work-log.md draws warning" \
    "no work-log entry detected" "$(cat "${run9[0]}/run.log")"
assert_eq "work-log on: warning does not fail the run" "closed" "$(cat "$FIX8/tb-r.status")"

echo open > "$FIX8/tb-r.status"
REPO10="$WORKDIR/repo10"; mk_repo "$REPO10"
: > "$CLAUDE_LOG"
OUT="$(cd "$REPO10" && FIXDIR="$FIX8" PROMPT_DUMP="$WORKDIR/prompt10.txt" \
    "$RUNNER" --test-cmd true --log-dir .bd-run-beads --work-log off tb-r 2>&1)"
assert_eq "work-log off: prompt has no skill step" "" \
    "$(grep -o 'work-log' "$WORKDIR/prompt10.txt" || true)"
run10=("$REPO10/.bd-run-beads"/*)
assert_eq "work-log off: no warning logged" "" \
    "$(grep -o 'no work-log entry detected' "${run10[0]}/run.log" || true)"

# --- case 11: auto-detect must not pick a broken .venv pytest shim ------------
# Simulates a repo whose .venv predates a directory move: the shim exists and
# is executable, but its shebang interpreter is gone. Detection must probe and
# fall through to a working candidate (or disable) instead of trusting -x.
# --dry-run exits before any git interaction, so no repo is needed.

PROJ="$WORKDIR/proj"; mkdir -p "$PROJ/.venv/bin" "$PROJ/src"
printf '#!/nonexistent/python\n' > "$PROJ/.venv/bin/pytest"
chmod +x "$PROJ/.venv/bin/pytest"
touch "$PROJ/pyproject.toml"

FIX7="$WORKDIR/fix7"; mkdir -p "$FIX7"
mk_bead "$FIX7" tb-r "root fix" open "" ""

OUT="$(cd "$PROJ" && FIXDIR="$FIX7" "$RUNNER" --dry-run tb-r 2>&1)"
gate_line="$(grep 'test gate:' <<<"$OUT")"
assert_eq "detect: broken .venv shim rejected" "" "$(grep -o '.venv/bin/pytest' <<<"$gate_line" || true)"

# --- case 12: default --allowedTools covers the mandated commands -------------

REPO11="$WORKDIR/repo11"; mk_repo "$REPO11"
FIX10="$WORKDIR/fix10"; mkdir -p "$FIX10"
mk_bead "$FIX10" tb-r "root fix" open "" ""

: > "$CLAUDE_LOG"
OUT="$(cd "$REPO11" && FIXDIR="$FIX10" ARGS_DUMP="$WORKDIR/args12.txt" \
    "$RUNNER" --test-cmd true --log-dir .bd-run-beads --work-log off tb-r 2>&1)"
DUMP="$(cat "$WORKDIR/args12.txt")"
assert_contains "default allowlist: bd" "Bash(bd:*)" "$DUMP"
assert_contains "default allowlist: git add" "Bash(git add:*)" "$DUMP"
assert_contains "default allowlist: git status" "Bash(git status:*)" "$DUMP"
assert_contains "default allowlist: git diff" "Bash(git diff:*)" "$DUMP"
assert_contains "default allowlist: git log" "Bash(git log:*)" "$DUMP"
assert_contains "default allowlist: git rev-parse" "Bash(git rev-parse:*)" "$DUMP"
assert_contains "default allowlist: test-cmd entry" "Bash(true:*)" "$DUMP"

# --- case 13: explicit --allowed-tools is passed through verbatim -------------

REPO12="$WORKDIR/repo12"; mk_repo "$REPO12"
FIX11="$WORKDIR/fix11"; mkdir -p "$FIX11"
mk_bead "$FIX11" tb-r "root fix" open "" ""

: > "$CLAUDE_LOG"
OUT="$(cd "$REPO12" && FIXDIR="$FIX11" ARGS_DUMP="$WORKDIR/args13.txt" \
    "$RUNNER" --test-cmd true --log-dir .bd-run-beads --work-log off \
    --allowed-tools "Bash(echo:*)" tb-r 2>&1)"
assert_eq "explicit allowlist: passed through verbatim" "Bash(echo:*)" \
    "$(cat "$WORKDIR/args13.txt")"

# --- case 14: npm test auto-detected without executing it ---------------------

PROJ2="$WORKDIR/proj2"; mkdir -p "$PROJ2"
cat > "$PROJ2/package.json" <<'JSON'
{"scripts":{"test":"true"}}
JSON

FIX12="$WORKDIR/fix12"; mkdir -p "$FIX12"
mk_bead "$FIX12" tb-r "root fix" open "" ""

OUT="$(cd "$PROJ2" && FIXDIR="$FIX12" "$RUNNER" --dry-run tb-r 2>&1)"
assert_contains "npm detect: npm test picked as gate" "test gate: npm test" "$OUT"

# ------------------------------------------------------------------------------

if (( FAILED )); then
    echo "FAILURES" >&2
    exit 1
fi
echo "ALL PASS"
