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

from . import export_logic, handlers, selector_logic, slackdump


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
        help="merge messages across workspaces matching --workspace into one JSON document",
        epilog=(
            "Example:\n  ./slackbackup export digest --archive-root ~/slack-backups --workspace 'f3*'\n"
            "  ./slackbackup export digest --archive-root ~/slack-backups --workspace 'f3*,dungeons-*'\n"
            "  ./slackbackup export digest --archive-root ~/slack-backups --workspace 'f3*' --days 30\n"
            "  ./slackbackup export digest --jobs 'jobs/*.json'\n"
            "Output: --out, defaulting to ~/slack-exports/f3-digest-<as-of>.json.\n"
            "With --jobs, each matched job's own archive-root/channels-file/workspaces/days/out/\n"
            "leadership-handler/users_out (see jobs/*.json) is used instead, one digest per job -\n"
            "--archive-root/--channels-file/--leadership-handler on the command line become the\n"
            "fallback for jobs that don't set their own."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_digest.add_argument(
        "--archive-root", default=None,
        help="required unless every --job entry defines its own archive_root",
    )
    p_digest.add_argument("--channels-file", default="./channels.json")
    p_digest.add_argument(
        "--workspace", dest="workspace_glob", default=None,
        help="workspace glob or comma-separated selector list; required unless every "
        "--job entry defines its own workspaces",
    )
    p_digest.add_argument(
        "--days", type=int, default=180,
        help="only include the trailing N days ending at --as-of; defaults to 180 days",
    )
    p_digest.add_argument("--as-of", default=None, help="defaults to today (UTC)")
    p_digest.add_argument(
        "--out", default=None,
        help="defaults to ~/slack-exports/f3-digest-<as-of>.json",
    )
    p_digest.add_argument(
        "--jobs", default=None,
        help="comma-separated glob(s) matching jobs/*.json report definitions "
        "(quote to stop the shell from expanding the glob itself), e.g. 'jobs/*.json' "
        "or 'jobs/f3-*.json,jobs/other.json'; one digest per matched job, "
        "overriding --channels-file/--workspace/--days/--out for that job",
    )
    p_digest.add_argument(
        "--leadership-handler", default=None,
        help=f"region-specific leadership/tagging handler ({', '.join(handlers.NAMES)}, or 'none'); "
        "defaults to 'f3' for a plain (non --jobs) run, preserving this project's original "
        "F3-only behavior. With --jobs, this is only the fallback for a job that doesn't set "
        "its own 'leadership_handler' field - the per-job default is 'none', since a job may "
        "target a non-F3 workspace",
    )
    p_digest.set_defaults(handler=_digest)

    p_users = sub.add_parser(
        "users",
        help="export every known user profile, grouped per workspace matching --workspace",
        epilog=(
            "Example:\n  ./slackbackup export users --archive-root ~/slack-backups --workspace 'f3*'\n"
            "  ./slackbackup export users --archive-root ~/slack-backups --workspace 'f3*,dungeons-*'\n"
            "Output: --out, defaulting to ~/slack-exports/f3-user-profiles-<today>.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_users.add_argument("--archive-root", required=True)
    p_users.add_argument("--channels-file", default="./channels.json")
    p_users.add_argument(
        "--workspace", dest="workspace_glob", required=True,
        help="workspace glob or comma-separated selector list",
    )
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


def _resolve_handler(name: str | None):
    if name in (None, "none"):
        return None
    return handlers.get(name)


def _run_digest(channels_file: Path, archive_root: Path, workspace_glob: str, days: int | None,
                 as_of: str, out_path: Path, handler, profiles_doc: dict | None = None) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = export_logic.build_digest(
        channels_file, archive_root, workspace_glob, days, as_of, slackdump.convert_export,
        handler=handler, profiles_doc=profiles_doc,
    )
    out_path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    ok = sum(1 for c in result["channels"] if c["status"] == "ok")
    missing = sum(1 for c in result["channels"] if c["status"] == "missing_archive")
    print(
        f"export digest: {len(result['messages'])} messages from {ok} channels "
        f"({missing} missing archive) -> {out_path}",
        file=sys.stderr,
    )


def _run_job(job_file: str, job: dict, args: argparse.Namespace, as_of: str) -> None:
    archive_root = export_logic.expand_job_path(job["archive_root"])
    channels_file = export_logic.expand_job_path(job.get("channels_file", args.channels_file))
    workspace_glob = ",".join(job["workspaces"])
    handler = _resolve_handler(job.get("leadership_handler", args.leadership_handler))

    profiles_doc = export_logic.build_user_profiles(
        channels_file, archive_root, workspace_glob, slackdump.convert_export, handler=handler,
    )
    if "users_out" in job:
        users_out_path = export_logic.resolve_job_out(job["users_out"], as_of)
        users_out_path.parent.mkdir(parents=True, exist_ok=True)
        users_out_path.write_text(json.dumps(profiles_doc, indent=2))
        print(f"export digest: job {job_file}: user profiles -> {users_out_path}", file=sys.stderr)

    _run_digest(
        channels_file, archive_root, workspace_glob, job.get("days", args.days), as_of,
        export_logic.resolve_job_out(job["out"], as_of), handler, profiles_doc=profiles_doc,
    )


def _digest(args: argparse.Namespace) -> int:
    as_of = args.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if args.jobs:
        exit_code = 0
        for job_file in selector_logic.expand_path_selector(args.jobs):
            try:
                job = export_logic.load_job(Path(job_file))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"export digest: skipping job {job_file}: {exc}", file=sys.stderr)
                exit_code = 1
                continue
            if not job.get("archive_root", args.archive_root):
                print(
                    f"export digest: skipping job {job_file}: no archive_root in job "
                    "and no --archive-root fallback given",
                    file=sys.stderr,
                )
                exit_code = 1
                continue
            job.setdefault("archive_root", args.archive_root)
            try:
                _run_job(job_file, job, args, as_of)
            except Exception as exc:
                print(f"export digest: job {job_file} failed: {exc}", file=sys.stderr)
                exit_code = 1
                continue
        return exit_code

    if not args.archive_root:
        print("export digest: --archive-root is required unless --jobs is given", file=sys.stderr)
        return 2

    if not args.workspace_glob:
        print("export digest: --workspace is required unless --jobs is given", file=sys.stderr)
        return 2

    try:
        handler = _resolve_handler(args.leadership_handler or "f3")
    except ValueError as exc:
        print(f"export digest: {exc}", file=sys.stderr)
        return 2
    out_path = Path(args.out) if args.out else DEFAULT_EXPORTS_DIR / f"f3-digest-{as_of}.json"
    _run_digest(
        Path(args.channels_file), Path(args.archive_root), args.workspace_glob, args.days, as_of, out_path, handler,
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
