#!/usr/bin/env python3
"""Per-channel archive/resume and multi-channel runs. Ported from
backup.sh + run-backups.sh.
"""
from __future__ import annotations

import hashlib
import heapq
import shutil
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from . import catalog_logic, channel_logic, slackdump


# Tiered backup cadence (SlackBackup-2ut). MODIFIABLE — the whole point is
# this is easy to tune. Each row is (min_age_weeks, cadence_days); the oldest
# (last) row whose min_age_weeks <= the channel's last-activity age wins.
# Rows must stay ordered youngest -> oldest (ascending min_age_weeks) and the
# first must be (0, ...) so every channel matches at least one row.
# Channels with no recorded last activity (empty / never posted) use the LAST
# (oldest) row's cadence. Max cadence sits far inside Slack's ~90-day retention,
# so backing off can never lose messages - only delay detection by a few days.
BACKUP_CADENCE_TIERS = [
    (0, 1),    # < 8 wk  -> every night
    (8, 2),    # 8-12 wk -> every other day
    (12, 10),  # > 12 wk -> every 10 days
]


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str, file=None) -> None:
    # flush=True: stdout is fully block-buffered (not line-buffered) once
    # redirected to a file/pipe rather than a tty - without this, a log
    # tailed via `tail -f` during a long-running backup looks stale for
    # minutes at a time, only catching up when the buffer fills or the
    # process exits.
    print(f"{_ts()} {msg}", file=file, flush=True)


def _cadence_days_for_age(age_weeks: float | None) -> int:
    """How many days apart this channel should be checked, given its
    last-activity age in weeks. `None` (empty / never posted) -> the oldest
    tier's cadence. See BACKUP_CADENCE_TIERS."""
    if age_weeks is None:
        return BACKUP_CADENCE_TIERS[-1][1]
    for min_age_weeks, cadence_days in reversed(BACKUP_CADENCE_TIERS):
        if age_weeks >= min_age_weeks:
            return cadence_days
    return BACKUP_CADENCE_TIERS[0][1]  # unreachable while first row is (0, ...)


def _parse_date(value: str | None) -> date | None:
    """Date portion of an ISO8601 catalog timestamp ('2026-06-20T00:00:00Z' or
    a bare '2026-06-20'), or None if absent/blank. Week granularity is all the
    cadence math needs, so the time-of-day and 'Z' suffix are ignored."""
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _stagger_due(channel_id: str, cadence_days: int, epoch_day: int) -> bool:
    """Deterministic phase so a tier's members spread evenly across their
    interval instead of all firing on the same night: due iff
    hash(channel_id) mod cadence_days == epoch_day mod cadence_days. Uses a
    stable hash (not Python's salted hash()) so a channel's due-night is the
    same across processes and runs."""
    if cadence_days <= 1:
        return True
    phase = int(hashlib.sha1(channel_id.encode()).hexdigest(), 16) % cadence_days
    return epoch_day % cadence_days == phase


def should_check_tonight(entry: dict, record: dict | None, today: date) -> bool:
    """Pure cadence filter: should this channel be backed up on `today`?
    Answerable entirely from the catalog record (last_posted drives the tier;
    last_checked the backstop) - the channel's sqlite is never opened on a
    skip. Active channels (youngest tier, 1-day cadence) are always due.
    Dormant/empty channels are due on their staggered night, and unconditionally
    due if last_checked has aged past their cadence (downtime backstop) or was
    never recorded - so a skip can never push a channel past Slack's retention
    window."""
    record = record or {}
    last_posted = _parse_date(record.get("last_posted"))
    age_weeks = None if last_posted is None else (today - last_posted).days / 7.0
    cadence_days = _cadence_days_for_age(age_weeks)

    last_checked = _parse_date(record.get("last_checked"))
    if last_checked is None or (today - last_checked).days >= cadence_days:
        return True
    return _stagger_due(entry["id"], cadence_days, today.toordinal())


def channel_dir(archive_root: Path, workspace: str, channel_slug: str) -> Path:
    # Keyed by <workspace>/<slug>, not slug alone - two different channels
    # in different workspaces sharing a slug must not collide into one
    # archive.
    return archive_root / workspace / channel_slug


