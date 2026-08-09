#!/usr/bin/env python3
"""Downloads images that F3 Nation's backblast/preblast bot ("Crazy Ivan")
embeds as Block Kit `image` blocks (blocks[].image_url) rather than native
Slack file uploads. archive/resume (slackdump.py) only downloads real Slack
file attachments (the files[] array -> FILE table -> __uploads/), so these
bot-embedded images never land locally through the normal backup path even
for a fully tracked, resumed channel - see docs/references/slackdump-cli-
notes.md and SlackBackup sat-lul/sat-q9s/sat-i2j.

Two URL flavors observed in practice:
- storage.googleapis.com/f3-public-images/... - F3 Nation's own public
  bucket, no auth needed, downloaded directly.
- files.slack.com/files-pri/... - Slack's private CDN. This project never
  persists the raw session cookie (by design - see slackdump-cli-notes.md),
  so this module has no auth to fetch these; they're reported and skipped
  rather than silently dropped.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_OUT_SUBDIR = "__bot-images"
AUTH_REQUIRED_HOST = "files.slack.com"
# Marker suffix for a URL confirmed permanently gone (HTTP 404) - written
# instead of retrying it every night forever. Observed in practice on F3
# Nation's ephemeral per-render calendar-preview thumbnails
# (f3nation-calendar-images bucket, workspace-wide "all-f3-*" announcement
# channels), which the bot's own service already garbage-collects - distinct
# from the stable f3-public-images bucket real backblast/preblast photos
# use, which hasn't been observed to 404 (SlackBackup sat-lqp backfill run).
GONE_MARKER_SUFFIX = ".gone"


@dataclass
class BackfillStats:
    found: int = 0
    downloaded: int = 0
    skipped_existing: int = 0
    skipped_auth: int = 0
    skipped_gone: int = 0
    failed: int = 0

    @property
    def total_skipped_auth(self) -> int:
        return self.skipped_auth


def iter_image_blocks(db_path: Path):
    """Yields (ts, image_url) for each distinct message with a Block Kit
    image block. Messages appear multiple times across chunks (resume
    re-fetches its lookback window each cycle); DISTINCT TS collapses that
    before parsing, not after, since parsing JSON per duplicate row is
    wasted work at this row count but not free at scale."""
    con = sqlite3.connect(str(db_path))
    try:
        seen_ts = set()
        for ts, data in con.execute("SELECT DISTINCT TS, DATA FROM MESSAGE"):
            if ts in seen_ts:
                continue
            seen_ts.add(ts)
            try:
                msg = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue
            for block in msg.get("blocks") or []:
                if block.get("type") == "image" and block.get("image_url"):
                    yield ts, block["image_url"]
    finally:
        con.close()


def date_prefix(ts: str) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def target_filename(ts: str, url: str) -> str:
    basename = Path(urlparse(url).path).name or "image"
    return f"{date_prefix(ts)}_{basename}"


def backfill_channel(
    archive_dir: Path, out_subdir: str = DEFAULT_OUT_SUBDIR, log=lambda msg: None
) -> BackfillStats:
    """Downloads every not-yet-present bot-embedded image for one channel
    archive into <archive_dir>/<out_subdir>/. Idempotent (a URL whose
    target filename already exists is skipped, not re-downloaded).
    Returns per-run counts; never raises for a missing db or a per-file
    download failure - callers decide whether/how to surface those (see
    backup_logic._backfill_bot_images_quietly for the non-fatal nightly
    caller)."""
    stats = BackfillStats()
    db_path = archive_dir / "slackdump.sqlite"
    if not db_path.exists():
        return stats

    out_dir = archive_dir / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    for ts, url in iter_image_blocks(db_path):
        stats.found += 1
        host = urlparse(url).netloc
        fname = target_filename(ts, url)
        dest = out_dir / fname
        gone_marker = dest.with_name(dest.name + GONE_MARKER_SUFFIX)

        if dest.exists():
            stats.skipped_existing += 1
            continue

        if gone_marker.exists():
            stats.skipped_gone += 1
            continue

        if host == AUTH_REQUIRED_HOST:
            stats.skipped_auth += 1
            log(f"bot-images: skipped (needs auth, not downloaded): {fname} <- {url}")
            continue

        try:
            urllib.request.urlretrieve(url, dest)
            stats.downloaded += 1
            log(f"bot-images: wrote {fname}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                gone_marker.touch()
                stats.skipped_gone += 1
                log(f"bot-images: gone (404, won't retry) {fname} <- {url}")
            else:
                stats.failed += 1
                log(f"bot-images: failed {fname} <- {url} ({exc})")
        except (urllib.error.URLError, OSError) as exc:
            stats.failed += 1
            log(f"bot-images: failed {fname} <- {url} ({exc})")

    return stats
