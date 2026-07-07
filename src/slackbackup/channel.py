#!/usr/bin/env python3
"""`slackbackup channel ...` - register/list/validate channels.json entries."""
import argparse
import sys
from pathlib import Path

from . import channel_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("channel", help="register and validate tracked channels")
    sub = group.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser(
        "register",
        help="look up a channel by name/id and add it to channels.json - both "
        "arguments accept globs or comma-separated selector lists to register many "
        "channels/workspaces at once",
        epilog=(
            "Examples:\n"
            "  ./slackbackup channel register f3pugetsound helpdesk\n"
            "  ./slackbackup channel register 'f3pugetsound,f3kirkland' 'helpdesk,event-*'\n"
            "  ./slackbackup channel register 'f3*' '*'  "
            "# every new public channel, every registered f3* workspace\n"
            "Output: appends {id, name, workspace} per new channel to --channels-file\n"
            "        (default ./channels.json). A plain name/id (no glob characters\n"
            "        in either argument) keeps the original single-match behavior -\n"
            "        errors on no match or an ambiguous match instead of registering\n"
            "        nothing. Any glob character ('*', '?', '[') in either argument\n"
            "        or a comma-separated list switches to the bulk path, which always checks the full (not\n"
            "        just member) channel catalog and silently registers zero or\n"
            "        more channels - nothing to call ambiguous. The bulk path always\n"
            "        skips private, archived, and \"shuttered*\"-named channels,\n"
            "        regardless of the glob."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_register.add_argument("workspace", help="exact workspace name, a glob like 'f3*', or a comma-separated list")
    p_register.add_argument(
        "channel", help="channel name (with or without #), raw channel id, a glob like '*', or a comma-separated list"
    )
    p_register.add_argument("--channels-file", default="./channels.json")
    p_register.set_defaults(handler=_register)

    p_list = sub.add_parser(
        "list",
        help="list channels in a workspace, with registered/not-registered status",
        epilog=(
            "Example:\n  ./slackbackup channel list f3pugetsound\n"
            "Output: printed to stdout only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_list.add_argument("workspace")
    p_list.add_argument("--channels-file", default="./channels.json")
    p_list.set_defaults(handler=_list)

    p_validate = sub.add_parser(
        "validate",
        help="validate a channels.json file",
        epilog=(
            "Example:\n  ./slackbackup channel validate channels.json\n"
            "Output: no file written - exits 0 (valid) or 1 with an error printed to stderr."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_validate.add_argument("channels_file")
    p_validate.set_defaults(handler=_validate)


def _register(args: argparse.Namespace) -> int:
    if not (channel_logic.is_glob(args.workspace) or channel_logic.is_glob(args.channel)):
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

    result = channel_logic.register_matching(args.workspace, args.channel, Path(args.channels_file))

    for workspace in result["workspaces_skipped_unregistered"]:
        print(
            f"channel register: skipping '{workspace}' - not registered yet "
            f"(run: workspace register {workspace} <cookie>)",
            file=sys.stderr,
        )

    for entry in result["added"]:
        print(f"channel register: added {entry['name']} ({entry['id']}) in {entry['workspace']} to {args.channels_file}")

    print(
        f"channel register: {len(result['added'])} new channel(s) across "
        f"{len(result['workspaces_checked'])} workspace(s)"
    )
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
