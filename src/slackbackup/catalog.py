#!/usr/bin/env python3
"""`slackbackup catalog ...` - per-workspace channel catalog (fast/full tier)."""
import argparse
import sqlite3
from pathlib import Path

from . import catalog_logic, channel_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("catalog", help="show the channel catalog for a workspace")
    sub = group.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="print the catalog (id, member, tracked, last_posted, name, description)")
    p_show.add_argument("workspace")
    p_show.add_argument("--full", action="store_true", help="also refresh/include the expensive full channel listing")
    p_show.add_argument("--channels-file", default="./channels.json")
    p_show.add_argument("--archive-root", default=None, help="enables last_posted for tracked channels (local-only)")
    p_show.set_defaults(handler=_show)


def _last_posted(archive_root: str | None, workspace: str, channel_name: str) -> str:
    if not archive_root:
        return ""
    db_path = Path(archive_root) / workspace / channel_name / "slackdump.sqlite"
    if not db_path.exists():
        return ""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT MAX(ts) FROM MESSAGE").fetchone()
        return str(row[0]) if row and row[0] is not None else ""
    finally:
        conn.close()


def _show(args: argparse.Namespace) -> int:
    if args.full:
        data = catalog_logic.refresh_full(args.workspace)
    else:
        data = catalog_logic.refresh_fast(args.workspace)

    tracked = {
        entry["id"]: entry["name"]
        for entry in channel_logic.load(Path(args.channels_file))
        if entry["workspace"] == args.workspace
    }

    print("id\tmember\ttracked\tlast_posted\tname\tdescription")
    for channel_id, channel in data["channels"].items():
        tracked_name = tracked.get(channel_id)
        is_tracked = tracked_name is not None
        last_posted = _last_posted(args.archive_root, args.workspace, tracked_name) if is_tracked else ""
        print(
            f"{channel_id}\t{'yes' if channel['member'] else 'no'}\t"
            f"{'yes' if is_tracked else 'no'}\t{last_posted}\t"
            f"{channel['name']}\t{channel['description']}"
        )
    return 0