def _max_message_ts(db_path: Path) -> str | None:
    """Real last-post time (ISO8601 UTC) from this archive's own message
    data, or None if there's no data to read (0 messages, or a malformed/
    placeholder file) - the caller falls back to registered_at instead of
    writing a bogus value in that case."""
    if not db_path.exists():
        # sqlite3.connect() would silently create an empty file here -
        # never do that as a side effect of just reading.
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT MAX(ts) FROM MESSAGE").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    return datetime.fromtimestamp(float(row[0]), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_last_backup(target_dir: Path) -> None:
    """Record the last successful backup of `target_dir` as a git-durable UTC
    stamp in `<target_dir>/.last_backup` (file content, not mtime - mtime does
    not survive a clone/checkout). The monthly exporter reads this to seal
    quiet/empty recent months as complete instead of falling back to the
    message high-water mark, which otherwise rewrites a quiet channel's last
    active month on every run (SlackBackup-026)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / ".last_backup").write_text(_ts() + "\n")


def backup_channel(
    channel_id: str,
    channel_slug: str,
    workspace: str,
    archive_root: Path,
    full: bool = False,
    cache_dir: Path = catalog_logic.DEFAULT_CACHE_DIR,
) -> str:
    """Returns "archive" or "resume" - which path was taken, for the
    caller's own summary/tally. A full re-sync always counts as "archive"."""
    slackdump.select_workspace_or_die(workspace)
    archive_root.mkdir(parents=True, exist_ok=True)

    if full:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        full_dir = archive_root / workspace / f"{channel_slug}-full-{stamp}"
        _log(
            f"backup: full re-sync requested — archiving into fresh dir {full_dir} "
            "(incremental archive untouched)"
        )
        slackdump.archive(channel_id, full_dir)
        _write_last_backup(full_dir)
        return "archive"

    channel_directory = channel_dir(archive_root, workspace, channel_slug)
    db_path = channel_directory / "slackdump.sqlite"

    if not db_path.exists():
        _log(f"backup: no existing archive — running full archive into {channel_directory}")
        slackdump.archive(channel_id, channel_directory)
        catalog_logic.update_last_posted(cache_dir, workspace, channel_id, _max_message_ts(db_path))
        _write_last_backup(channel_directory)
        return "archive"

    try:
        count = _message_count(db_path)
    except sqlite3.Error:
        # Malformed/unreadable local file - treat the same as "empty",
        # since there's no usable checkpoint for resume either way.
        count = 0

    if count == 0:
        # resume reads its continuation point from this file's own session/
        # chunk bookkeeping; a 0-message archive has none, so resume always
        # errors before even calling the API (see SlackBackup-8ew) - it can
        # never self-heal even after the channel gets real posts. archive
        # is only safe against an empty/new directory (re-running it over an
        # existing one duplicates data - slackdump-cli-notes.md), so wipe
        # the stale empty dir first rather than archiving on top of it.
        _log(
            f"backup: existing archive at {db_path} has 0 messages — resume cannot "
            "continue from an empty checkpoint; wiping and re-archiving fresh"
        )
        shutil.rmtree(channel_directory)
        slackdump.archive(channel_id, channel_directory)
        catalog_logic.update_last_posted(cache_dir, workspace, channel_id, _max_message_ts(db_path))
        _write_last_backup(channel_directory)
        return "archive"

    _log(f"backup: existing archive found at {db_path} — resuming")
    # -dedupe deliberately never passed: confirmed to delete thread-root
    # rows (SlackBackup-d3r). Accept duplicate rows across resume cycles.
    slackdump.resume(channel_directory)
    catalog_logic.update_last_posted(cache_dir, workspace, channel_id, _max_message_ts(db_path))
    _write_last_backup(channel_directory)
    return "resume"


