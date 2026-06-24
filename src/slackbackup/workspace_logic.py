#!/usr/bin/env python3
"""Workspace registration: tokens file lookup + cookie -> slackdump
workspace import. Originally ported from register-workspace.sh (since
removed - this is now the only implementation).

Prerequisite: a tokens file (default ~/.slackdump-tokens.json) containing a
flat JSON object mapping workspace identifiers to their xoxc- token, e.g.
{"f3pugetsound": "xoxc-...", "f3kirkland": "xoxc-..."}. See README.md's
"Getting Started" section for how to populate it (DevTools console
snippet) and where to find the xoxd- cookie - that's a one-time, manual,
browser-side step that can't be scripted around.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from . import slackdump

DEFAULT_TOKENS_FILE = Path.home() / ".slackdump-tokens.json"

_REGISTERED_LINE_RE = re.compile(r"^(=> )?\s*([^\s]+)\s*\(file:.*last modified: (.*)\)\s*$")


class WorkspaceError(RuntimeError):
    pass


def normalize(workspace_raw: str) -> str:
    workspace = workspace_raw.strip().lower()
    workspace = re.sub(r"^https?://", "", workspace)
    workspace = re.sub(r"\.slack\.com$", "", workspace)
    return workspace


def load_tokens(tokens_file: Path) -> dict:
    if not tokens_file.exists():
        raise WorkspaceError(
            f"tokens file not found: {tokens_file} (see README.md's "
            "\"Getting Started\" section for how to create it)"
        )
    return json.loads(tokens_file.read_text())


def parse_registered(raw: str) -> dict[str, dict]:
    """Parses `slackdump workspace list` output into
    {bare_name: {"current": bool, "last_modified": str}}."""
    registered: dict[str, dict] = {}
    for line in raw.splitlines():
        match = _REGISTERED_LINE_RE.match(line)
        if not match:
            continue
        is_current, name, last_modified = match.groups()
        bare = re.sub(r"\.slack\.com$", "", name)
        registered[bare] = {"current": bool(is_current), "last_modified": last_modified}
    return registered


def status(tokens_file: Path = DEFAULT_TOKENS_FILE) -> dict:
    """Returns {"known": [{name, registered, current, last_modified}, ...],
    "others": [bare_name, ...]} - "others" is workspaces slackdump knows
    about that aren't in the tokens file."""
    tokens = load_tokens(tokens_file)
    registered = parse_registered(slackdump.workspace_list())

    known = []
    for name in tokens:
        info = registered.get(name)
        known.append(
            {
                "name": name,
                "registered": info is not None,
                "current": info["current"] if info else False,
                "last_modified": info["last_modified"] if info else None,
            }
        )

    others = [name for name in registered if name not in tokens]
    return {"known": known, "others": others}


def register(workspace_raw: str, cookie: str, tokens_file: Path = DEFAULT_TOKENS_FILE) -> str:
    """Registers `workspace_raw` with slackdump using its token from
    `tokens_file` plus the given fresh session cookie. Returns the
    normalized workspace name. Raises WorkspaceError if no token is on
    file for it."""
    tokens = load_tokens(tokens_file)
    workspace = normalize(workspace_raw)

    token = tokens.get(workspace)
    if not token:
        known = ", ".join(tokens.keys())
        raise WorkspaceError(f"no token found for '{workspace}' in {tokens_file} (known: {known})")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as env_file:
        env_file.write(f"SLACK_TOKEN={token}\nSLACK_COOKIE={cookie}\n")
        env_path = Path(env_file.name)

    try:
        slackdump.workspace_import(env_path)
    finally:
        env_path.unlink(missing_ok=True)

    return workspace
