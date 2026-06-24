#!/usr/bin/env python3
"""`slackbackup search ...` - cross-workspace message search to HTML."""
import argparse


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("search", help="search across registered f3* workspaces")
    sub = group.add_subparsers(dest="command", required=True)

    p_messages = sub.add_parser("messages", help="search messages, render results as one HTML report")
    p_messages.add_argument("query", nargs="+", help="search query words (implicit AND, no OR operator)")
    p_messages.add_argument("--out", default="./search-results.html")
    p_messages.set_defaults(handler=_not_implemented)


def _not_implemented(args: argparse.Namespace) -> int:
    raise NotImplementedError("search commands not yet ported from search-messages.sh / lib/message_search_helpers.sh")
