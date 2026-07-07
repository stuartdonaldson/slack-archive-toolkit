#!/usr/bin/env python3
"""`slackbackup channel-digest ...` - on-demand extraction of any channel-
name glob pattern in a workspace into a single JSON digest of surviving
messages/files/canvases. Deliberately not wired into backup_logic.run()'s
nightly cadence - this is a manual, occasional tool (e.g. for shuttered-*
channels left behind by a Slack workspace migration). See
channel_digest_logic.py and SlackBackup-ie2 for background."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import catalog_logic, channel_digest_logic, slackdump


def register(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser(
        "channel-digest", help="extract channels matching a name pattern into one digest"
    )
    sub = group.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser(
        "run",
        help="archive every channel matching a glob pattern and write a JSON digest",
        epilog=(
            "Example:\n"
            "  ./slackbackup channel-digest run f3pugetsound 'shuttered-*' "
            "~/slack-backups/f3pugetsound-shuttered-digest\n"
            "Slow: one `slackdump archive` + `convert -f export` per matching channel (~15-25s each).\n"
            "Safe to re-run - each channel's raw archive is re-created fresh under <out_dir>/raw/.\n"
            "If <out_dir>'s digest JSON already exists, this run's results are merged into it "
            "(first_seen_at/last_seen_at/content_last_changed_at track what's new vs. unchanged)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_run.add_argument("workspace")
    p_run.add_argument("pattern", help="fnmatch glob against channel name, e.g. 'shuttered-*'")
    p_run.add_argument("out_dir")
    p_run.add_argument("--cache-dir", default=str(catalog_logic.DEFAULT_CACHE_DIR))
    p_run.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    out_root = Path(args.out_dir)
    raw_root = out_root / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    slackdump.select_workspace_or_die(args.workspace)
    catalog = catalog_logic.load(Path(args.cache_dir), args.workspace)
    channels = channel_digest_logic.filter_channels(catalog, args.pattern)
    if not channels:
        print(f"no channels matching '{args.pattern}' found in {args.workspace} catalog cache", file=sys.stderr)
        return 1

    print(f"found {len(channels)} channels matching '{args.pattern}' - archiving each (this will take a while)")
    results = []
    for i, channel in enumerate(channels, 1):
        channel_dir = raw_root / channel["name"]
        print(f"[{i}/{len(channels)}] {channel['name']} ({channel['id']})...", end=" ", flush=True)
        try:
            if channel_dir.exists():
                shutil.rmtree(channel_dir)
            slackdump.archive(channel["id"], channel_dir)
            with tempfile.TemporaryDirectory() as export_dir:
                export_dir_path = Path(export_dir)
                slackdump.convert_export(channel_dir, export_dir_path)
                extracted = channel_digest_logic.extract_channel(channel_dir, export_dir_path)
            results.append({"channel": channel, **extracted})
            print(f"{len(extracted['messages'])} messages, {len(extracted['files'])} files")
        except slackdump.SlackdumpError as exc:
            results.append({"channel": channel, "messages": [], "files": [], "error": str(exc)})
            print(f"ERROR: {exc}")

    digest = channel_digest_logic.build_digest(args.workspace, args.pattern, results)
    safe_pattern = args.pattern.replace("*", "").replace("?", "").strip("-_") or "channels"
    digest_path = out_root / f"{args.workspace}-{safe_pattern}-digest.json"
    if digest_path.exists():
        existing = json.loads(digest_path.read_text())
        digest = channel_digest_logic.merge_digests(existing, digest)
        print(f"merged into existing digest ({digest['manifest']['channels_total']} channels total)")
    digest_path.write_text(json.dumps(digest, indent=2))
    print(f"\nwrote {digest_path}")
    return 0
