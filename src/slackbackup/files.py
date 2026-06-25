#!/usr/bin/env python3
"""`slackbackup files ...` - file/canvas harvesting and indexing."""
import argparse
from pathlib import Path

from . import files_logic


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("files", help="harvest and index non-image files/canvases")
    sub = group.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser(
        "fetch",
        help="best-effort search-files harvesting across registered f3* workspaces",
        epilog=(
            "Not yet ported - see scripts/fetch-files.sh, still the live implementation.\n"
            "Example:\n  scripts/fetch-files.sh ~/slack-file-search\n"
            "Output: <out_archive_root>/<workspace>/<term>/slackdump.sqlite, one per search term."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_fetch.add_argument("out_archive_root")
    p_fetch.add_argument("--terms-file", default=None)
    p_fetch.set_defaults(handler=_not_implemented)

    p_index = sub.add_parser(
        "index",
        help="unify tracked-archive + search-result files into one index.json",
        epilog=(
            "Not yet ported - see scripts/build-file-index.sh, still the live implementation.\n"
            "Example:\n"
            "  scripts/build-file-index.sh ~/slack-files index.json \\\n"
            "      --archive-root ~/slack-backups --search-root ~/slack-file-search\n"
            "Output: <out_files_dir>/<workspace>/<channel>/<filename>__<file-id>.<ext>\n"
            "        plus <index_json> (one array, one entry per unique file id)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_index.add_argument("out_files_dir")
    p_index.add_argument("index_json")
    p_index.add_argument("--archive-root", required=True)
    p_index.add_argument("--search-root", required=True)
    p_index.set_defaults(handler=_not_implemented)

    p_list = sub.add_parser(
        "list",
        help="summarize an index.json (counts by workspace/mimetype/context type)",
        epilog=(
            "Example:\n  ./slackbackup files list index.json\n"
            "Output: printed to stdout only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_list.add_argument("index_json")
    p_list.set_defaults(handler=_list)


def _not_implemented(args: argparse.Namespace) -> int:
    raise NotImplementedError("files commands not yet ported from fetch-files.sh / build-file-index.sh")


def _list(args: argparse.Namespace) -> int:
    summary = files_logic.summarize(Path(args.index_json))
    print(f"total: {summary['total']}")
    print("by workspace:")
    for ws, count in sorted(summary["by_workspace"].items()):
        print(f"  {ws}: {count}")
    print("by mimetype:")
    for mimetype, count in sorted(summary["by_mimetype"].items()):
        print(f"  {mimetype}: {count}")
    print("by context type:")
    for context_type, count in sorted(summary["by_context_type"].items()):
        print(f"  {context_type}: {count}")
    return 0
