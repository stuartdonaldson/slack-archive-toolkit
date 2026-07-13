#!/usr/bin/env python3
"""bd-run-beads.py (bd SlackBackup-j7b, -dbp) — run bd issues to completion
via headless `claude -p` sessions, one session per bead, dependency-first.

Given one or more target bead ids, resolves their transitive open `blocks`
dependencies into execution order (deps before dependents, deduped,
cycle-detected), picks a model per bead from cues, and runs a fresh claude
session for each. Sequential on purpose: beads in one dependency tree
usually touch the same files, so parallel sessions would conflict; and a
fresh small-context session per bead is cheaper than one long session
dragging every prior bead along.

Model cue precedence (first match wins):
  1. label  `model:<name>`             (bd label add <id> model:haiku)
  2. title  `[<name>]` / `[<name>-ok]` e.g. "[haiku-ok] trivial join fields"
  3. --default-model (sonnet)

After each session, two hard gates the model can't talk its way past: the
test command must pass, and the bead must actually be closed. First failure
stops the run; already-closed beads are skipped, so rerunning after a fix
picks up where it left off.

Logging: each executed run writes --log-dir/<UTC-stamp>/ containing run.log
(plan, per-bead timings, git HEAD before/after, gate results, fatal errors)
plus, per bead, the full claude stream-json transcript
(<bead>.stream.jsonl), the session's stderr (<bead>.stderr.log), and the
test-gate output (<bead>.tests.log). Compact per-event progress (assistant
text, tool calls, result/cost) is echoed to the console as the session runs.

Work-log capture (--work-log auto|on|off, default auto = on when a
work-log skill dir exists user- or project-level): each session is asked to
invoke the existing work-log skill itself — reused, never reimplemented
here — before committing, so the entry lands inside the bead's own commit
and its provenance session-id is the session that did the work. The runner
only warns (never fails) when work-log.md didn't grow during a bead.

The prompt is delivered on the session's stdin, never as a positional
argument — claude's --allowedTools is variadic and eats a trailing
positional prompt ("Input must be provided either through stdin...").

Env: BD_BIN / CLAUDE_BIN override the binaries (used by the test suite);
CLAUDE_EXTRA_ARGS is shlex-split into extra claude flags.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BD = os.environ.get("BD_BIN", "bd")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")

_TITLE_CUE_RE = re.compile(r"\[(haiku|sonnet|opus|fable)(-ok)?\]", re.IGNORECASE)

RUNLOG: "RunLog | None" = None


class RunLog:
    """Timestamped append-only run.log; most entries also echo to stdout."""

    def __init__(self, path: Path) -> None:
        self._fh = open(path, "a", buffering=1)

    def log(self, msg: str, console: bool = True) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._fh.write(f"{stamp} {msg}\n")
        if console:
            print(msg, flush=True)


def die(msg: str) -> None:
    if RUNLOG is not None:
        RUNLOG.log(f"FATAL: {msg}", console=False)
    print(f"bd-run-beads: {msg}", file=sys.stderr)
    sys.exit(1)


class IssueCache:
    """One `bd show --json` per id, cached; `fresh=True` re-reads (gates
    must see the status a session just wrote, not the planning snapshot)."""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def show(self, issue_id: str, fresh: bool = False) -> dict:
        if fresh or issue_id not in self._docs:
            proc = subprocess.run(
                [BD, "show", issue_id, "--json"], capture_output=True, text=True
            )
            if proc.returncode != 0:
                die(f"bd show {issue_id} failed: {proc.stderr.strip()}")
            self._docs[issue_id] = json.loads(proc.stdout)[0]
        return self._docs[issue_id]


def blocks_deps(doc: dict) -> list[str]:
    return [
        dep["id"]
        for dep in doc.get("dependencies") or []
        if dep.get("dependency_type", "blocks") == "blocks"
    ]


def model_for(doc: dict, default_model: str) -> tuple[str, str]:
    """-> (model, cue-source). Label wins over title cue wins over default."""
    for label in doc.get("labels") or []:
        if label.startswith("model:"):
            return label[len("model:"):], "label"
    match = _TITLE_CUE_RE.search(doc.get("title") or "")
    if match:
        return match.group(1).lower(), "title"
    return default_model, "default"


def resolve(targets: list[str], issues: IssueCache) -> tuple[list[str], list[str]]:
    """DFS post-order over open blocks-dependencies: deps first, deduped.
    Closed beads are recorded but not ordered (their subtree is done)."""
    order: list[str] = []
    closed_skipped: list[str] = []
    seen: set[str] = set()
    on_path: set[str] = set()

    def visit(issue_id: str) -> None:
        if issue_id in on_path:
            die(f"dependency cycle detected at {issue_id}")
        if issue_id in seen:
            return
        seen.add(issue_id)
        doc = issues.show(issue_id)
        if doc.get("status") == "closed":
            closed_skipped.append(issue_id)
            return
        on_path.add(issue_id)
        for dep in blocks_deps(doc):
            visit(dep)
        on_path.remove(issue_id)
        order.append(issue_id)

    for target in targets:
        visit(target)
    return order, closed_skipped


def probe_test_cmd(cmd: str) -> bool:
    """A candidate must prove it can actually collect tests — existence
    isn't enough (e.g. a stale .venv whose shims point at a pre-move
    interpreter path). pytest exit 5 is "no tests collected": still a
    working runner."""
    rc = subprocess.call(
        ["bash", "-c", f"{cmd} --collect-only >/dev/null 2>&1"]
    )
    return rc in (0, 5)


def detect_test_cmd() -> str:
    candidates = []
    if os.access(".venv/bin/pytest", os.X_OK):
        candidates.append(".venv/bin/pytest -q")
    if os.path.exists("pyproject.toml"):
        if os.path.isdir("src"):
            candidates.append("PYTHONPATH=src python3 -m pytest -q")
        candidates.append("python3 -m pytest -q")
    candidates.append("pytest -q")
    for cand in candidates:
        if probe_test_cmd(cand):
            return cand
    print(
        "bd-run-beads: no working test command detected; test gate disabled",
        file=sys.stderr,
    )
    return ""


def session_prompt(issue_id: str, test_cmd: str, work_log: bool) -> str:
    steps = [
        f"Run 'bd show {issue_id}' and follow its description and acceptance criteria literally.",
        f"Claim it: bd update {issue_id} --claim",
        "Implement only this issue. Do not start, modify, or close any other bead.",
    ]
    if test_cmd:
        steps.append(f"Run the test suite until it passes: {test_cmd}")
    if work_log:
        # Reuse the work-log skill, don't reproduce its format here: the
        # worker is a single-objective session (the skill's no-confirmation
        # case), and the skill's mechanical session-id capture points at
        # this very session - the one that did the work - which is what
        # the capture audit pairs entries against.
        steps.append(
            "Log the work: invoke the work-log skill (/work-log) to append "
            "this session's entry to work-log.md. This is a single-objective "
            "session, so no confirmation gate applies; mark anything you had "
            "to infer as inferred."
        )
    steps.append(
        f"Commit the changes{' - including work-log.md -' if work_log else ''} "
        f"with '{issue_id}' in the commit message. Do not push."
    )
    steps.append(f"Close it: bd close {issue_id}")
    numbered = "\n".join(f"{n}. {step}" for n, step in enumerate(steps, 1))
    return f"Work exactly one bd issue to completion: {issue_id}.\n{numbered}"


def _squeeze(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit] + "…"


def _tool_brief(tool_input: dict) -> str:
    for key in ("command", "file_path", "pattern", "skill", "description"):
        if key in tool_input:
            return str(tool_input[key])
    return ""


def summarize_event(line: str) -> str | None:
    """One compact console line per interesting stream-json event; None for
    noise (and for non-JSON lines, which still land in the raw transcript)."""
    try:
        event = json.loads(line)
    except ValueError:
        return None
    etype = event.get("type")
    if etype == "assistant":
        parts = []
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                parts.append(_squeeze(block["text"], 100))
            elif block.get("type") == "tool_use":
                brief = _squeeze(_tool_brief(block.get("input") or {}), 80)
                parts.append(f"[{block.get('name')}] {brief}".rstrip())
        return "; ".join(parts) or None
    if etype == "result":
        bits = [f"result: {event.get('subtype')}"]
        for key in ("num_turns", "duration_ms", "total_cost_usd"):
            if key in event:
                bits.append(f"{key}={event[key]}")
        return " ".join(bits)
    return None


def run_session(
    cmd: list[str], prompt: str, stream_path: Path, stderr_path: Path, runlog: RunLog
) -> int:
    with open(stream_path, "w") as stream, open(stderr_path, "w") as errf:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errf, text=True
        )
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(prompt)
        proc.stdin.close()
        for line in proc.stdout:
            stream.write(line)
            stream.flush()
            progress = summarize_event(line)
            if progress:
                runlog.log(f"   {progress}")
        return proc.wait()


def git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    )
    return proc.stdout.strip() or "?"


def main() -> None:
    global RUNLOG

    parser = argparse.ArgumentParser(
        prog="bd-run-beads",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("targets", nargs="+", metavar="bead-id")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="print the plan (order, model, cue) and exit")
    parser.add_argument("-m", "--default-model", default="sonnet",
                        help="model when no cue matches (default: sonnet)")
    parser.add_argument("-t", "--test-cmd", default=None,
                        help='post-session test gate; "" disables. Default: auto-detect')
    parser.add_argument("--permission-mode", default="acceptEdits",
                        help="passed to claude (default: acceptEdits)")
    parser.add_argument("--allowed-tools", default="",
                        help="passed to claude as --allowedTools")
    parser.add_argument("--log-dir", default=".bd-run-beads",
                        help="root for per-run log dirs (default: .bd-run-beads)")
    parser.add_argument("--work-log", choices=["auto", "on", "off"], default="auto",
                        help="have each session append a work-log.md entry via the "
                             "work-log skill (auto: on when the skill is installed)")
    args = parser.parse_args()

    if args.work_log == "auto":
        work_log = (Path.home() / ".claude/skills/work-log").is_dir() \
            or Path(".claude/skills/work-log").is_dir()
    else:
        work_log = args.work_log == "on"

    test_cmd = args.test_cmd if args.test_cmd is not None else detect_test_cmd()

    issues = IssueCache()
    order, closed_skipped = resolve(args.targets, issues)

    plan_lines = [f"test gate: {test_cmd or '<disabled>'}",
                  f"Execution plan ({len(order)} beads):"]
    plan_model: dict[str, str] = {}
    for step, issue_id in enumerate(order, 1):
        doc = issues.show(issue_id)
        model, cue = model_for(doc, args.default_model)
        plan_model[issue_id] = model
        plan_lines.append(
            f"{step:2d}  {issue_id} {model} ({cue})  {doc.get('title') or ''}"
        )
    for issue_id in closed_skipped:
        plan_lines.append(f" -  {issue_id} skipped (closed)")
    print("\n".join(plan_lines))
    if not order:
        print("nothing to do")
        return
    if args.dry_run:
        return

    run_dir = Path(args.log_dir) / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    RUNLOG = runlog = RunLog(run_dir / "run.log")
    runlog.log(f"command: {shlex.join(sys.argv)}", console=False)
    for line in plan_lines:
        runlog.log(line, console=False)
    print(f"logs: {run_dir}")

    for issue_id in order:
        # a session may already have closed it (rerun, or manual work between)
        if issues.show(issue_id, fresh=True).get("status") == "closed":
            runlog.log(f"== {issue_id} already closed, skipping")
            continue

        model = plan_model[issue_id]
        started = time.monotonic()
        runlog.log(f"== {issue_id} ({model}) start head={git_head()}")
        work_log_path = Path("work-log.md")
        work_log_size = work_log_path.stat().st_size if work_log_path.exists() else 0

        stream_path = run_dir / f"{issue_id}.stream.jsonl"
        stderr_path = run_dir / f"{issue_id}.stderr.log"
        cmd = [CLAUDE, "-p", "--verbose", "--output-format", "stream-json",
               "--model", model, "--permission-mode", args.permission_mode]
        if args.allowed_tools:
            cmd += ["--allowedTools", args.allowed_tools]
        cmd += shlex.split(os.environ.get("CLAUDE_EXTRA_ARGS", ""))

        rc = run_session(cmd, session_prompt(issue_id, test_cmd, work_log),
                         stream_path, stderr_path, runlog)
        if rc != 0:
            die(f"{issue_id}: claude session exited {rc} "
                f"(transcript: {stream_path}, stderr: {stderr_path})")

        # Hard gates: the session's own claims don't count.
        if test_cmd:
            tests_path = run_dir / f"{issue_id}.tests.log"
            with open(tests_path, "w") as tests_fh:
                gate_rc = subprocess.call(
                    ["bash", "-c", test_cmd],
                    stdout=tests_fh, stderr=subprocess.STDOUT,
                )
            if gate_rc != 0:
                for tail_line in tests_path.read_text().splitlines()[-15:]:
                    runlog.log(f"   {tail_line}", console=False)
                die(f"{issue_id}: test gate failed after session "
                    f"({test_cmd}); output: {tests_path}")
        if issues.show(issue_id, fresh=True).get("status") != "closed":
            die(f"{issue_id}: session ended without closing the bead "
                f"(transcript: {stream_path})")
        if work_log:
            # warn-only: a missing log entry is a capture gap, not a reason
            # to strand the rest of the dependency tree
            new_size = work_log_path.stat().st_size if work_log_path.exists() else 0
            if new_size <= work_log_size:
                runlog.log(f"   warning: {issue_id}: no work-log entry detected "
                           f"(work-log.md unchanged)")
        runlog.log(
            f"== {issue_id} done in {time.monotonic() - started:.0f}s head={git_head()}"
        )

    runlog.log(
        f"All {len(order)} beads completed. Logs: {run_dir}. Review the diff, then push."
    )


if __name__ == "__main__":
    main()
