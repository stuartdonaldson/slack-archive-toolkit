# Sourced helper: pure(ish) process-tree and lock-parsing logic for
# stop-nightly-backup.sh (bd sat-b9b), split out so it's unit-testable with
# real short-lived `sleep` processes standing in for the wrapper/children,
# without needing an actual slackbackup run.

# stop_pid_alive <pid> -> exit 0 if a process with that pid exists (liveness
# only, same os.kill(pid, 0) semantics as channel_lock.py's _is_alive - a
# pid we don't own but that still exists counts as alive). exit 1 for a
# dead, empty, or non-numeric pid.
stop_pid_alive() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null
}

# stop_descendant_pids <ppid> -> echoes every descendant of ppid (children,
# grandchildren, ...), one per line, depth-first. Empty output if ppid has
# no live children. Deliberately walks the process tree by parentage
# (pgrep -P) rather than matching process names/args - a name-based match
# (e.g. `pgrep -f slackdump`) risks catching an unrelated concurrent
# process; parentage cannot.
stop_descendant_pids() {
    local ppid="$1" child
    while IFS= read -r child; do
        [[ -n "$child" ]] || continue
        echo "$child"
        stop_descendant_pids "$child"
    done < <(pgrep -P "$ppid" 2>/dev/null)
}

# stop_process_tree <root_pid> -> echoes root_pid followed by all of its
# descendants (top-down order: parent before child). Must be called BEFORE
# any signal is sent to the tree - once the root dies, orphaned children are
# reparented (typically to init/PID 1) and are no longer discoverable via
# `pgrep -P <root_pid>`, so the tree has to be captured up front.
stop_process_tree() {
    local root_pid="$1"
    stop_pid_alive "$root_pid" || return 0
    echo "$root_pid"
    stop_descendant_pids "$root_pid"
}

# stop_wait_until_dead <timeout_seconds> <poll_interval_seconds> <pid...> ->
# polls the given pids (bounded, not a single blind sleep) until every one
# has exited or the timeout elapses, whichever comes first. Echoes whichever
# pids are STILL alive when it returns (one per line; nothing if all died).
# Always returns 0 - callers check the echoed list, not the exit code.
stop_wait_until_dead() {
    local timeout="$1" interval="$2"
    shift 2
    local pids=("$@")
    local waited=0 alive=() p
    while :; do
        alive=()
        for p in "${pids[@]}"; do
            stop_pid_alive "$p" && alive+=("$p")
        done
        if [[ "${#alive[@]}" -eq 0 || "$waited" -ge "$timeout" ]]; then
            break
        fi
        sleep "$interval"
        waited=$((waited + interval))
    done
    [[ "${#alive[@]}" -eq 0 ]] || printf '%s\n' "${alive[@]}"
}

# stop_find_wrapper_pid <script_path> -> echoes the pid of the single
# running nightly-backup-digest.sh wrapper that was actually invoked with
# the wrapper's *absolute* script path as one of its own argv entries, or
# nothing if it isn't running.
#
# Deliberately does NOT stop at a plain `pgrep -f <script_path>` substring
# match: that also matches any process whose command line merely *contains*
# the path as a fragment of some larger string - e.g. a wrapping shell
# invoked as `bash -c "... /path/to/nightly-backup-digest.sh ..."` (this is
# exactly what an interactive dev sandbox's own command wrapper looks like,
# and it is NOT the wrapper run - SIGTERM-ing it would kill the wrong
# thing). pgrep -f is used only as a cheap pre-filter; each candidate pid is
# then confirmed by reading its actual NUL-delimited argv from
# /proc/<pid>/cmdline and requiring script_path to appear there as a whole
# argument, not a substring - the same distinction as `bash <path>` (real
# invocation, argv has <path> as its own element) vs. `bash -c "... <path>
# ..."` (embedded, argv has one big string containing <path>).
#
# Explicitly excludes our OWN pids: stop-nightly-backup.sh is normally
# invoked with no arguments (script_path defaults to the sibling
# nightly-backup-digest.sh and never appears in our own argv), but when a
# caller passes --wrapper-script explicitly (as the test suite does), that
# exact path IS one of our own argv entries too - without this exclusion
# we'd always "find" ourselves. Excludes BOTH $$ and $BASHPID because this
# function always runs inside a `$(...)` command substitution (a real
# fork): $$ keeps reporting the *outer* script's pid (a bash quirk - it
# doesn't change inside a subshell) while $BASHPID reports the subshell
# fork's own actual pid: the outer script process and the transient
# subshell fork both share the same argv and both show up as separate
# pgrep matches, so both pids need excluding. Only the first remaining
# match is returned (there should be at most one legitimate instance).
stop_find_wrapper_pid() {
    local script_path="$1" pid arg
    for pid in $(pgrep -f -- "$script_path" 2>/dev/null); do
        [[ "$pid" == "$$" || "$pid" == "$BASHPID" ]] && continue
        [[ -r "/proc/$pid/cmdline" ]] || continue
        while IFS= read -r -d '' arg; do
            if [[ "$arg" == "$script_path" ]]; then
                echo "$pid"
                return 0
            fi
        done < "/proc/$pid/cmdline"
    done
}

# stop_parse_lock_file <lock_path> -> echoes "<pid>\t<since>" (since may be
# empty) for a readable, well-formed lock file (first line a bare integer
# pid - see channel_lock.py::_read_lock), or nothing at all for a missing,
# empty, or corrupt one - same "treat as absent" leniency _read_lock uses.
stop_parse_lock_file() {
    local lock_path="$1"
    [[ -f "$lock_path" ]] || return 0
    local text first_line rest
    text="$(cat "$lock_path" 2>/dev/null)"
    [[ -n "$text" ]] || return 0
    first_line="$(head -n1 <<< "$text")"
    [[ "$first_line" =~ ^[0-9]+$ ]] || return 0
    rest="$(tail -n +2 <<< "$text" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -v '^$' | head -n1)"
    printf '%s\t%s\n' "$first_line" "$rest"
}
