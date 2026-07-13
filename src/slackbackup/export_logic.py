#!/usr/bin/env python3
"""Monthly JSON export transform - the custom logic slackdump's
`convert -f export` does not provide: range bounding, monthly bucketing/
naming, thread nesting, and the sealed-month idempotency guard. Ported from
scripts/lib/export_transform.sh; reuses the exact same fixtures
(scripts/test_fixtures/export-archive/) for parity testing.

Sealing: with a stamp, month M is sealed iff the backup ran after M ended;
otherwise M is sealed iff the archive holds data in a later month
(high-water-mark fallback). Sealing alone is not sufficient to skip a
rewrite, though - a thread parented in month M can receive a reply long
after M is sealed (threads don't expire), and that reply must still land
under its parent in M's file. So a sealed month is only skipped when its
freshly computed content is also unchanged from what's already on disk;
otherwise it's rewritten even though sealed.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, AbstractSet

from . import catalog_logic, selector_logic
from .handlers import f3 as _default_handler

_DAY_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def _is_day_file(path: Path) -> bool:
    return bool(_DAY_FILE_RE.match(path.name))


def _load_all_messages(daydir: Path) -> list[dict]:
    files = sorted(p for p in daydir.rglob("*.json") if _is_day_file(p))
    messages: list[dict] = []
    for f in files:
        messages.extend(json.loads(f.read_text()))
    return messages


def _load_users_map(daydir: Path) -> dict[str, str]:
    users_file = daydir / "users.json"
    if not users_file.exists():
        return {}
    users = json.loads(users_file.read_text())
    result = {}
    for user in users:
        display = (user.get("profile") or {}).get("display_name") or ""
        if not display:
            display = user.get("real_name") or user.get("name") or user["id"]
        result[user["id"]] = display
    return result


def _is_parent(msg: dict) -> bool:
    thread_ts = msg.get("thread_ts")
    return thread_ts is None or thread_ts == msg.get("ts")


def _clean(msg: dict, users_map: dict[str, str]) -> dict:
    uid = msg.get("user") or msg.get("bot_id")
    resolved = users_map.get(uid) if uid is not None else None
    display_name = resolved or msg.get("username") or uid
    base = {"ts": msg["ts"], "text": msg.get("text"), "user": uid, "display_name": display_name}
    files = msg.get("files")
    if files:
        base["files"] = [
            {"name": f.get("name"), "filetype": f.get("filetype"), "permalink": f.get("permalink")}
            for f in files
        ]
    return base


def _format_month(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")


def _next_month(month: str) -> str:
    year, mon = (int(part) for part in month.split("-"))
    return f"{year + 1}-01" if mon == 12 else f"{year}-{mon + 1:02d}"


def _month_start_epoch(month: str) -> float:
    return datetime.strptime(f"{month}-01 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()


def _date_epoch(date: str, time_part: str) -> float:
    return datetime.strptime(f"{date} {time_part}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()


def export_month(
    all_messages: list[dict],
    workspace: str,
    channel: str,
    month: str,
    from_epoch: float,
    to_epoch: float,
    outdir: Path,
    hw_month: str | None,
    lb_epoch: float | None,
    users_map: dict[str, str],
) -> str:
    by_thread: dict[str, list[dict]] = {}
    for msg in all_messages:
        if _is_parent(msg):
            continue
        by_thread.setdefault(msg["thread_ts"], []).append(msg)
    for thread_ts, replies in by_thread.items():
        by_thread[thread_ts] = [
            _clean(m, users_map) for m in sorted(replies, key=lambda m: float(m["ts"]))
        ]

    messages = []
    for msg in all_messages:
        if not _is_parent(msg):
            continue
        parent_ts = float(msg["ts"])
        if not (from_epoch <= parent_ts <= to_epoch):
            continue
        if _format_month(parent_ts) != month:
            continue
        cleaned = _clean(msg, users_map)
        replies = by_thread.get(msg["ts"])
        if replies:
            cleaned["replies"] = replies
        messages.append(cleaned)
    messages.sort(key=lambda m: float(m["ts"]))

    if not messages:
        print(f"empty (no messages) {month}")
        return "empty"

    target = outdir / f"{workspace}-{channel}-{month}.json"

    if lb_epoch is not None:
        sealed = lb_epoch >= _month_start_epoch(_next_month(month))
    else:
        sealed = bool(hw_month) and hw_month > month

    existed = target.exists()

    if sealed and existed:
        try:
            existing_messages = json.loads(target.read_text()).get("messages")
        except (json.JSONDecodeError, OSError):
            existing_messages = None
        if existing_messages == messages:
            print(f"skipped (exists) {month}")
            return "skipped"

    year, mon = (int(part) for part in month.split("-"))
    last_day = monthrange(year, mon)[1]

    output = {
        "workspace": workspace,
        "channel": channel,
        "month": month,
        "range": {"from": f"{month}-01", "to": f"{month}-{last_day:02d}"},
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "messages": messages,
    }
    outdir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2))

    if not existed:
        print(f"wrote {month}")
        return "wrote"
    if sealed:
        print(f"rewrote (late reply to sealed month) {month}")
        return "rewrote_late"
    print(f"rewrote (trailing month) {month}")
    return "rewrote_trailing"


_MONTH_SUFFIX_RE = re.compile(r"-(\d{4}-\d{2})$")


def list_exports(
    out_dir: Path, workspace: str | None = None, channel: str | None = None
) -> list[dict]:
    """Scans `out_dir` for <workspace>-<channel>-yyyy-mm.json files and
    returns one row per file: {workspace, channel, month, path}, optionally
    filtered. Pure filesystem scan - no archive access, no API calls.

    Both workspace and channel names can contain hyphens (e.g.
    "dungeons-of-finn-hill", "all-f3-cascades"), so "<ws>-<ch>" can't be
    split unambiguously by regex alone. Resolved exactly whenever at least
    one of workspace/channel is given as a filter (the common case - you
    already know what you're listing); an unfiltered listing falls back to
    a best-effort split (first hyphen) since the ambiguity is then
    unresolvable from the filename alone.
    """
    rows = []
    for path in sorted(out_dir.glob("*.json")):
        match = _MONTH_SUFFIX_RE.search(path.stem)
        if not match:
            continue
        month = match.group(1)
        ws_ch = path.stem[: match.start()]

        if workspace is not None and channel is not None:
            if ws_ch != f"{workspace}-{channel}":
                continue
            row_ws, row_ch = workspace, channel
        elif workspace is not None:
            prefix = f"{workspace}-"
            if not ws_ch.startswith(prefix):
                continue
            row_ws, row_ch = workspace, ws_ch[len(prefix):]
        elif channel is not None:
            suffix = f"-{channel}"
            if not ws_ch.endswith(suffix):
                continue
            row_ws, row_ch = ws_ch[: -len(suffix)], channel
        elif "-" in ws_ch:
            row_ws, row_ch = ws_ch.split("-", 1)
        else:
            row_ws, row_ch = ws_ch, ""

        rows.append({"workspace": row_ws, "channel": row_ch, "month": month, "path": path})
    return rows


def export_transform(
    daydir: Path,
    workspace: str,
    channel: str,
    date_from: str,
    date_to: str,
    outdir: Path,
    last_backup_file: Path | None = None,
) -> list[tuple[str, str]]:
    all_messages = _load_all_messages(daydir)
    users_map = _load_users_map(daydir)

    hw_month = None
    if all_messages:
        hw_month = _format_month(max(float(m["ts"]) for m in all_messages))

    lb_epoch = None
    if last_backup_file is not None and last_backup_file.exists() and last_backup_file.stat().st_size > 0:
        stamp_text = last_backup_file.read_text().strip()
        try:
            lb_epoch = datetime.strptime(stamp_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            lb_epoch = None

    from_epoch = _date_epoch(date_from, "00:00:00")
    to_epoch = _date_epoch(date_to, "23:59:59")

    month = date_from[:7]
    end_month = date_to[:7]
    results = []
    while month <= end_month:
        result = export_month(
            all_messages, workspace, channel, month, from_epoch, to_epoch, outdir, hw_month, lb_epoch, users_map
        )
        results.append((month, result))
        month = _next_month(month)
    return results


# --- digest: one merged document spanning every message ever archived (or
# the trailing N days, via --days) across every workspace matching a glob,
# separate from the per-channel-month exporter above (different schema,
# different purpose - see docs/llm-export-suggestion.md). ---


def load_job(job_file: Path) -> dict:
    """Reads one jobs/*.json report definition (see .gitignore's comment on
    that path - operator-specific, never committed). Currently only
    type="digest" is implemented; other types raise so a typo'd or
    future-schema job fails loudly instead of silently producing nothing.

    Also validates "workspaces" is a list of workspace-name strings, not
    just present - a bare string (e.g. "f3pugetsound" instead of
    ["f3pugetsound"]) would otherwise iterate character-by-character where
    it's joined into a glob at the call site, silently producing a nonsense
    glob instead of failing loudly."""
    job = json.loads(job_file.read_text())
    if job.get("type") != "digest":
        raise ValueError(f"{job_file}: unsupported job type {job.get('type')!r}")
    if "workspaces" not in job:
        raise ValueError(f"{job_file}: missing required 'workspaces' list")
    workspaces = job["workspaces"]
    if not isinstance(workspaces, list) or not all(isinstance(w, str) for w in workspaces):
        raise ValueError(f"{job_file}: 'workspaces' must be a list of workspace names, got {workspaces!r}")
    return job


def expand_job_path(value: str) -> Path:
    """`~`/`~user` and `$VAR`/`${VAR}` expansion for a path read out of a
    job file - job files are hand-edited operator config, not code, so they
    get the same shorthand a shell would give them."""
    return Path(os.path.expandvars(os.path.expanduser(value)))


def resolve_job_out(out_template: str, as_of: str) -> Path:
    return expand_job_path(out_template.replace("{as_of}", as_of))


def select_channels(channels_file: Path, workspace_glob: str = "f3*") -> list[dict]:
    entries = json.loads(channels_file.read_text())
    return [e for e in entries if selector_logic.matches_selector(workspace_glob, e["workspace"])]


def trailing_days_range(days: int | None, as_of: str) -> tuple[str | None, str]:
    """Trailing `days` calendar days ending at `as_of`, inclusive of both
    ends (days=1 means just as_of's own date). `days=None` means no lower
    bound at all - digest every message ever archived. This function itself
    has no default: callers (export.py's CLI and --jobs runner) supply
    days=180 unless overridden, so `None` only reaches here when a caller
    explicitly asks for an unbounded digest."""
    if days is None:
        return None, as_of
    from_date = date.fromisoformat(as_of) - timedelta(days=days - 1)
    return from_date.isoformat(), as_of


def digest_message_url(workspace: str, channel_id: str, ts: str) -> str:
    return f"https://{workspace}.slack.com/archives/{channel_id}/p{ts.replace('.', '')}"


def _channel_context(catalog: dict, channel_id: str) -> dict:
    """description/creator/created_at for one channel, read-only from an
    already-loaded catalog cache (no API call, no refresh - the digest
    stays local-only; if the cache was never warmed for this channel, e.g.
    a fresh checkout, these are just None rather than triggering a live
    fetch). created_at is an ISO8601 string, not the raw epoch, matching
    this module's posted_at_utc convention elsewhere."""
    channel = catalog["channels"].get(channel_id, {})
    created = channel.get("created")
    return {
        "description": channel.get("description") or None,
        "creator": channel.get("creator") or None,
        "created_at": (
            datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if created else None
        ),
    }


_BLOCK_TAGS = {"p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br"}
_CELL_TAGS = {"td", "th"}


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML-to-text, stdlib only (no new dependency for what's
    currently just one content type - Slack Canvases, which are real HTML
    on disk despite the "application/vnd.slack-docs" mimetype). Not a full
    renderer: block tags become newlines, table cells become " | "
    separators, everything else is just text content concatenated in
    document order. Good enough for an LLM to read a Canvas's table/text
    structure - not pixel-perfect reflow."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _CELL_TAGS:
            self._parts.append(" | ")
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [re.sub(r"[ \t]+", " ", line).strip(" |") for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def _html_to_text(raw_html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    return parser.text()


# Content is only extracted for types we can read without a new dependency:
# Slack Canvases (real HTML on disk despite this pseudo-mimetype) and plain
# text/*. Everything else (PDF, video, external Google Sheets links with no
# downloadable blob at all, ...) stays metadata-only - content: None.
_HTML_LIKE_MIMETYPES = {"application/vnd.slack-docs", "text/html"}


def _extract_file_content(mimetype: str, path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if mimetype in _HTML_LIKE_MIMETYPES:
        return _html_to_text(raw)
    if mimetype.startswith("text/"):
        return raw
    return None


def _clean_file(data: dict) -> dict:
    created = data.get("created")
    return {
        "id": data["id"],
        "name": data.get("name"),
        "title": data.get("title"),
        "filetype": data.get("filetype"),
        "mimetype": data.get("mimetype"),
        "pretty_type": data.get("pretty_type"),
        "creator": data.get("user") or None,
        "created_at": (
            datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if created else None
        ),
        "size": data.get("size"),
        "permalink": data.get("permalink") or None,
    }


def _load_channel_files(channel_dir: Path) -> list[dict]:
    """Reads channel_dir's slackdump.sqlite FILE table directly - not via
    convert_fn's message-anchored export, which never surfaces these at
    all for an unattached channel Canvas (FILE.MESSAGE_ID is "EMPTY FOR
    CHANNEL CANVAS FILES" per the table's own comment - a Canvas isn't a
    reply to anything). Read-only, local-only, no API call. Non-image
    only (mimetype not image/*), matching docs/DESIGN-files.md's existing
    non-image filtering convention. Deduped by file id - the same row can
    repeat across resume cycles, like MESSAGE.
    """
    db_path = channel_dir / "slackdump.sqlite"
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT DATA FROM FILE").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        # Malformed/placeholder archive (e.g. a 0-byte file) - no FILE
        # table to read, same as "no files" rather than a hard failure.
        return []

    by_id: dict[str, dict] = {}
    for (raw,) in rows:
        data = json.loads(raw)
        if (data.get("mimetype") or "").startswith("image/"):
            continue
        by_id[data["id"]] = data

    files = []
    for data in by_id.values():
        cleaned = _clean_file(data)
        local_path = channel_dir / "__uploads" / cleaned["id"] / (cleaned["name"] or "")
        exists = local_path.exists()
        cleaned["local_path"] = str(local_path.relative_to(channel_dir.parent.parent)) if exists else None
        cleaned["content"] = _extract_file_content(cleaned["mimetype"] or "", local_path if exists else None)
        files.append(cleaned)

    files.sort(key=lambda f: f["created_at"] or "")
    return files


def select_messages_in_range(
    all_messages: list[dict], users_map: dict[str, str], from_epoch: float, to_epoch: float
) -> list[dict]:
    """Like export_month's filtering/nesting, but range-bounded only - no
    calendar-month bucketing, since a digest spans multiple months in one
    document."""
    by_thread: dict[str, list[dict]] = {}
    for msg in all_messages:
        if _is_parent(msg):
            continue
        by_thread.setdefault(msg["thread_ts"], []).append(msg)
    for thread_ts, replies in by_thread.items():
        by_thread[thread_ts] = [
            _clean(m, users_map) for m in sorted(replies, key=lambda m: float(m["ts"]))
        ]

    messages = []
    for msg in all_messages:
        if not _is_parent(msg):
            continue
        parent_ts = float(msg["ts"])
        parent_in_range = from_epoch <= parent_ts <= to_epoch
        replies = by_thread.get(msg["ts"])
        reply_in_range = replies is not None and any(
            from_epoch <= float(r["ts"]) <= to_epoch for r in replies
        )
        if not parent_in_range and not reply_in_range:
            continue
        cleaned = _clean(msg, users_map)
        if replies:
            cleaned["replies"] = replies
        if not parent_in_range:
            # Parent predates the export window but a reply revived the
            # thread inside it (see docs/DESIGN-export.md Idempotency for
            # the analogous late-reply case in export_month) - keep the
            # thread but flag the parent so _channel_activity can exclude
            # it from root counts while its in-range replies still count.
            cleaned["in_scope"] = False
        messages.append(cleaned)
    messages.sort(key=lambda m: float(m["ts"]))
    return messages


def _format_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _enrich_for_digest(msg: dict, workspace: str, channel: str, channel_id: str) -> None:
    msg["workspace"] = workspace
    msg["channel"] = channel
    msg["channel_id"] = channel_id
    msg["message_url"] = digest_message_url(workspace, channel_id, msg["ts"])
    msg["posted_at_utc"] = _format_utc(float(msg["ts"]))
    replies = msg.get("replies")
    if replies:
        # Thread rollups so a consumer can answer "how active was this
        # thread" without re-walking replies[] - the root author counts as
        # a thread participant too, not just repliers.
        participants = {msg.get("user")} | {r.get("user") for r in replies}
        msg["reply_count"] = len(replies)
        msg["thread_participant_count"] = len(participants - {None})
        msg["thread_last_reply_utc"] = _format_utc(max(float(r["ts"]) for r in replies))
        for reply in replies:
            _enrich_for_digest(reply, workspace, channel, channel_id)


_BOT_ID_PREFIX = "B"


def _is_bot_author(uid: str | None, bot_ids: AbstractSet[str]) -> bool:
    # Two authoritative signals, neither name-based: Slack's own id
    # convention for messages with no resolvable user (bot ids start with
    # "B", human user ids with "U"), and the workspace roster's own is_bot
    # flag (folded into slack_roles by _clean_user) for the common case of
    # a bot posting through an ordinary "U..." user account.
    return uid is not None and (uid.startswith(_BOT_ID_PREFIX) or uid in bot_ids)


def _channel_activity(messages: list[dict], bot_ids: AbstractSet[str] = frozenset()) -> dict:
    """Precomputed counts for one channel's already range-filtered,
    thread-nested message list (the same shape build_digest already
    produces per channel) - so a digest consumer doesn't have to recount
    root/reply messages itself to answer "which channels are active" or
    "most active channel" questions. Returns both the fields exposed on
    the channel's digest entry and the extra (set/human-only) data
    build_digest needs to aggregate workspace_activity_index, since that
    aggregation can't be done correctly from counts alone (set union,
    not sum, avoids double-counting a participant across channels)."""
    participants: set[str] = set()
    human_participants: set[str] = set()
    timestamps: list[float] = []
    human_total = 0
    root_count = 0
    for msg in messages:
        # A parent flagged in_scope:false (see select_messages_in_range)
        # predates the export window - it's only present so its in-range
        # replies have somewhere to nest, and must not itself count as a
        # root message, participant, or first/last timestamp.
        if msg.get("in_scope") is not False:
            root_count += 1
            timestamps.append(float(msg["ts"]))
            uid = msg.get("user")
            if uid is not None:
                participants.add(uid)
                if not _is_bot_author(uid, bot_ids):
                    human_participants.add(uid)
                    human_total += 1
            elif not _is_bot_author(uid, bot_ids):
                human_total += 1
        for reply in msg.get("replies", ()):
            timestamps.append(float(reply["ts"]))
            ruid = reply.get("user")
            if ruid is not None:
                participants.add(ruid)
                if not _is_bot_author(ruid, bot_ids):
                    human_participants.add(ruid)
                    human_total += 1
            elif not _is_bot_author(ruid, bot_ids):
                human_total += 1

    reply_count = len(timestamps) - root_count
    total = root_count + reply_count
    fields = (
        {
            "root_message_count": 0, "reply_count": 0, "total_message_count": 0,
            "participant_count": 0, "first_message_utc": None, "last_message_utc": None,
            "activity_status": "inactive",
            "activity_status_basis": "zero root messages and zero nested replies during export_scope",
        }
        if total == 0
        else {
            "root_message_count": root_count, "reply_count": reply_count, "total_message_count": total,
            "participant_count": len(participants), "first_message_utc": _format_utc(min(timestamps)),
            "last_message_utc": _format_utc(max(timestamps)),
            "activity_status": "active", "activity_status_basis": "has messages during export_scope",
        }
    )
    return {
        **fields,
        "_participants": participants,
        "_human_total_message_count": human_total,
    }


def _build_workspace_activity_index(channels_meta: list[dict], activity_by_channel: dict[tuple, dict]) -> list[dict]:
    """One record per workspace, aggregated from each "ok" channel's
    _channel_activity() output - keyed by (workspace, channel_id) so a
    workspace with two channels sharing a name still aggregates correctly."""
    by_workspace: dict[str, list[dict]] = {}
    for meta in channels_meta:
        by_workspace.setdefault(meta["workspace"], []).append(meta)

    index: list[dict] = []
    for workspace in sorted(by_workspace):
        entries = by_workspace[workspace]
        ok_entries = [e for e in entries if e["status"] == "ok"]
        active = [e for e in ok_entries if e["activity_status"] == "active"]
        inactive = [e for e in ok_entries if e["activity_status"] == "inactive"]

        participants: set[str] = set()
        human_totals: dict[str, int] = {}
        for entry in ok_entries:
            activity = activity_by_channel[(workspace, entry["channel_id"])]
            participants |= activity["_participants"]
            human_totals[entry["channel_id"]] = activity["_human_total_message_count"]

        def _channel_summary(entry: dict) -> dict:
            return {
                "channel": entry["channel"],
                "root_message_count": entry["root_message_count"],
                "reply_count": entry["reply_count"],
                "total_message_count": entry["total_message_count"],
            }

        most_active = max(active, key=lambda e: e["total_message_count"], default=None)
        human_candidates = [e for e in active if human_totals[e["channel_id"]] > 0]
        most_active_human = max(human_candidates, key=lambda e: human_totals[e["channel_id"]], default=None)

        index.append(
            {
                "workspace": workspace,
                "channel_count": len(entries),
                "active_channel_count": len(active),
                "inactive_channel_count": len(inactive),
                "root_message_count": sum(e["root_message_count"] for e in ok_entries),
                "reply_count": sum(e["reply_count"] for e in ok_entries),
                "total_message_count": sum(e["total_message_count"] for e in ok_entries),
                "participant_count": len(participants),
                "most_active_channel": _channel_summary(most_active) if most_active else None,
                "most_active_human_channel": _channel_summary(most_active_human) if most_active_human else None,
                "inactive_channels": sorted(e["channel"] for e in inactive),
                "inactive_definition": "zero root messages and zero nested replies during export_scope",
            }
        )
    return index


def build_digest(
    channels_file: Path,
    archive_root: Path,
    workspace_glob: str,
    days: int | None,
    as_of: str,
    convert_fn: Callable[[Path, Path], None],
    catalog_cache_dir: Path = catalog_logic.DEFAULT_CACHE_DIR,
    handler=_default_handler,
    profiles_doc: dict | None = None,
) -> dict:
    """Reads every (workspace, channel) in `channels_file` matching
    `workspace_glob`, converts each channel's archive (via `convert_fn` -
    normally `slackdump.convert_export`, injected so tests can fake it),
    and merges messages from the trailing `days` days (or everything ever
    archived, when `days` is None) into one chronologically-sorted
    document. A channel with no archive on disk is recorded with status
    "missing_archive" and skipped - one un-archived channel must not abort
    a digest spanning many workspaces.

    Deliberately has no top-level merged "users"/"authors" table: the same
    Slack user id (or display name) in two different workspaces is not the
    same identity, so author info stays embedded per-message, scoped to
    that message's own workspace, exactly as `_clean()` already resolves it.

    Each "ok" channel's entry also carries its non-image files/Canvases
    (see _load_channel_files) - read directly from the channel's own
    archive, not via convert_fn, since an unattached channel Canvas never
    surfaces in a message-anchored export.

    `handler` (see handlers/__init__.py) supplies the digest's "leadership"
    section - defaults to the "f3" handler for backward compatibility with
    this project's original (F3-only) purpose; pass handler=None to disable
    leadership inference entirely (an empty leadership section), which is
    the right choice for a non-F3 workspace. `profiles_doc`, if the caller
    already built one (e.g. to also write it out as a standalone
    deliverable - see export.py's job runner), is reused as-is instead of
    re-converting every workspace's archive a second time; it must already
    be tagged by the same `handler`.
    """
    date_from, date_to = trailing_days_range(days, as_of)
    from_epoch = _date_epoch(date_from, "00:00:00") if date_from else 0.0
    to_epoch = _date_epoch(date_to, "23:59:59")

    # Built up front (not after the channel loop) because per-channel
    # activity needs each workspace's bot-id set to tell a bot/log channel
    # apart from a human one - is_bot is on the user roster, not on the
    # cleaned message, and a bot frequently posts as an ordinary "U..."
    # user account rather than via Slack's legacy bot_id field, so a
    # bot_id-prefix check alone misses it (see SlackBackup follow-up: the
    # f3kirkland nation_bot_logs bot posts as user U0A3GF12LEA).
    if profiles_doc is None:
        profiles_doc = build_user_profiles(channels_file, archive_root, workspace_glob, convert_fn, handler=handler)
    bot_ids_by_workspace: dict[str, set[str]] = {
        ws_entry["workspace"]: {p["id"] for p in ws_entry["profiles"] if "bot" in p["slack_roles"]}
        for ws_entry in profiles_doc["workspaces"]
        if ws_entry["status"] == "ok"
    }

    channels_meta: list[dict] = []
    messages: list[dict] = []
    activity_by_channel: dict[tuple, dict] = {}

    catalog_cache: dict[str, dict] = {}

    for entry in select_channels(channels_file, workspace_glob):
        workspace, channel, channel_id = entry["workspace"], entry["name"], entry["id"]
        if workspace not in catalog_cache:
            catalog_cache[workspace] = catalog_logic.load(catalog_cache_dir, workspace)
        channel_info = _channel_context(catalog_cache[workspace], channel_id)

        channel_dir = archive_root / workspace / channel
        if not (channel_dir / "slackdump.sqlite").exists():
            channels_meta.append(
                {
                    "workspace": workspace, "channel": channel, "channel_id": channel_id,
                    "status": "missing_archive", "files": [], **channel_info,
                }
            )
            continue

        with tempfile.TemporaryDirectory() as export_dir:
            export_dir_path = Path(export_dir)
            convert_fn(channel_dir, export_dir_path)
            all_messages = _load_all_messages(export_dir_path)
            users_map = _load_users_map(export_dir_path)

        cleaned = select_messages_in_range(all_messages, users_map, from_epoch, to_epoch)
        activity = _channel_activity(cleaned, bot_ids_by_workspace.get(workspace, set()))
        activity_by_channel[(workspace, channel_id)] = activity
        activity_fields = {k: v for k, v in activity.items() if not k.startswith("_")}
        for msg in cleaned:
            _enrich_for_digest(msg, workspace, channel, channel_id)
        messages.extend(cleaned)
        channels_meta.append(
            {
                "workspace": workspace, "channel": channel, "channel_id": channel_id,
                "status": "ok", "files": _load_channel_files(channel_dir), **channel_info,
                **activity_fields,
            }
        )

    messages.sort(key=lambda m: float(m["ts"]))

    # Leadership candidates come from the full per-workspace roster
    # (build_user_profiles/profiles_doc), not just this digest's posters -
    # a leader who didn't happen to post in this window should still
    # surface. This is the digest's *only* profile data; everyone else in
    # the roster is intentionally left out (see build_user_profiles for the
    # full list). Delegated entirely to `handler` - see its module docstring
    # in handlers/__init__.py; an empty section when no handler is set.
    leadership = (
        handler.build_leadership(profiles_doc)
        if handler is not None
        else {"profile_role_matches": [], "by_region": [], "former_by_region": []}
    )

    return {
        "schema_version": "slack-llm-digest-v2",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "export_scope": {"from": date_from, "to": date_to, "days": days, "workspace_glob": workspace_glob},
        "manifest": {
            "workspaces_included": len({c["workspace"] for c in channels_meta}),
            "counting_rules": {
                "root_message_count": "top-level messages only",
                "reply_count": "nested replies under root messages",
                "total_message_count": "root_message_count plus reply_count",
                "activity_status": "active when total_message_count > 0 in export_scope, else inactive",
                "in_scope": (
                    "a thread whose parent predates export_scope but received a reply inside it "
                    "is still included in full (parent plus all replies); its parent record carries "
                    "in_scope: false and is excluded from root_message_count, participant_count, and "
                    "first_message_utc/last_message_utc, while its in-range replies are still counted "
                    "as replies. Records without this key are implicitly in scope; the key is never "
                    "emitted as true."
                ),
            },
            "known_limitations": [
                "Private or inaccessible channels may be absent",
                "User profile completeness depends on Slack profile data",
                "Leadership roles may be inferred from display names unless explicitly confirmed",
            ],
        },
        "channels": channels_meta,
        "workspace_activity_index": _build_workspace_activity_index(channels_meta, activity_by_channel),
        "messages": messages,
        "leadership": leadership,
    }


# --- user profiles: the full per-workspace roster (everyone slackdump has
# cached, not just digest posters), kept as a separate document since
# profile identity does not carry across workspaces - see build_digest's
# docstring. ---


# Slack-platform role/account-type flags, folded into one "slack_roles"
# list rather than a pile of individual is_* booleans. Distinct from the
# digest's inferred F3-leadership-position scan - these are authoritative,
# not inferred, and already present on the raw user object. Excludes
# is_invited_user/is_email_confirmed (account status, not a role) per the
# same noise-stripping philosophy as the rest of _clean_user.
_SLACK_ROLE_FLAGS = (
    ("is_primary_owner", "primary_owner"),
    ("is_owner", "owner"),
    ("is_admin", "admin"),
    ("is_bot", "bot"),
    ("is_app_user", "app_user"),
    ("is_restricted", "restricted"),
    ("is_ultra_restricted", "ultra_restricted"),
    ("is_stranger", "stranger"),
)


def _slack_roles(user: dict) -> list[str]:
    return [role for flag, role in _SLACK_ROLE_FLAGS if user.get(flag, False)]


def _clean_user(user: dict) -> dict:
    """Field-reduces a raw Slack user object to identity fields only -
    drops avatar URLs, email/phone, presence, enterprise_user, etc., same
    noise-stripping philosophy as _clean() for messages."""
    profile = user.get("profile") or {}
    return {
        "id": user["id"],
        "name": user.get("name"),
        "real_name": user.get("real_name"),
        "display_name": profile.get("display_name") or None,
        "title": profile.get("title") or None,
        "deleted": user.get("deleted", False),
        "slack_roles": _slack_roles(user),
    }


def build_user_profiles(
    channels_file: Path,
    archive_root: Path,
    workspace_glob: str,
    convert_fn: Callable[[Path, Path], None],
    handler=None,
) -> dict:
    """users.json from `convert -f export` is workspace-scoped, identical
    no matter which of that workspace's channels you convert - so this
    converts just one archived channel per workspace (whichever is
    archived first) to fetch it, rather than every channel.

    `handler` (see handlers/__init__.py), when given, tags each profile
    with a "derived_leadership" field via handler.annotate_profile() -
    None (the default) leaves profiles untouched, since this general-
    purpose roster export has no reason to assume any particular region's
    role vocabulary unless asked."""
    by_workspace: dict[str, list[dict]] = {}
    for entry in select_channels(channels_file, workspace_glob):
        by_workspace.setdefault(entry["workspace"], []).append(entry)

    workspaces_out = []
    for workspace in sorted(by_workspace):
        archived = next(
            (e for e in by_workspace[workspace] if (archive_root / workspace / e["name"] / "slackdump.sqlite").exists()),
            None,
        )
        if archived is None:
            workspaces_out.append({"workspace": workspace, "status": "missing_archive", "profiles": []})
            continue

        channel_dir = archive_root / workspace / archived["name"]
        with tempfile.TemporaryDirectory() as export_dir:
            export_dir_path = Path(export_dir)
            convert_fn(channel_dir, export_dir_path)
            users_file = export_dir_path / "users.json"
            raw_users = json.loads(users_file.read_text()) if users_file.exists() else []

        profiles = [_clean_user(u) for u in raw_users]
        if handler is not None:
            for profile in profiles:
                profile["derived_leadership"] = handler.annotate_profile(profile["display_name"], profile["title"])

        workspaces_out.append({"workspace": workspace, "status": "ok", "profiles": profiles})

    return {
        "schema_version": "slack-user-profiles-v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace_glob": workspace_glob,
        "workspaces": workspaces_out,
    }
