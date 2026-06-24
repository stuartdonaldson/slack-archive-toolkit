#!/usr/bin/env python3
"""Per-channel archive/resume and multi-channel runs. Ported from
backup.sh + run-backups.sh.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import catalog_logic, channel_logic, slackdump


def channel_dir(archive_root: Path, workspace: str, channel_slug: str) -> Path:
    # Keyed by <workspace>/<slug>, not slug alone - two different channels
    # in different workspaces sharing a slug must not collide into one
    # archive.
    return archive_root / workspace / channel_slug


def backup_channel(
    channel_id: str,
    channel_slug: str,
    workspace: str,
    archive_root: Path,
    full: bool = False,
) -> None:
    slackdump.select_workspace_or_die(workspace)
    archive_root.mkdir(parents=True, exist_ok=True)

    if full:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        full_dir = archive_root / workspace / f"{channel_slug}-full-{stamp}"
        print(
            f"backup: full re-sync requested — archiving into fresh dir {full_dir} "
            "(incremental archive untouched)"
        )
        slackdump.archive(channel_id, full_dir)
        return

    channel_directory = channel_dir(archive_root, workspace, channel_slug)
    db_path = channel_directory / "slackdump.sqlite"

    if db_path.exists():
        print(f"backup: existing archive found at {db_path} — resuming")
        # -dedupe deliberately never passed: confirmed to delete thread-root
        # rows (SlackBackup-d3r). Accept duplicate rows across resume cycles.
        slackdump.resume(channel_directory)
    else:
        print(f"backup: no existing archive — running full archive into {channel_directory}")
        slackdump.archive(channel_id, channel_directory)


def run(channels_file: Path, archive_root: Path, full: bool = False) -> bool:
    """Returns True if every channel backed up successfully."""
    entries = channel_logic.validate(channels_file)

    for workspace in sorted({entry["workspace"] for entry in entries}):
        catalog_logic.refresh_fast(workspace)

    all_ok = True
    for entry in entries:
        print(f"backup run: backing up {entry['name']} ({entry['id']}) in {entry['workspace']}")
        try:
            backup_channel(entry["id"], entry["name"], entry["workspace"], archive_root, full)
        except slackdump.SlackdumpError as exc:
            print(f"backup run: backup failed for {entry['name']} ({entry['id']}): {exc}", file=sys.stderr)
            all_ok = False

    return all_ok


def _local_status(db_path: Path) -> dict:
    """Read-only, local-only (no API call): message count and last-modified
    time of a channel's archive, if it exists."""
    if not db_path.exists():
        return {"archived": False, "message_count": None, "last_modified": None}

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM MESSAGE").fetchone()[0]
    finally:
        conn.close()

    mtime = datetime.fromtimestamp(db_path.stat().st_mtime, tz=timezone.utc)
    return {
        "archived": True,
        "message_count": count,
        "last_modified": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def list_status(channels_file: Path, archive_root: Path) -> list[dict]:
    """One row per tracked channel: {id, name, workspace, archived,
    message_count, last_modified}. Entirely local - no API calls."""
    entries = channel_logic.validate(channels_file)
    rows = []
    for entry in entries:
        db_path = channel_dir(archive_root, entry["workspace"], entry["name"]) / "slackdump.sqlite"
        status = _local_status(db_path)
        rows.append({**entry, **status})
    return rows
