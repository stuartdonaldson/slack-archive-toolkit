#!/usr/bin/env python3
"""`slackbackup catalog ...` - per-workspace channel catalog (fast/full tier)."""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import catalog_logic, channel_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("catalog", help="show the channel catalog for a workspace")
    sub = group.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser(
        "show",
        help=(
            "print the catalog (id, member, tracked, last_posted_live, last_posted_cached, "
            "registered_at, name, description, creator, created)"
        ),
        epilog=(
            "Example:\n  ./slackbackup catalog show f3pugetsound --full --archive-root ~/slack-backups\n"
            "Output: printed to stdout (tab-separated); also refreshes the cache file at\n"
            "        ~/.cache/slackbackup/<workspace>.catalog.json as a side effect.\n"
            "last_posted_live is recomputed now from --archive-root (needs a local archive).\n"
            "last_posted_cached/registered_at are persisted by `backup run`/`channel register`\n"
            "over time - cached stays unset until a backup actually finds message data; until\n"
            "then registered_at (when we started tracking it) is the best signal available."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_show.add_argument("workspace")
    p_show.add_argument("--full", action="store_true", help="also refresh/include the expensive full channel listing")
    p_show.add_argument("--channels-file", default="./channels.json")
    p_show.add_argument(
        "--archive-root", default=None, help="enables last_posted_live for tracked channels (local-only)"
    )
    p_show.set_defaults(handler=_show)

    p_list = sub.add_parser(
        "list",
        help="human-readable view of tracked channels: name, last-updated, message count",
        epilog=(
            "Example:\n  ./slackbackup catalog list f3pugetsound --archive-root ~/slack-backups --description\n"
            "Output: printed to stdout, sorted most-recently-updated first. Local-only - never\n"
            "        calls the Slack API or refreshes the catalog cache, just reads what's\n"
            "        already cached/on-disk (run `catalog show`/`backup sync-catalog` first if\n"
            "        the data looks stale). Message count requires --archive-root; omitted\n"
            "        (shown as '-') without it."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_list.add_argument("workspace")
    p_list.add_argument("--channels-file", default="./channels.json")
    p_list.add_argument("--archive-root", default=None, help="enables message counts (local-only)")
    p_list.add_argument("--description", action="store_true", help="include the channel description column")
    p_list.add_argument("--topic", action="store_true", help="include the raw topic column")
    p_list.set_defaults(handler=_list)


def _last_posted_live(archive_root: str | None, workspace: str, channel_name: str) -> str:
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


def _created_at(created: int | None) -> str:
    if not created:
        return ""
    return datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _message_count_local(archive_root: str | None, workspace: str, channel_name: str) -> int | None:
    if not archive_root:
        return None
    db_path = Path(archive_root) / workspace / channel_name / "slackdump.sqlite"
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM MESSAGE").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def _list(args: argparse.Namespace) -> int:
    catalog = catalog_logic.load(catalog_logic.DEFAULT_CACHE_DIR, args.workspace)
    tracked = [
        entry for entry in channel_logic.load(Path(args.channels_file)) if entry["workspace"] == args.workspace
    ]

    rows = []
    for entry in tracked:
        channel = catalog["channels"].get(entry["id"], {})
        rows.append(
            {
                "name": entry["name"],
                "last_updated": catalog_logic.effective_recency(catalog, entry["id"]) or "unknown",
                "message_count": _message_count_local(args.archive_root, args.workspace, entry["name"]),
                "description": channel.get("description") or "",
                "topic": channel.get("topic") or "",
            }
        )
    rows.sort(key=lambda r: r["last_updated"], reverse=True)

    name_width = max([len("NAME")] + [len(r["name"]) for r in rows]) + 2
    header = f"{'NAME':<{name_width}}{'LAST UPDATED':<22}{'MESSAGES':>9}"
    if args.description:
        header += "  DESCRIPTION"
    if args.topic:
        header += "  TOPIC"
    print(header)

    for r in rows:
        count = str(r["message_count"]) if r["message_count"] is not None else "-"
        line = f"{r['name']:<{name_width}}{r['last_updated']:<22}{count:>9}"
        if args.description:
            line += f"  {r['description']}"
        if args.topic:
            line += f"  {r['topic']}"
        print(line)
    return 0


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

    print(
        "id\tmember\ttracked\tlast_posted_live\tlast_posted_cached\tregistered_at\t"
        "name\tdescription\tcreator\tcreated"
    )
    for channel_id, channel in data["channels"].items():
        tracked_name = tracked.get(channel_id)
        is_tracked = tracked_name is not None
        last_posted_live = _last_posted_live(args.archive_root, args.workspace, tracked_name) if is_tracked else ""
        print(
            f"{channel_id}\t{'yes' if channel['member'] else 'no'}\t"
            f"{'yes' if is_tracked else 'no'}\t{last_posted_live}\t"
            f"{channel.get('last_posted') or ''}\t{channel.get('registered_at') or ''}\t"
            f"{channel['name']}\t{channel['description']}\t"
            f"{channel.get('creator') or ''}\t{_created_at(channel.get('created'))}"
        )
    return 0
