#!/usr/bin/env python3
"""One-time backfill (SlackBackup-9hq): run `slackdump tools dedupe` across
every already-archived channel to clean up duplicate MESSAGE/CHANNEL/
CHANNEL_USER/FILE rows accumulated by weeks/months of `resume` cycles before
the dedupe step was wired into backup_channel() (see backup_logic.py). Going
forward, backup_channel() runs this automatically after every resume, so
this script only needs to run once to clear the existing backlog - safe to
re-run afterward too (a no-op on an already-deduped archive).

Usage:
    scripts/dedupe-existing-archives.py [--channels-file channels.json]
        [--archive-root ~/slack-backups] [--dry-run]
        [--only workspace/channel[,workspace/channel...]]

--dry-run reports what would be removed (via `tools dedupe` without
-execute) without changing anything.

--only restricts the run to an explicit list of "workspace/channel" pairs
(exact match, comma-separated) - e.g. for clearing just the worst-offender
channels immediately rather than waiting on backup_channel()'s per-resume
dedupe to reach every channel over its normal cadence.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from slackbackup import channel_lock, channel_logic, selector_logic, slackdump  # noqa: E402


def _dry_run_report(channel_dir: Path) -> str | None:
    """Runs `tools dedupe` without -execute (report-only) and returns its
    "Duplicate messages: N" line, or None if the archive is missing/empty."""
    if not (channel_dir / "slackdump.sqlite").exists():
        return None
    result = slackdump._run(["tools", "dedupe", "-mode", "message-key", str(channel_dir)])
    if result.returncode != 0:
        return f"error: {result.stderr.strip()}"
    for line in result.stdout.splitlines():
        if line.startswith("Duplicate messages:"):
            return line
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels-file", type=Path, default=REPO_ROOT / "channels.json")
    parser.add_argument("--archive-root", type=Path, default=Path.home() / "slack-backups")
    parser.add_argument("--dry-run", action="store_true", help="report only, no changes")
    parser.add_argument(
        "--only", type=str, default=None,
        help="comma-separated workspace/channel pairs (exact match) to restrict the run to",
    )
    args = parser.parse_args()

    entries = channel_logic.validate(args.channels_file)

    if args.only is not None:
        wanted = set(selector_logic.split_selector_list(args.only))
        entries = [e for e in entries if f"{e['workspace']}/{e['name']}" in wanted]
        found = {f"{e['workspace']}/{e['name']}" for e in entries}
        missing = wanted - found
        if missing:
            print(f"warning: --only pair(s) not found in {args.channels_file}: {', '.join(sorted(missing))}", file=sys.stderr)

    total_removed = 0
    channels_touched = 0
    channels_failed = 0

    for entry in sorted(entries, key=lambda e: (e["workspace"], e["name"])):
        channel_dir = args.archive_root / entry["workspace"] / entry["name"]
        db_path = channel_dir / "slackdump.sqlite"
        if not db_path.exists():
            continue  # never archived - nothing to dedupe

        label = f"{entry['workspace']}/{entry['name']}"
        if args.dry_run:
            report = _dry_run_report(channel_dir)
            if report:
                print(f"{label}: {report}")
            continue

        try:
            with channel_lock.channel_lock(channel_dir):
                removed = slackdump.dedupe(channel_dir)
        except channel_lock.ChannelLockedError as exc:
            print(f"{label}: skipping - {exc}", file=sys.stderr)
            continue
        except slackdump.SlackdumpError as exc:
            print(f"{label}: FAILED - {exc}", file=sys.stderr)
            channels_failed += 1
            continue

        if removed:
            print(f"{label}: removed {removed} duplicate message row(s)")
            total_removed += removed
            channels_touched += 1

    if not args.dry_run:
        print(
            f"\ndone: {channels_touched} channel(s) cleaned, {total_removed} duplicate "
            f"message row(s) removed total, {channels_failed} failure(s)"
        )
    return 1 if channels_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
