#!/usr/bin/env python3
"""Ad-hoc report: region (workspace), channel, message count, days since the
last message, days since the channel was created, topic, and description -
read straight from each channel's archived slackdump.sqlite.

Usage:
    scripts/channel-message-summary.py [--channels-file channels.json]
        [--archive-root ~/slack-backups] [--out /tmp/slack-backup-recent.csv]

Reads the message high-water mark the same way backup_logic._max_message_ts
does (MAX(ts) from MESSAGE), so "days since last message" reflects what's
actually archived, not channels.json's registration metadata. Creation date,
topic, and description all come from the CHANNEL table's own Slack-API JSON
payload ("created", "topic.value", "purpose.value" - Slack's API calls the
description field "purpose"), captured whenever the channel was first
archived.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from slackbackup import channel_logic  # noqa: E402


def _max_ts_and_count(db_path: Path) -> tuple[int | None, float | None]:
    """(message count, MAX(ts) as float epoch) for a channel archive, or
    (None, None) if the archive is missing/empty/unreadable.

    Counts DISTINCT ts, not COUNT(*): slackdump resume is run without
    -dedupe (backup_logic.py: "-dedupe deliberately never passed: confirmed
    to delete thread-root rows ... Accept duplicate rows across resume
    cycles"), so MESSAGE accumulates a duplicate row per message per resume
    cycle it was re-fetched in - a channel resumed nightly for weeks can
    have single-digit true message counts but 100+ raw rows. Each message's
    ts is stable across resumes (it's Slack's own message identity), so
    COUNT(DISTINCT ts) recovers the true count - confirmed to match the
    digest's own top-level+threaded total for a spot-checked channel
    (f3kirkland/ask-arches: 178 raw rows, 20 distinct ts)."""
    if not db_path.exists():
        return None, None
    try:
        conn = sqlite3.connect(db_path)
        try:
            count_row = conn.execute("SELECT COUNT(DISTINCT ts) FROM MESSAGE").fetchone()
            max_row = conn.execute("SELECT MAX(ts) FROM MESSAGE").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None, None
    count = count_row[0] if count_row else None
    last_ts = float(max_row[0]) if max_row and max_row[0] else None
    return count, last_ts


def _channel_meta(db_path: Path) -> dict:
    """Creation time, topic, and description (Slack calls it "purpose") from
    the CHANNEL row's own Slack-API JSON payload. Missing/unreadable archive
    yields all-empty values rather than raising, same as the message-side
    helpers - a channel not yet backed up should still get a report row."""
    empty = {"created_ts": None, "topic": "", "description": ""}
    if not db_path.exists():
        return empty
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT DATA FROM CHANNEL LIMIT 1").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return empty
    if not row or not row[0]:
        return empty
    try:
        data = json.loads(row[0])
    except (ValueError, TypeError):
        return empty
    created = data.get("created")
    return {
        "created_ts": float(created) if created else None,
        "topic": (data.get("topic") or {}).get("value") or "",
        "description": (data.get("purpose") or {}).get("value") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels-file", type=Path, default=REPO_ROOT / "channels.json")
    parser.add_argument("--archive-root", type=Path, default=Path.home() / "slack-backups")
    parser.add_argument("--out", type=Path, default=Path("/tmp/slack-backup-recent.csv"))
    args = parser.parse_args()

    entries = channel_logic.validate(args.channels_file)
    now = datetime.now(timezone.utc)

    rows = []
    for entry in sorted(entries, key=lambda e: (e["workspace"], e["name"])):
        workspace = entry["workspace"]
        name = entry["name"]
        db_path = args.archive_root / workspace / name / "slackdump.sqlite"
        count, last_ts = _max_ts_and_count(db_path)
        meta = _channel_meta(db_path)
        created_ts = meta["created_ts"]

        if last_ts is not None:
            last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
            days_since = (now - last_dt).days
            last_message_str = last_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            days_since = ""
            last_message_str = ""

        if created_ts is not None:
            created_dt = datetime.fromtimestamp(created_ts, tz=timezone.utc)
            days_since_created = (now - created_dt).days
        else:
            days_since_created = ""

        rows.append(
            {
                "region": workspace,
                "channel": name,
                "num_messages": count if count is not None else 0,
                "last_message": last_message_str,
                "days_since_last_message": days_since,
                "days_since_created": days_since_created,
                "topic": meta["topic"],
                "description": meta["description"],
            }
        )

    with args.out.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "region",
                "channel",
                "num_messages",
                "last_message",
                "days_since_last_message",
                "days_since_created",
                "topic",
                "description",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
