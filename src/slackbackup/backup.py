#!/usr/bin/env python3
"""`slackbackup backup ...` - per-channel archive/resume and multi-channel runs."""
import argparse
import sys
from pathlib import Path

from . import backup_logic, channel_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("backup", help="archive/resume Slack channels")
    sub = group.add_subparsers(dest="command", required=True)

    p_channel = sub.add_parser("channel", help="back up a single channel (archive if new, resume if existing)")
    p_channel.add_argument("-f", "--full", action="store_true", help="full re-sync into a fresh dated directory")
    p_channel.add_argument("channel_id")
    p_channel.add_argument("channel_slug")
    p_channel.add_argument("workspace")
    p_channel.add_argument("archive_root")
    p_channel.set_defaults(handler=_channel)

    p_run = sub.add_parser("run", help="back up every channel listed in channels.json")
    p_run.add_argument("-f", "--full", action="store_true")
    p_run.add_argument("channels_file")
    p_run.add_argument("archive_root")
    p_run.set_defaults(handler=_run)

    p_list = sub.add_parser("list", help="show archived status, message count, and last-modified per tracked channel (local-only)")
    p_list.add_argument("channels_file")
    p_list.add_argument("archive_root")
    p_list.set_defaults(handler=_list)


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
