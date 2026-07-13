#!/usr/bin/env bash
# bd-run-beads.sh (bd SlackBackup-j7b) — run bd issues to completion via
# headless `claude -p` sessions, one session per bead, dependency-first.
#
# Given one or more target bead ids, resolves their transitive open
# `blocks` dependencies into execution order (deps before dependents,
# deduped, cycle-detected), picks a model per bead from cues, and runs a
# fresh claude session for each. Sequential on purpose: beads in one
# dependency tree usually touch the same files, so parallel sessions
# would conflict; and a fresh small-context session per bead is cheaper
# than one long session dragging every prior bead along.
#
# Model cue precedence (first match wins):
#   1. label  `model:<name>`         (bd label add <id> model:haiku)
#   2. title  `[<name>]`/`[<name>-ok]`  e.g. "[haiku-ok] trivial join fields"
#   3. --default-model (sonnet)
#
# After each session, two hard gates the model can't talk its way past:
# the test command must pass, and the bead must actually be closed.
# First failure stops the run; already-closed beads are skipped, so
# rerunning after a fix picks up where it left off.
#
# Usage:
#   bd-run-beads.sh [options] <bead-id> [<bead-id>...]
#     -n, --dry-run             print the plan (order, model, cue) and exit
#     -m, --default-model M     model when no cue matches (default: sonnet)
#     -t, --test-cmd CMD        post-session test gate; "" disables.
#                               Default: .venv/bin/pytest -q if present,
#                               else pytest -q if pyproject.toml, else none.
#         --permission-mode M   passed to claude (default: acceptEdits)
#         --allowed-tools LIST  passed to claude as --allowedTools
#
# Env: BD_BIN / CLAUDE_BIN override the binaries (used by the test suite);
# CLAUDE_EXTRA_ARGS is word-split into extra claude flags.
set -euo pipefail

BD="${BD_BIN:-bd}"
CLAUDE="${CLAUDE_BIN:-claude}"

DEFAULT_MODEL="sonnet"
DRY_RUN=0
TEST_CMD="__auto__"
PERMISSION_MODE="acceptEdits"
ALLOWED_TOOLS=""
TARGETS=()

die() { echo "bd-run-beads: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--dry-run) DRY_RUN=1; shift ;;
        -m|--default-model) DEFAULT_MODEL="$2"; shift 2 ;;
        -t|--test-cmd) TEST_CMD="$2"; shift 2 ;;
        --permission-mode) PERMISSION_MODE="$2"; shift 2 ;;
        --allowed-tools) ALLOWED_TOOLS="$2"; shift 2 ;;
        -h|--help) sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        --) shift; TARGETS+=("$@"); break ;;
        -*) die "unknown option: $1" ;;
        *) TARGETS+=("$1"); shift ;;
    esac
