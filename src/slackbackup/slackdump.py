#!/usr/bin/env python3
"""Thin subprocess wrapper around the `slackdump` binary. Every call to the
binary in this project goes through here so call sites stay one-liners and
so tests can monkeypatch `_run` instead of mocking subprocess directly.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


# Timeouts (SlackBackup sat-hh0). Observed 2026-08-09: `slackdump tools
# dedupe -mode message-key -execute` pegged at 100% CPU for 24+ minutes on a
# 966-message channel (weasel-shakers, similar scale, deduped in 185s for
# comparison) - a genuine algorithmic hang in slackdump itself, not
# I/O-blocked or WSL2-host-sleep (a separate, cosmetic wall-clock-gap
# phenomenon also seen the same night). Nothing bounded it: these calls ran
# via subprocess.run with no timeout, so one pathological channel could
# block an entire nightly run indefinitely. dedupe is a local sqlite-only
# operation (no network) and should always be fast even on large channels,
# so it gets a tight bound; archive/resume do real network I/O + file
# downloads and can legitimately run long on a channel's first-ever full
# archive, so they get generous bounds. All three are MODIFIABLE - tune if
# a legitimately large channel starts tripping one.
DEDUPE_TIMEOUT_SECONDS = 900  # 15 min - local-only; should be seconds normally
RESUME_TIMEOUT_SECONDS = 3600  # 1 hour - incremental, but lookback can be large
ARCHIVE_TIMEOUT_SECONDS = 7200  # 2 hours - first-ever full history + files


class SlackdumpError(RuntimeError):
    pass


def _run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["slackdump", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # subprocess.run already killed the child before raising this -
        # nothing left running to clean up.
        raise SlackdumpError(
            f"slackdump {' '.join(args)} timed out after {timeout}s (killed)"
        ) from exc


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
    result = _run(["archive", "-o", str(out_dir), channel_id], timeout=ARCHIVE_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump archive failed: {result.stderr}")


def resume(channel_dir: Path) -> None:
    # -dedupe deliberately never passed: confirmed to delete thread-root
    # rows (SlackBackup-d3r). Accept duplicate rows across resume cycles -
    # dedupe(), below, cleans them up as a separate, verified-safe step.
    result = _run(["resume", str(channel_dir)], timeout=RESUME_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump resume failed: {result.stderr}")


def dedupe(channel_dir: Path) -> int:
    """Removes duplicate MESSAGE/CHANNEL/CHANNEL_USER/FILE rows that
    `resume`'s lookback window re-inserts every cycle (SlackBackup-9hq).
    Returns the number of message rows removed.

    This is the standalone `slackdump tools dedupe` command, NOT the buggy
    `resume -dedupe` flag `resume()` above deliberately avoids - confirmed
    (2026-08-08, sat-9hq) on a real archive that `-mode message-key -execute`
    here collapses duplicate rows down to one per distinct message `ts`
    while leaving IS_PARENT=1 thread-root rows intact, unlike the inline
    flag's confirmed thread-root-deletion bug. `-mode message-key` (vs.
    the default `exact`) collapses by (channel, ts) even if Slack-regenerated
    fields differ between fetches, keeping the latest copy.
    """
    result = _run(
        ["tools", "dedupe", "-mode", "message-key", "-execute", str(channel_dir)],
        timeout=DEDUPE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump tools dedupe failed: {result.stderr}")
    for line in result.stdout.splitlines():
        if line.startswith("Removed messages:"):
            return int(line.split(":", 1)[1].strip())
    return 0


def convert_export(channel_dir: Path, out_dir: Path) -> None:
    """`convert -f export` takes the archive *directory* (containing
    slackdump.sqlite) as its source, not the .sqlite file path itself."""
    result = _run(["convert", "-f", "export", "-o", str(out_dir), str(channel_dir)])
    if result.returncode != 0:
        raise SlackdumpError(f"slackdump convert -f export failed: {result.stderr}")
