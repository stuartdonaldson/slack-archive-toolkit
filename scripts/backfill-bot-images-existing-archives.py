#!/usr/bin/env python3
"""One-time backfill (SlackBackup sat-lqp): run bot_images_logic.backfill_channel
across every already-archived channel in every workspace, to catch up
historical F3 Nation bot backblast/preblast images (Block Kit image blocks -
see bot_images_logic.py) before the automatic per-backup step (backup_logic,
sat-i2j) starts covering it going forward. Supersedes the earlier
scripts/backfill-bot-image-blocks.py one-off (sat-lul/sat-q9s), which only
took a single archive dir at a time - this wraps the same logic over every
channel in channels.json.

Usage:
    scripts/backfill-bot-images-existing-archives.py [--channels-file channels.json]
        [--archive-root ~/slack-backups] [--only workspace/channel[,workspace/channel...]]

--only restricts the run to an explicit list of "workspace/channel" pairs
(exact match, comma-separated).

Idempotent: safe to re-run - already-downloaded images are skipped, not
re-fetched (see bot_images_logic.backfill_channel).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from slackbackup import bot_images_logic, channel_lock, channel_logic, selector_logic  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--channels-file", type=Path, default=REPO_ROOT / "channels.json")
    parser.add_argument("--archive-root", type=Path, default=Path.home() / "slack-backups")
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

    total_downloaded = total_skipped_auth = total_skipped_gone = total_failed = 0
    channels_touched = 0

    for entry in sorted(entries, key=lambda e: (e["workspace"], e["name"])):
        channel_dir = args.archive_root / entry["workspace"] / entry["name"]
        label = f"{entry['workspace']}/{entry['name']}"

        # sat-7k9: shares the same per-channel lock as backup/dedupe/export -
        # a channel already being touched by a concurrent backup run must
        # not also get a bot-image backfill racing on the same directory.
        try:
            with channel_lock.channel_lock(channel_dir):
                stats = bot_images_logic.backfill_channel(
                    channel_dir, log=lambda msg, label=label: print(f"{label}: {msg}")
                )
        except channel_lock.ChannelLockedError as exc:
            print(f"{label}: skipping - {exc}", file=sys.stderr)
            continue
        if stats.found == 0:
            continue

        channels_touched += 1
        total_downloaded += stats.downloaded
        total_skipped_auth += stats.skipped_auth
        total_skipped_gone += stats.skipped_gone
        total_failed += stats.failed
        print(
            f"{label}: found={stats.found} downloaded={stats.downloaded} "
            f"skipped_existing={stats.skipped_existing} skipped_auth={stats.skipped_auth} "
            f"skipped_gone={stats.skipped_gone} failed={stats.failed}"
        )

    print(
        f"\ndone: {channels_touched} channel(s) with bot images, {total_downloaded} image(s) "
        f"downloaded total, {total_skipped_auth} skipped (needs auth), "
        f"{total_skipped_gone} confirmed gone (404, won't retry), {total_failed} failure(s)"
    )
    return 1 if total_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