done
(( ${#TARGETS[@]} )) || die "no bead ids given (try --help)"

if [[ "$TEST_CMD" == "__auto__" ]]; then
    if [[ -x .venv/bin/pytest ]]; then TEST_CMD=".venv/bin/pytest -q"
    elif [[ -f pyproject.toml ]] && command -v pytest >/dev/null; then TEST_CMD="pytest -q"
    else TEST_CMD=""; echo "bd-run-beads: no test command detected; test gate disabled" >&2
    fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- issue access (cached per id; fetch_fresh busts the cache for gates) ----

fetch() {
    [[ -s "$TMP/$1.json" ]] || "$BD" show "$1" --json > "$TMP/$1.json" \
        || die "bd show $1 failed"
}

fetch_fresh() { rm -f "$TMP/$1.json"; fetch "$1"; }

# issue_field <id> <status|title|labels|deps>
issue_field() {
    fetch "$1"
    python3 - "$TMP/$1.json" "$2" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))[0]
field = sys.argv[2]
if field == "deps":
    for dep in doc.get("dependencies") or []:
        if dep.get("dependency_type", "blocks") == "blocks":
            print(dep["id"])
elif field == "labels":
    for label in doc.get("labels") or []:
        print(label)
else:
    print(doc.get(field) or "")
PY
}

# --- model cue ---------------------------------------------------------------

# model_for <id> -> "model cue-source"
model_for() {
    local label
    while read -r label; do
        if [[ "$label" == model:* ]]; then
            echo "${label#model:} label"
            return
        fi
    done < <(issue_field "$1" labels)

    local title
    title="$(issue_field "$1" title | tr '[:upper:]' '[:lower:]')"
    if [[ "$title" =~ \[(haiku|sonnet|opus|fable)(-ok)?\] ]]; then
        echo "${BASH_REMATCH[1]} title"
        return
    fi
    echo "$DEFAULT_MODEL default"
}

# --- dependency resolution (DFS post-order = deps first) ----------------------

declare -A SEEN=() ONPATH=()
ORDER=()
CLOSED_SKIPPED=()

visit() {
    local id="$1"
    [[ -n "${ONPATH[$id]:-}" ]] && die "dependency cycle detected at $id"
    [[ -n "${SEEN[$id]:-}" ]] && return 0
    SEEN[$id]=1
    if [[ "$(issue_field "$id" status)" == "closed" ]]; then
        CLOSED_SKIPPED+=("$id")
        return 0
    fi
    ONPATH[$id]=1
    local dep
    while read -r dep; do
        [[ -n "$dep" ]] && visit "$dep"
    done < <(issue_field "$id" deps)
    unset "ONPATH[$id]"
    ORDER+=("$id")
}

for target in "${TARGETS[@]}"; do
    visit "$target"
done

# --- plan ----------------------------------------------------------------------

echo "Execution plan (${#ORDER[@]} beads):"
declare -A PLAN_MODEL=()
step=0
for id in "${ORDER[@]}"; do
    step=$((step + 1))
    read -r model cue <<<"$(model_for "$id")"
    PLAN_MODEL[$id]="$model"
    printf '%2d  %s %s (%s)  %s\n' "$step" "$id" "$model" "$cue" "$(issue_field "$id" title)"
done
for id in "${CLOSED_SKIPPED[@]+"${CLOSED_SKIPPED[@]}"}"; do
    printf ' -  %s skipped (closed)\n' "$id"
done
(( ${#ORDER[@]} )) || { echo "nothing to do"; exit 0; }
(( DRY_RUN )) && exit 0

# --- execute --------------------------------------------------------------------

for id in "${ORDER[@]}"; do
    # a session may already have closed it (rerun, or manual work in between)
    fetch_fresh "$id"
    if [[ "$(issue_field "$id" status)" == "closed" ]]; then
        echo "== $id already closed, skipping"
        continue
    fi

    model="${PLAN_MODEL[$id]}"
    echo "== $id ($model) $(date -u +%H:%M:%SZ)"

    prompt="Work exactly one bd issue to completion: $id.
1. Run 'bd show $id' and follow its description and acceptance criteria literally.
2. Claim it: bd update $id --claim
3. Implement only this issue. Do not start, modify, or close any other bead."
    if [[ -n "$TEST_CMD" ]]; then
        prompt+="
4. Run the test suite until it passes: $TEST_CMD"
    fi
    prompt+="
5. Commit the changes with '$id' in the commit message. Do not push.
6. Close it: bd close $id"

    extra_args=()
    [[ -n "$ALLOWED_TOOLS" ]] && extra_args+=(--allowedTools "$ALLOWED_TOOLS")
    # shellcheck disable=SC2086  # CLAUDE_EXTRA_ARGS is word-split on purpose
    "$CLAUDE" -p --model "$model" --permission-mode "$PERMISSION_MODE" \
        "${extra_args[@]+"${extra_args[@]}"}" ${CLAUDE_EXTRA_ARGS:-} "$prompt" \
        || die "$id: claude session exited non-zero"

    # Hard gates: the session's own claims don't count.
    if [[ -n "$TEST_CMD" ]]; then
        bash -c "$TEST_CMD" || die "$id: test gate failed after session ($TEST_CMD)"
    fi
    fetch_fresh "$id"
    [[ "$(issue_field "$id" status)" == "closed" ]] \
        || die "$id: session ended without closing the bead"
    echo "== $id done"
done

echo "All ${#ORDER[@]} beads completed. Review the diff, then push."