def _interleave_by_workspace(entries: list[dict]) -> list[dict]:
    """Reorders entries (each already sorted most-recent-first *within* its
    own workspace by the caller) so consecutive channels alternate across
    workspaces as much as possible, minimizing back-to-back calls against
    the same workspace's Slack rate-limit bucket - confirmed per-workspace,
    not global, so spreading calls across workspaces lets one workspace's
    bucket refill while we work another. Greedy: always take next from
    whichever workspace currently has the most entries left (classic
    "task scheduler" / "reorganize string" approach - optimal spacing for
    uneven group sizes), only repeating the immediately preceding workspace
    when no other workspace has anything left."""
    queues: dict[str, list[dict]] = {}
    for entry in entries:
        queues.setdefault(entry["workspace"], []).append(entry)

    heap = [(-len(items), ws) for ws, items in queues.items()]
    heapq.heapify(heap)

    result: list[dict] = []
    last_ws: str | None = None
    while heap:
        neg_count, ws = heapq.heappop(heap)
        if ws == last_ws and heap:
            neg_count2, ws2 = heapq.heappop(heap)
            heapq.heappush(heap, (neg_count, ws))
            neg_count, ws = neg_count2, ws2

        result.append(queues[ws].pop(0))
        last_ws = ws
        if queues[ws]:
            heapq.heappush(heap, (-len(queues[ws]), ws))

    return result


def run(
    channels_file: Path,
    archive_root: Path,
    full: bool = False,
    cache_dir: Path = catalog_logic.DEFAULT_CACHE_DIR,
    today: date | None = None,
) -> bool:
    """Returns True if every channel backed up successfully. Within each
    workspace, channels are ordered most-recently-active first (real
    last_posted if a backup has ever found message data, else the
    registered_at fallback - see catalog_logic.effective_recency) - so if
    the run is interrupted, the channels we have the most reason to care
    about have already been covered. Across workspaces, channels are then
    interleaved (see _interleave_by_workspace) rather than processed one
    workspace at a time, since Slack's rate limit is per-workspace - this
    spreads calls out so one workspace's bucket has time to refill while
    others are being worked, instead of exhausting one bucket completely
    before moving to the next."""
    entries = channel_logic.validate(channels_file)

    # Warm each workspace's fast-tier catalog, but don't let one workspace with
    # an expired session abort the whole multi-workspace run - skip it and carry
    # on with the rest (its channels would only fail downstream anyway).
    skipped_workspaces: dict[str, str] = {}
    for workspace in sorted({entry["workspace"] for entry in entries}):
        try:
            catalog_logic.refresh_fast(workspace, cache_dir=cache_dir)
        except slackdump.SlackdumpError as exc:
            _log(
                f"backup run: skipping workspace '{workspace}' - catalog refresh failed "
                f"(session likely expired; re-register it): {exc}",
                file=sys.stderr,
            )
            skipped_workspaces[workspace] = str(exc)

    if skipped_workspaces:
        entries = [e for e in entries if e["workspace"] not in skipped_workspaces]

    catalog_cache: dict[str, dict] = {}
    for entry in entries:
        workspace = entry["workspace"]
        if workspace not in catalog_cache:
            catalog_cache[workspace] = catalog_logic.load(cache_dir, workspace)
    entries = sorted(
        entries,
        key=lambda e: catalog_logic.effective_recency(catalog_cache[e["workspace"]], e["id"]),
        reverse=True,
    )
    entries = _interleave_by_workspace(entries)

    all_ok = not skipped_workspaces
    counts = {"archive": 0, "resume": 0, "failed": 0, "skipped": 0}
    run_start = time.monotonic()
    today = datetime.now(timezone.utc).date() if today is None else today
    today_iso = today.isoformat()

    # Per-workspace progress: X/Y where Y is how many channels this run handles
    # for the workspace and X the running position within it. Entries interleave
    # across workspaces (see _interleave_by_workspace), so a workspace's X values
    # are not consecutive in the log - the counter is what makes progress through
    # each workspace legible.
    ws_totals: dict[str, int] = {}
    for entry in entries:
        ws_totals[entry["workspace"]] = ws_totals.get(entry["workspace"], 0) + 1
    ws_seen: dict[str, int] = {ws: 0 for ws in ws_totals}

    for entry in entries:
        workspace = entry["workspace"]
        ws_seen[workspace] += 1
        progress = f"[{ws_seen[workspace]}/{ws_totals[workspace]} in {workspace}]"
        record = catalog_cache[workspace].get("channels", {}).get(entry["id"], {})
        # -full always re-syncs; the cadence filter only governs incremental runs.
        if not full and not should_check_tonight(entry, record, today):
            _log(
                f"backup run: skipping {entry['name']} ({entry['id']}) in {workspace} "
                f"{progress} - not due tonight (cadence)"
            )
            catalog_logic.record_check(cache_dir, workspace, entry["id"], today_iso, "skip")
            counts["skipped"] += 1
            continue

        _log(f"backup run: backing up {entry['name']} ({entry['id']}) in {workspace} {progress}")
        channel_start = time.monotonic()
        try:
            kind = backup_channel(
                entry["id"], entry["name"], workspace, archive_root, full, cache_dir=cache_dir
            )
            elapsed = time.monotonic() - channel_start
            _log(f"backup run: finished {entry['name']} in {workspace} ({kind}, {elapsed:.1f}s)")
            counts[kind] += 1
            catalog_logic.record_check(cache_dir, workspace, entry["id"], today_iso, kind)
        except slackdump.SlackdumpError as exc:
            elapsed = time.monotonic() - channel_start
            _log(
                f"backup run: backup failed for {entry['name']} ({entry['id']}) after {elapsed:.1f}s: {exc}",
                file=sys.stderr,
            )
            all_ok = False
            counts["failed"] += 1
            catalog_logic.record_check(cache_dir, workspace, entry["id"], today_iso, "failed")

    total_elapsed = time.monotonic() - run_start
    skipped_note = (
        f", {len(skipped_workspaces)} workspace(s) skipped" if skipped_workspaces else ""
    )
    _log(
        f"backup run: done - {len(entries)} channel(s), {counts['archive']} archive(s), "
        f"{counts['resume']} resume(s), {counts['skipped']} not-due skip(s), "
        f"{counts['failed']} failure(s){skipped_note}, {total_elapsed / 60:.1f} min total"
    )
    return all_ok


