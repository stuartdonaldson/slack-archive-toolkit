#!/usr/bin/env python3
"""`slackbackup workspace ...` - register/list slackdump workspace sessions."""
import argparse

from . import workspace_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("workspace", help="manage slackdump workspace sessions")
    sub = group.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register", help="register a workspace from a saved token + fresh cookie")
    p_register.add_argument("name", help="workspace name or URL, e.g. f3pugetsound")
    p_register.add_argument("cookie", help="fresh xoxd- session cookie")
    p_register.set_defaults(handler=_register)

    p_list = sub.add_parser("list", help="show known workspaces and registration status")
    p_list.set_defaults(handler=_list)


def _register(args: argparse.Namespace) -> int:
    workspace = workspace_logic.register(args.name, args.cookie)
    print(f"workspace: registered '{workspace}'")
    return 0


def _list(args: argparse.Namespace) -> int:
    result = workspace_logic.status()
    print(f"Known workspaces (from {workspace_logic.DEFAULT_TOKENS_FILE}):")
    for row in result["known"]:
        if row["registered"]:
            marker = "registered, current" if row["current"] else "registered"
            print(f"  {row['name']} — {marker}, last registered {row['last_modified']}")
        else:
            print(f"  {row['name']} — token known, not yet registered (run: workspace register {row['name']} <cookie>)")

    if result["others"]:
        print("Other registered workspaces (no token on file):")
        for name in result["others"]:
            print(f"  {name}")
    return 0
