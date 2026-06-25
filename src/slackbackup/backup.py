#!/usr/bin/env python3
"""`slackbackup backup ...` - per-channel archive/resume and multi-channel runs."""
import argparse
import sys
from pathlib import Path

from . import backup_logic, channel_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("backup", help="archive/resume Slack channels")
    sub = group.add_subparsers(dest="command", required=True)

    p_channel = sub.add_parser(
        "channel",
        help="back up a single channel (archive if new, resume if existing)",
        epilog=(
            "Example:\n  ./slackbackup backup channel CJBG619C5 helpdesk f3pugetsound ~/slack-backups\n"
            "Output: <archive_root>/<workspace>/<channel_slug>/slackdump.sqlite\n"
            "        (with -f/--full: a fresh <channel_slug>-full-<UTC-timestamp>/ dir instead)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_channel.add_argument("-f", "--full", action="store_true", help="full re-sync into a fresh dated directory")
    p_channel.add_argument("channel_id")
    p_channel.add_argument("channel_slug")
    p_channel.add_argument("workspace")
    p_channel.add_argument("archive_root")
    p_channel.set_defaults(handler=_channel)

    p_run = sub.add_parser(
        "run",
        help="back up every channel listed in channels.json",
        epilog=(
            "Example:\n  ./slackbackup backup run channels.json ~/slack-backups\n"
            "Output: <archive_root>/<workspace>/<channel>/slackdump.sqlite per tracked channel."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_run.add_argument("-f", "--full", action="store_true")
    p_run.add_argument("channels_file")
    p_run.add_argument("archive_root")
    p_run.set_defaults(handler=_run)

    p_list = sub.add_parser(
        "list",
        help="show archived status, message count, and last-modified per tracked channel (local-only)",
        epilog=(
            "Example:\n  ./slackbackup backup list channels.json ~/slack-backups\n"
            "Output: printed to stdout (tab-separated) only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_list.add_argument("channels_file")
    p_list.add_argument("archive_root")
    p_list.set_defaults(handler=_list)

    p_sync = sub.add_parser(
        "sync-catalog",
        help="backfill catalog last_posted/registered_at from local archives only (no API calls)",
        epilog=(
            "Example:\n  ./slackbackup backup sync-catalog channels.json ~/slack-backups\n"
            "Use after interrupting a backup run, or any time the catalog's recency fields\n"
            "(last_posted/registered_at) look stale relative to what's actually on disk.\n"
            "Output: a one-line summary to stdout; no files are read beyond local archives."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_sync.add_argument("channels_file")
    p_sync.add_argument("archive_root")
    p_sync.set_defaults(handler=_sync_catalog)


def _channel(args: argparse.Namespace) -> int:
    backup_logic.backup_channel(
        args.channel_id, args.channel_slug, args.workspace, Path(args.archive_root), args.full
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    try:
        all_ok = backup_logic.run(Path(args.channels_file), Path(args.archive_root), args.full)
    except channel_logic.ChannelError as exc:
        print(f"backup run: {exc}", file=sys.stderr)
        return 1
    return 0 if all_ok else 1


def _list(args: argparse.Namespace) -> int:
    try:
        rows = backup_logic.list_status(Path(args.channels_file), Path(args.archive_root))
    except channel_logic.ChannelError as exc:
        print(f"backup list: {exc}", file=sys.stderr)
        return 1

    print("workspace\tchannel\tarchived\tmessage_count\tlast_modified")
    for row in rows:
        print(
            f"{row['workspace']}\t{row['name']}\t{'yes' if row['archived'] else 'no'}\t"
            f"{row['message_count'] if row['message_count'] is not None else ''}\t"
            f"{row['last_modified'] or ''}"
        )
    return 0


def _sync_catalog(args: argparse.Namespace) -> int:
    try:
        counts = backup_logic.sync_catalog_from_local(Path(args.channels_file), Path(args.archive_root))
    except channel_logic.ChannelError as exc:
        print(f"backup sync-catalog: {exc}", file=sys.stderr)
        return 1

    print(
        f"backup sync-catalog: {counts['total']} channel(s) - "
        f"{counts['last_posted']} last_posted set from archive data, "
        f"{counts['registered_at']} stamped registered_at (no data found)"
    )
    return 0