def _message_count(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM MESSAGE").fetchone()[0]
    finally:
        conn.close()


def _local_status(db_path: Path) -> dict:
    """Read-only, local-only (no API call): message count and last-modified
    time of a channel's archive, if it exists."""
    if not db_path.exists():
        return {"archived": False, "message_count": None, "last_modified": None}

    count = _message_count(db_path)
    mtime = datetime.fromtimestamp(db_path.stat().st_mtime, tz=timezone.utc)
    return {
        "archived": True,
        "message_count": count,
        "last_modified": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def list_status(channels_file: Path, archive_root: Path) -> list[dict]:
    """One row per tracked channel: {id, name, workspace, archived,
    message_count, last_modified}. Entirely local - no API calls."""
    entries = channel_logic.validate(channels_file)
    rows = []
    for entry in entries:
        db_path = channel_dir(archive_root, entry["workspace"], entry["name"]) / "slackdump.sqlite"
        status = _local_status(db_path)
        rows.append({**entry, **status})
    return rows


def sync_catalog_from_local(
    channels_file: Path,
    archive_root: Path,
    cache_dir: Path = catalog_logic.DEFAULT_CACHE_DIR,
) -> dict:
    """Backfills the catalog's last_posted/registered_at purely from local
    archives already on disk - no API calls, safe to run any time (e.g.
    after interrupting a `backup run` mid-flight, when many channels were
    actually backed up by the now-dead process before it had this
    bookkeeping wired in). For each tracked channel: if its local archive
    has real message data, stamp last_posted from MAX(ts); otherwise stamp
    registered_at with now (set_registered_at is idempotent - a no-op if
    a real registered_at is already on record, so this never clobbers a
    true earlier value, it just ensures every channel has *some* recency
    signal). Returns {"last_posted": n, "registered_at": m, "total": t}."""
    entries = channel_logic.validate(channels_file)
    counts = {"last_posted": 0, "registered_at": 0, "total": len(entries)}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for entry in entries:
        db_path = channel_dir(archive_root, entry["workspace"], entry["name"]) / "slackdump.sqlite"
        last_posted = _max_message_ts(db_path)
        if last_posted:
            catalog_logic.update_last_posted(cache_dir, entry["workspace"], entry["id"], last_posted)
            counts["last_posted"] += 1
        else:
            catalog_logic.set_registered_at(cache_dir, entry["workspace"], entry["id"], now)
            counts["registered_at"] += 1

    return counts
