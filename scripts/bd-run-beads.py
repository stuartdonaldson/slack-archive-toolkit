#!/usr/bin/env python3
"""bd-run-beads.py (bd SlackBackup-j7b) — run bd issues to completion via
headless `claude -p` sessions, one session per bead, dependency-first.

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
from datetime import datetime, timezone

BD = os.environ.get("BD_BIN", "bd")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")

_TITLE_CUE_RE = re.compile(r"\[(haiku|sonnet|opus|fable)(-ok)?\]", re.IGNORECASE)


def die(msg: str) -> None:
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


def session_prompt(issue_id: str, test_cmd: str) -> str:
    lines = [
        f"Work exactly one bd issue to completion: {issue_id}.",
        f"1. Run 'bd show {issue_id}' and follow its description and acceptance criteria literally.",
        f"2. Claim it: bd update {issue_id} --claim",
        "3. Implement only this issue. Do not start, modify, or close any other bead.",
    ]
    if test_cmd:
        lines.append(f"4. Run the test suite until it passes: {test_cmd}")
    lines.append(
        f"5. Commit the changes with '{issue_id}' in the commit message. Do not push."
    )
    lines.append(f"6. Close it: bd close {issue_id}")
    return "\n".join(lines)


def main() -> None:
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
    args = parser.parse_args()

    test_cmd = args.test_cmd if args.test_cmd is not None else detect_test_cmd()

    issues = IssueCache()
    order, closed_skipped = resolve(args.targets, issues)

    print(f"test gate: {test_cmd or '<disabled>'}")
    print(f"Execution plan ({len(order)} beads):")
    plan_model: dict[str, str] = {}
    for step, issue_id in enumerate(order, 1):
        doc = issues.show(issue_id)
        model, cue = model_for(doc, args.default_model)
        plan_model[issue_id] = model
        print(f"{step:2d}  {issue_id} {model} ({cue})  {doc.get('title') or ''}")
    for issue_id in closed_skipped:
        print(f" -  {issue_id} skipped (closed)")
    if not order:
        print("nothing to do")
        return
    if args.dry_run:
        return

    for issue_id in order:
        # a session may already have closed it (rerun, or manual work between)
        if issues.show(issue_id, fresh=True).get("status") == "closed":
            print(f"== {issue_id} already closed, skipping")
            continue

        model = plan_model[issue_id]
        now = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
        print(f"== {issue_id} ({model}) {now}", flush=True)

        cmd = [CLAUDE, "-p", "--model", model, "--permission-mode", args.permission_mode]
        if args.allowed_tools:
            cmd += ["--allowedTools", args.allowed_tools]
        cmd += shlex.split(os.environ.get("CLAUDE_EXTRA_ARGS", ""))
        cmd.append(session_prompt(issue_id, test_cmd))
        if subprocess.call(cmd) != 0:
            die(f"{issue_id}: claude session exited non-zero")

        # Hard gates: the session's own claims don't count.
        if test_cmd and subprocess.call(["bash", "-c", test_cmd]) != 0:
            die(f"{issue_id}: test gate failed after session ({test_cmd})")
        if issues.show(issue_id, fresh=True).get("status") != "closed":
            die(f"{issue_id}: session ended without closing the bead")
        print(f"== {issue_id} done")

    print(f"All {len(order)} beads completed. Review the diff, then push.")


if __name__ == "__main__":
    main()
