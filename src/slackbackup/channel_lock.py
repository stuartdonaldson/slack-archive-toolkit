#!/usr/bin/env python3
"""Exclusive per-channel pidfile lock (SlackBackup sat-7k9).

Why channel granularity: the actual unit of file conflict is one channel's
directory (slackdump.sqlite + __uploads/__bot-images) - it's already the
loop unit in backup_logic.py, and different channels never touch each
other's files, even within the same workspace. A workspace- or
archive-root-level lock would block unrelated concurrent work for no
reason (e.g. nightly grinding through f3pugetsound's 120 channels
shouldn't stop a manual mid-day run against one f3nation channel).

Every tool that writes into (or, for export, reads a point-in-time
snapshot of) a channel directory acquires this before touching it:
backup's archive/resume+dedupe (backup_logic.backup_channel), the
standalone bot-image backfill script, and export's convert_export call
sites. See docs/DESIGN.md.

This closes the overlap risk seen in nightly.log (2026-08-05->06 and
2026-08-08->09: a channel's resume/dedupe step logs, then the next log
line is 20+ hours later at the *next* night's cron fire) - without a lock,
Task Scheduler firing on top of a still-running prior night, or a manual
mid-day run targeting the same channel, can race on the same sqlite file.
Complements sat-hh0 (subprocess timeout on the slackdump calls themselves)
- the lock alone doesn't help if nothing ever releases it because the
process holding it hung forever; the timeout is what guarantees the lock
actually gets released.
"""
from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

LOCK_SUFFIX = ".lock"


def lock_path_for(channel_directory: Path) -> Path:
    """The lock lives as a *sibling* of `channel_directory`
    (`<workspace_dir>/.<channel_slug>.lock`), not inside it. backup_channel's
    zero-message path does `shutil.rmtree(channel_directory)` while the lock
    is held (wiping a stale empty archive before re-archiving) - a lock file
    stored inside the directory it's protecting would be deleted along with
    it mid-hold, opening a race window right up until archive() recreates
    the directory. A sibling path is immune to whatever happens to the
    directory's own contents."""
    return channel_directory.parent / f".{channel_directory.name}{LOCK_SUFFIX}"


class ChannelLockedError(RuntimeError):
    """Raised when a channel's lock is already held by another live
    process. Callers processing a batch of channels should catch this and
    skip-and-continue, the same way they already handle
    slackdump.SlackdumpError - one busy channel must not abort the batch."""


def _is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by someone else - still alive from
        # our point of view.
        return True
    return True


def _read_lock(lock_path: Path) -> tuple[int, str] | None:
    """Returns (pid, since) from an existing lock file, or None if it's
    missing, empty, or doesn't start with a parseable pid (corrupt lock -
    treated the same as stale, below)."""
    try:
        text = lock_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not text:
        return None
    first_line, _, rest = text.partition("\n")
    try:
        pid = int(first_line)
    except ValueError:
        return None
    return pid, rest.strip()


def _try_create(lock_path: Path, content: str) -> bool:
    """Atomic create-if-absent (O_EXCL) - avoids a plain read-then-write
    race for the common case of two processes starting at once."""
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return True


@contextlib.contextmanager
def channel_lock(channel_directory: Path):
    """Exclusive lock on `channel_directory` for the life of the `with`
    block. Raises ChannelLockedError immediately if another live process
    already holds it. A lock left behind by a dead process (crash,
    kill -9, a killed batch run) is reclaimed automatically - detected via
    os.kill(pid, 0), not file age, so it's correct even across the
    multi-hour wall-clock gaps a suspended WSL2 host can produce (see the
    nightly.log hang investigation, 2026-08-09) where a live process can
    legitimately look "old" by mtime alone.
    """
    lock_path = lock_path_for(channel_directory)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    content = f"{os.getpid()}\n{since}\n"

    if not _try_create(lock_path, content):
        held = _read_lock(lock_path)
        if held is not None and _is_alive(held[0]):
            pid, since_held = held
            raise ChannelLockedError(
                f"{channel_directory} is locked by pid {pid}"
                + (f" (since {since_held})" if since_held else "")
            )
        # Stale (dead pid, or an unreadable/corrupt lock file) - reclaim.
        lock_path.unlink(missing_ok=True)
        if not _try_create(lock_path, content):
            # Lost a race with another reclaimer - treat as locked rather
            # than silently overwrite; caller can retry.
            held = _read_lock(lock_path)
            pid = held[0] if held else "?"
            raise ChannelLockedError(f"{channel_directory} is locked by pid {pid} (lost reclaim race)")

    try:
        yield
    finally:
        # Only remove it if it's still ours - never clobber a lock another
        # process has since (legitimately) acquired.
        current = _read_lock(lock_path)
        if current is not None and current[0] == os.getpid():
            lock_path.unlink(missing_ok=True)
