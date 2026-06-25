#!/usr/bin/env python3
"""Thin subprocess wrapper around the `slackdump` binary. Every call to the
binary in this project goes through here so call sites stay one-liners and
so tests can monkeypatch `_run` instead of mocking subprocess directly.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


class SlackdumpError(RuntimeError):
    pass


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["slackdump", *args], capture_output=True, text=True)


def select_workspace_or_die(workspace: str) -> None:
    """Tries `workspace` as-is, then with/without a '.slack.com' suffix -
    slackdump registers workspaces under either form depending on how they
    were imported, and a raw `-workspace` flag does not retry both forms
    itself (see docs/references/slackdump-cli-notes.md).
    """
    candidates = [workspace]
    if workspace.endswith(".slack.com"):
        candidates.append(workspace[: -len(".slack.com")])
    else:
        candidates.append(workspace + ".slack.com")

    for candidate in candidates:
        if _run(["workspace", "select", candidate]).returncode == 0:
            return
    raise SlackdumpError(
        f"could not select workspace '{workspace}' (tried as given, and with/without .slack.com)"
    )


def workspace_list() -> str:
    return _run(["workspace", "list"]).stdout


def workspace_import(env_file: Path) -> None:
    result = _run(["workspace", "import", str(env_file)])
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump workspace import failed: {result.stderr}")


def list_channels(member_only: bool) -> list[dict]:
    """`list channels [-member-only] -format JSON`. Always passes
    -no-chan-cache: slackdump's own internal channel-list cache (20-minute
    default, shared across every workspace under the same cache-dir) was
    observed returning another, recently-queried workspace's stale result
    right after switching workspaces. We maintain our own catalog cache
    already, so slackdump's internal one is pure redundant risk - always
    disabled. Always passes -no-json so it doesn't also drop a
    `channels-<team>.json` file into the current directory as a side effect.
    """
    args = ["list", "channels", "-format", "JSON", "-no-json", "-no-chan-cache"]
    if member_only:
        args.append("-member-only")
    result = _run(args)
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump list channels failed: {result.stderr}")
    text = result.stdout.strip()
    entries = json.loads(text) if text else []
    # Confirmed empirically (even with -member-only): this also returns DM
    # conversations - is_channel:false, blank name, id prefixed D instead of
    # C. Multi-person DMs (group chats) are sneakier: Slack reports
    # is_channel:true for them too, with a C-prefixed id - the only
    # reliable signal is the name, which Slack always prefixes "mpdm-" and
    # embeds the real usernames of every participant in (a privacy leak,
    # not just noise, if these slip into channels.json). Filter both out
    # here so no caller (catalog/channel registration) ever sees them, on
    # either tier.
    return [e for e in entries if e.get("is_channel") and not e.get("name", "").startswith("mpdm-")]


def search_files(term: str, out_dir: Path) -> bool:
    return _run(["search", "files", "-o", str(out_dir), term]).returncode == 0


def search_messages(query_terms: list[str], out_dir: Path) -> bool:
    return _run(["search", "messages", "-o", str(out_dir), *query_terms]).returncode == 0


def archive(channel_id: str, out_dir: Path) -> None:
    result = _run(["archive", "-o", str(out_dir), channel_id])
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump archive failed: {result.stderr}")


def resume(channel_dir: Path) -> None:
    # -dedupe deliberately never passed: confirmed to delete thread-root
    # rows (SlackBackup-d3r). Accept duplicate rows across resume cycles.
    result = _run(["resume", str(channel_dir)])
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump resume failed: {result.stderr}")


def convert_export(channel_dir: Path, out_dir: Path) -> None:
    """`convert -f export` takes the archive *directory* (containing
    slackdump.sqlite) as its source, not the .sqlite file path itself."""
    result = _run(["convert", "-f", "export", "-o", str(out_dir), str(channel_dir)])
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump convert -f export failed: {result.stderr}")
