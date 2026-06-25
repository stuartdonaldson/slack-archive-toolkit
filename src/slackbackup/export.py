#!/usr/bin/env python3
"""`slackbackup export ...` - monthly JSON export of an archived channel.

Read-only consumer of one channel's slackdump.sqlite archive: renders it
through slackdump's documented `convert -f export` boundary, then runs the
custom transform (range bounding, monthly bucketing, thread nesting, sealed-
month idempotency) in export_logic.py. Never modifies the archive and never
calls the Slack API.
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import export_logic, slackdump


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("export", help="export an archived channel to bounded monthly JSON")
    sub = group.add_subparsers(dest="command", required=True)

    p_monthly = sub.add_parser(
        "monthly",
        help="export months overlapping [--from, --to]",
        epilog=(
            "Example:\n"
            "  ./slackbackup export monthly --from 2026-01-01 --to 2026-06-30 \\\n"
            "      --workspace f3pugetsound --channel helpdesk \\\n"
            "      --archive-root ~/slack-backups --out ~/slack-exports\n"
            "Output: <out>/<workspace>-<channel>-yyyy-mm.json, one file per overlapping month."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_monthly.add_argument("--from", dest="date_from", required=True)
    p_monthly.add_argument("--to", dest="date_to", required=True)
    p_monthly.add_argument("--workspace", required=True)
    p_monthly.add_argument("--channel", required=True)
    p_monthly.add_argument("--archive-root", required=True)
    p_monthly.add_argument("--out", required=True)
    p_monthly.set_defaults(handler=_monthly)

    p_list = sub.add_parser(
        "list",
        help="list which months are already exported in a directory",
        epilog=(
            "Example:\n  ./slackbackup export list ~/slack-exports --workspace f3pugetsound\n"
            "Output: printed to stdout (tab-separated) only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_list.add_argument("out", help="directory previously passed to 'export monthly --out'")
    p_list.add_argument("--workspace", default=None)
    p_list.add_argument("--channel", default=None)
    p_list.set_defaults(handler=_list)

    p_digest = sub.add_parser(
        "digest",
        help="merge the trailing N months across workspaces matching --workspace-glob into one JSON document",
        epilog=(
            "Example:\n  ./slackbackup export digest --archive-root ~/slack-backups\n"
            "Output: --out, defaulting to ~/slack-exports/f3-digest-<as-of>.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_digest.add_argument("--archive-root", required=True)
    p_digest.add_argument("--channels-file", default="./channels.json")
    p_digest.add_argument("--workspace-glob", default="f3*")
    p_digest.add_argument("--months", type=int, default=3)
    p_digest.add_argument("--as-of", default=None, help="defaults to today (UTC)")
    p_digest.add_argument(
        "--out", default=None,
        help="defaults to ~/slack-exports/f3-digest-<as-of>.json",
    )
    p_digest.set_defaults(handler=_digest)

    p_users = sub.add_parser(
        "users",
        help="export every known user profile, grouped per workspace matching --workspace-glob",
        epilog=(
            "Example:\n  ./slackbackup export users --archive-root ~/slack-backups\n"
            "Output: --out, defaulting to ~/slack-exports/f3-user-profiles-<today>.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_users.add_argument("--archive-root", required=True)
    p_users.add_argument("--channels-file", default="./channels.json")
    p_users.add_argument("--workspace-glob", default="f3*")
    p_users.add_argument(
        "--out", default=None,
        help="defaults to ~/slack-exports/f3-user-profiles-<today>.json",
    )
    p_users.set_defaults(handler=_users)


def _monthly(args: argparse.Namespace) -> int:
    channel_dir = Path(args.archive_root) / args.workspace / args.channel
    db_path = channel_dir / "slackdump.sqlite"

    if not db_path.exists():
        print(
            f"export monthly: archive not found for ({args.workspace}, {args.channel}): {db_path}",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as export_dir:
        print(f"export monthly: converting {db_path} -> export day files", file=sys.stderr)
        slackdump.convert_export(channel_dir, Path(export_dir))

        last_backup_file = channel_dir / ".last_backup"
        export_logic.export_transform(
            Path(export_dir), args.workspace, args.channel, args.date_from, args.date_to,
            out_dir, last_backup_file,
        )
    return 0


def _list(args: argparse.Namespace) -> int:
    rows = export_logic.list_exports(Path(args.out), args.workspace, args.channel)
    print("workspace\tchannel\tmonth\tpath")
    for row in rows:
        print(f"{row['workspace']}\t{row['channel']}\t{row['month']}\t{row['path']}")
    return 0


DEFAULT_EXPORTS_DIR = Path.home() / "slack-exports"


def _digest(args: argparse.Namespace) -> int:
    as_of = args.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = Path(args.out) if args.out else DEFAULT_EXPORTS_DIR / f"f3-digest-{as_of}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = export_logic.build_digest(
        Path(args.channels_file), Path(args.archive_root), args.workspace_glob,
        args.months, as_of, slackdump.convert_export,
    )
    out_path.write_text(json.dumps(result, indent=2))

    ok = sum(1 for c in result["channels"] if c["status"] == "ok")
    missing = sum(1 for c in result["channels"] if c["status"] == "missing_archive")
    print(
        f"export digest: {len(result['messages'])} messages from {ok} channels "
        f"({missing} missing archive) -> {out_path}",
        file=sys.stderr,
    )
    return 0


def _users(args: argparse.Namespace) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = Path(args.out) if args.out else DEFAULT_EXPORTS_DIR / f"f3-user-profiles-{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = export_logic.build_user_profiles(
        Path(args.channels_file), Path(args.archive_root), args.workspace_glob, slackdump.convert_export,
    )
    out_path.write_text(json.dumps(result, indent=2))

    for ws in result["workspaces"]:
        print(f"export users: {ws['workspace']}: {ws['status']} ({len(ws['profiles'])} profiles)", file=sys.stderr)
    print(f"export users: -> {out_path}", file=sys.stderr)
    return 0
