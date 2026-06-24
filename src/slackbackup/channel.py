#!/usr/bin/env python3
"""`slackbackup channel ...` - register/list/validate channels.json entries."""
import argparse
import sys
from pathlib import Path

from . import channel_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("channel", help="register and validate tracked channels")
    sub = group.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register", help="look up a channel by name/id and add it to channels.json")
    p_register.add_argument("workspace")
    p_register.add_argument("channel", help="channel name (with or without #) or raw channel id")
    p_register.add_argument("--channels-file", default="./channels.json")
    p_register.set_defaults(handler=_register)

    p_list = sub.add_parser("list", help="list channels in a workspace, with registered/not-registered status")
    p_list.add_argument("workspace")
    p_list.add_argument("--channels-file", default="./channels.json")
    p_list.set_defaults(handler=_list)

    p_validate = sub.add_parser("validate", help="validate a channels.json file")
    p_validate.add_argument("channels_file")
    p_validate.set_defaults(handler=_validate)


def _register(args: argparse.Namespace) -> int:
    try:
        channel_id, name, already_present = channel_logic.register(
            args.workspace, args.channel, Path(args.channels_file)
        )
    except channel_logic.ChannelError as exc:
        print(f"channel register: {exc}", file=sys.stderr)
        return 1

    if already_present:
        print(f"channel register: {name} ({channel_id}) in {args.workspace} is already in {args.channels_file}")
    else:
        print(f"channel register: added {name} ({channel_id}) in {args.workspace} to {args.channels_file}")
    return 0


def _list(args: argparse.Namespace) -> int:
    rows = channel_logic.list_for_workspace(args.workspace, Path(args.channels_file))
    print(f"Channels in {args.workspace}:")
    for row in rows:
        status = "registered" if row["registered"] else "not registered"
        print(f"  {row['name']} ({row['id']}) — {status}")
    return 0


def _validate(args: argparse.Namespace) -> int:
    try:
        channel_logic.validate(Path(args.channels_file))
    except channel_logic.ChannelError as exc:
        print(f"channel validate: {exc}", file=sys.stderr)
        return 1
    return 0
