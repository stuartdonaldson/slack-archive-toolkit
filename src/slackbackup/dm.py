#!/usr/bin/env python3
"""`slackbackup dm ...` - discover/register/validate tracked DM conversations
in dms.json, the DM counterpart to channel.py/channels.json."""
import argparse
import sys
from pathlib import Path

from . import channel_logic, dm_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("dm", help="register and validate tracked DM/group-DM conversations")
    sub = group.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser(
        "register-matching",
        help="discover DM/group-DM conversations across registered workspaces and add them to dms.json",
        epilog=(
            "Examples:\n"
            "  ./slackbackup dm register-matching 'f3*'\n"
            "  ./slackbackup dm register-matching '*' --no-group\n"
            "Output: appends {id, name, workspace} per new conversation to --dms-file\n"
            "        (default ./dms.json, gitignored - see .gitignore). A 1:1 DM's\n"
            "        synthesized name is 'dm-<other-user-id>' (Slack never gives one);\n"
            "        a group DM keeps Slack's own 'mpdm-...' name. Also PRUNES already-\n"
            "        tracked conversations no longer present in a fresh listing\n"
            "        (reported as \"removed\", reason \"missing\"). --no-group excludes\n"
            "        group DMs (mpim), tracking 1:1 DMs only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_register.add_argument("workspace", help="exact workspace name, a glob like 'f3*', or a comma-separated list")
    p_register.add_argument("--dms-file", default="./dms.json")
    p_register.add_argument(
        "--no-group", dest="include_group", action="store_false", default=True,
        help="track 1:1 DMs only, excluding group DMs (mpim)",
    )
    p_register.set_defaults(handler=_register)

    p_validate = sub.add_parser(
        "validate",
        help="validate a dms.json file",
        epilog=(
            "Example:\n  ./slackbackup dm validate dms.json\n"
            "Output: no file written - exits 0 (valid) or 1 with an error printed to stderr."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_validate.add_argument("dms_file")
    p_validate.set_defaults(handler=_validate)


def _register(args: argparse.Namespace) -> int:
    result = dm_logic.register_matching(args.workspace, Path(args.dms_file), include_group=args.include_group)

    for workspace in result["workspaces_skipped_unregistered"]:
        print(
            f"dm register-matching: skipping '{workspace}' - not registered yet "
            f"(run: workspace register {workspace} <cookie>)",
            file=sys.stderr,
        )

    for entry in result["added"]:
        print(f"dm register-matching: added {entry['name']} ({entry['id']}) in {entry['workspace']} to {args.dms_file}")

    for entry in result["removed"]:
        print(
            f"dm register-matching: removed {entry['name']} ({entry['id']}) from "
            f"{entry['workspace']} — {entry['reason']}"
        )

    print(
        f"dm register-matching: {len(result['added'])} new conversation(s), "
        f"{len(result['removed'])} removed, across {len(result['workspaces_checked'])} workspace(s)"
    )
    return 0


def _validate(args: argparse.Namespace) -> int:
    try:
        channel_logic.validate(Path(args.dms_file))
    except channel_logic.ChannelError as exc:
        print(f"dm validate: {exc}", file=sys.stderr)
        return 1
    return 0
