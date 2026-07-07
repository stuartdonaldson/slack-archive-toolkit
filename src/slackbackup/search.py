#!/usr/bin/env python3
"""`slackbackup search ...` - cross-workspace message search to HTML."""
import argparse
import sys
from pathlib import Path

from . import search_logic, slackdump, workspace_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("search", help="search messages across workspaces matching a name or glob")
    sub = group.add_subparsers(dest="command", required=True)

    p_messages = sub.add_parser(
        "messages",
        help="search messages across workspaces matching <workspace>, render results as one HTML report",
        epilog=(
            "Example:\n"
            "  ./slackbackup search messages 'f3pugetsound,f3kirkland' convergence pax\n"
            "  ./slackbackup search messages 'f3*' convergence pax\n"
            "Output: ./search-results.html by default (override with --out)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_messages.add_argument("workspace", help="exact workspace name, glob, or comma-separated list, e.g. f3pugetsound or 'f3*'")
    p_messages.add_argument("query", nargs="+", help="search query words (implicit AND, no OR operator)")
    p_messages.add_argument("--out", default="./search-results.html")
    p_messages.set_defaults(handler=_messages)


def _messages(args: argparse.Namespace) -> int:
    try:
        results, skipped = search_logic.search_messages(
            args.workspace, args.query, slackdump.search_messages, slackdump.select_workspace_or_die,
        )
    except (workspace_logic.WorkspaceError, search_logic.NoWorkspaceMatchError) as exc:
        print(f"search messages: {exc}", file=sys.stderr)
        return 1

    for name in skipped:
        print(
            f"search messages: skipping '{name}' - not registered yet "
            f"(run: workspace register {name} <cookie>)",
            file=sys.stderr,
        )

    query_label = " ".join(args.query)
    Path(args.out).write_text(search_logic.render_messages_html(results, query_label))
    print(f"search messages: wrote {len(results)} result(s) to {args.out}")
    return 0
