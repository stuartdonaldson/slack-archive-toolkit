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

import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile

import pypdf
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, AbstractSet
from zoneinfo import ZoneInfo

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


_ARCHIVE_URL_RE = re.compile(r"/archives/([^/]+)/p(\d+)")


def _parse_archive_url(url: str) -> tuple[str, str] | None:
    match = _ARCHIVE_URL_RE.search(url)
    if not match:
        return None
    channel_id, digits = match.group(1), match.group(2)
    return channel_id, f"{digits[:-6]}.{digits[-6:]}"


_MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")
_LINK_TOKEN_RE = re.compile(r"<(https?://[^|>]+)(?:\|([^>]*))?>")


def _extract_mentions(text: str | None) -> list[str]:
    """<@U...> user ids in order of first appearance, deduped."""
    if not text:
        return []
    seen: list[str] = []
    for match in _MENTION_RE.finditer(text):
        uid = match.group(1)
        if uid not in seen:
            seen.append(uid)
    return seen


def _extract_links(text: str | None) -> list[dict]:
    """Slack angle-bracket link tokens <url> / <url|label> (url must start
    with http, so <#C...>/<@U...>/<!here> tokens are never matched here)."""
    if not text:
        return []
    links = []
    for match in _LINK_TOKEN_RE.finditer(text):
        url, label = match.group(1), match.group(2)
        entry = {"url": url, "label": label or None}
        if "slack.com/archives/" in url:
            entry["type"] = "slack_message"
            target = _parse_archive_url(url)
            if target:
                entry["target_channel_id"], entry["target_ts"] = target
        elif "slack.com/docs/" in url or "slack.com/files/" in url:
            entry["type"] = "slack_file"
        else:
            entry["type"] = "external"
        links.append(entry)
    return links


def _block_texts(msg: dict) -> list[str]:
    """Text bodies of Block Kit blocks carrying a text object (section/
    header). Bot-posted backblasts (F3 Nation/PAXminer crosspost) put the
    *PAX*: line with its <@U...> mentions in blocks[].text.text while the
    top-level msg.text is a narrative-only fallback, so mention/link
    extraction must read both sources (SlackBackup-rie)."""
    texts = []
    for block in msg.get("blocks") or []:
        text = block.get("text")
        if isinstance(text, dict) and text.get("text"):
            texts.append(text["text"])
    return texts


def _unfurls_from_attachments(attachments: list[dict]) -> list[dict]:
    unfurls = []
    for att in attachments:
        from_url = att.get("from_url")
        is_msg_unfurl = att.get("is_msg_unfurl") or (from_url and "slack.com/archives/" in from_url)
        if is_msg_unfurl:
            entry = {
                "url": from_url,
                "author_name": att.get("author_name"),
                "quoted_text": att.get("text"),
            }
            target = _parse_archive_url(from_url) if from_url else None
            if target:
                entry["target_channel_id"], entry["target_ts"] = target
            unfurls.append(entry)
            continue
        title_link = att.get("title_link")
        if from_url or title_link:
            unfurls.append({"url": from_url or title_link, "title": att.get("title")})
    return unfurls


def _clean(msg: dict, users_map: dict[str, str], evidence: bool = False, channel_dir: Path | None = None) -> dict:
    uid = msg.get("user") or msg.get("bot_id")
    resolved = users_map.get(uid) if uid is not None else None
    display_name = resolved or msg.get("username") or uid
    base = {"ts": msg["ts"], "text": msg.get("text"), "user": uid, "display_name": display_name}
    files = msg.get("files")
    if files:
        cleaned_files = []
        for f in files:
            entry = {
                "id": f.get("id"), "name": f.get("name"), "filetype": f.get("filetype"), "permalink": f.get("permalink"),
            }
            if channel_dir is not None:
                # Only the digest path passes channel_dir - export_month has
                # no equivalent field and keeps its existing schema untouched.
                entry["local_path"] = _resolve_local_path(channel_dir, f.get("id"), f.get("name"))
            cleaned_files.append(entry)
        base["files"] = cleaned_files
    if evidence:
        reactions = msg.get("reactions")
        if reactions:
            base["reactions"] = [
                {"name": r.get("name"), "count": r.get("count"), "users": r.get("users")}
                for r in reactions
            ]
        edited = msg.get("edited")
        if edited:
            base["edited"] = {"user": edited.get("user"), "at_utc": _format_utc(float(edited["ts"]))}
        subtype = msg.get("subtype")
        if subtype:
            base["subtype"] = subtype
        attachments = msg.get("attachments")
        if attachments:
            unfurls = _unfurls_from_attachments(attachments)
            if unfurls:
                base["unfurls"] = unfurls
        sources = [msg.get("text"), *_block_texts(msg)]
        mentions: list[str] = []
        links: list[dict] = []
        for source in sources:
            for uid in _extract_mentions(source):
                if uid not in mentions:
                    mentions.append(uid)
            for link in _extract_links(source):
                if link not in links:
                    links.append(link)
        if mentions:
            base["mentions"] = mentions
        if links:
            base["links"] = links
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
    if job.get("split_by_month") and "{month}" not in job.get("out", ""):
        raise ValueError(f"{job_file}: 'split_by_month' is set but 'out' has no {{month}} placeholder")
    return job


def expand_job_path(value: str) -> Path:
    """`~`/`~user` and `$VAR`/`${VAR}` expansion for a path read out of a
    job file - job files are hand-edited operator config, not code, so they
    get the same shorthand a shell would give them."""
    return Path(os.path.expandvars(os.path.expanduser(value)))


def resolve_job_out(out_template: str | Path, as_of: str, month: str | None = None) -> Path:
    resolved = str(out_template).replace("{as_of}", as_of)
    if month is not None:
        resolved = resolved.replace("{month}", month)
    return expand_job_path(resolved)


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


def digest_channel_url(workspace: str, channel_id: str) -> str:
    return f"https://{workspace}.slack.com/archives/{channel_id}"


def digest_message_url(workspace: str, channel_id: str, ts: str) -> str:
    return f"https://{workspace}.slack.com/archives/{channel_id}/p{ts.replace('.', '')}"


def _channel_context(catalog: dict, channel_id: str) -> dict:
    """description/creator/created_at for one channel, read-only from an
    already-loaded catalog cache (no API call, no refresh - the digest
    stays local-only; if the cache was never warmed for this channel, e.g.
    a fresh checkout, these are just None rather than triggering a live
    fetch). created_at is an ISO8601 string, not the raw epoch, matching
    this module's posted_at_local convention elsewhere."""
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


# Content is extracted for types we can read cheaply: Slack Canvases (real
# HTML on disk despite this pseudo-mimetype), plain text/*, PDF (pypdf), and
# the OOXML Office formats (docx/pptx/xlsx - all just zip archives of XML,
# read with stdlib zipfile, no new dependency for those three). Images and
# anything else (video, audio, external Google Sheets links with no
# downloadable blob at all, ...) stay metadata-only - content: None.
_HTML_LIKE_MIMETYPES = {"application/vnd.slack-docs", "text/html"}
_DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIMETYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_TEXT_RUN_RE = re.compile(r"<[aw]:t[^>]*>(.*?)</[aw]:t>", re.DOTALL)
_SHARED_STRING_RE = re.compile(r"<t[^>]*>(.*?)</t>", re.DOTALL)


def _extract_pdf_text(path: Path) -> str | None:
    try:
        reader = pypdf.PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return None
    text = text.strip()
    return text or None


def _extract_zip_xml_text(path: Path, member_glob: str, pattern: re.Pattern) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            names = sorted(n for n in zf.namelist() if fnmatch.fnmatch(n, member_glob))
            parts = []
            for name in names:
                xml = zf.read(name).decode("utf-8", errors="replace")
                parts.extend(pattern.findall(xml))
    except (zipfile.BadZipFile, OSError):
        return None
    text = "\n".join(p for p in parts if p).strip()
    return text or None


def _extract_file_content(mimetype: str, path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    if mimetype == "application/pdf":
        return _extract_pdf_text(path)
    if mimetype == _DOCX_MIMETYPE:
        return _extract_zip_xml_text(path, "word/document.xml", _TEXT_RUN_RE)
    if mimetype == _PPTX_MIMETYPE:
        return _extract_zip_xml_text(path, "ppt/slides/slide*.xml", _TEXT_RUN_RE)
    if mimetype == _XLSX_MIMETYPE:
        return _extract_zip_xml_text(path, "xl/sharedStrings.xml", _SHARED_STRING_RE)
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


def _file_archive_status(data: dict, blob_exists: bool, content: str | None) -> str:
    """One of content_extracted | no_blob | unsupported_type | tombstone
    (sat-811 §8) - lets a files_out consumer tell "no text because Slack
    deleted the file" apart from "no text because we can't parse this
    type" apart from "we never captured the blob at all". The tombstone
    check (Slack's FILE.mode == "tombstone" for a deleted file) is a
    best-effort inference, not verified against a real tombstoned row in
    this project's archives - a wrong guess here only costs a cosmetic
    "unsupported_type"/"no_blob" instead of "tombstone", never content."""
    if data.get("mode") == "tombstone":
        return "tombstone"
    if not blob_exists:
        return "no_blob"
    if content is not None:
        return "content_extracted"
    return "unsupported_type"


def _resolve_local_path(channel_dir: Path | None, file_id: str | None, name: str | None) -> str | None:
    """Path (relative to the archive root - two levels above channel_dir,
    i.e. <workspace>/<channel>/...) to the downloaded blob for a file, if
    slackdump actually fetched it. None when the file was never attached to
    a channel_dir (no local archive context) or the blob isn't on disk."""
    if channel_dir is None or file_id is None:
        return None
    local_path = channel_dir / "__uploads" / file_id / (name or "")
    if not local_path.exists():
        return None
    return str(local_path.relative_to(channel_dir.parent.parent))


def _load_channel_files(channel_dir: Path) -> list[dict]:
    """Reads channel_dir's slackdump.sqlite FILE table directly - not via
    convert_fn's message-anchored export, which never surfaces these at
    all for an unattached channel Canvas (FILE.MESSAGE_ID is NULL for
    channel Canvas files - a Canvas isn't a reply to anything). Read-only,
    local-only, no API call. Includes images (metadata + local_path only,
    since content extraction doesn't apply to them - see
    _extract_file_content). Deduped by file id - the same row can repeat
    across resume cycles, like MESSAGE. When merging duplicate rows, prefer
    one with non-null MESSAGE_ID.
    """
    db_path = channel_dir / "slackdump.sqlite"
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT DATA, MESSAGE_ID FROM FILE").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        # Malformed/placeholder archive (e.g. a 0-byte file) - no FILE
        # table to read, same as "no files" rather than a hard failure.
        return []

    by_id: dict[str, tuple[dict, str | None]] = {}
    for raw, message_id in rows:
        data = json.loads(raw)
        # When deduping by id, prefer rows with non-null MESSAGE_ID over null.
        file_id = data["id"]
        if file_id not in by_id or by_id[file_id][1] is None:
            by_id[file_id] = (data, message_id)

    files = []
    for data, message_id in by_id.values():
        cleaned = _clean_file(data)
        if message_id is not None:
            cleaned["message_ts"] = message_id
        blob_path = channel_dir / "__uploads" / cleaned["id"] / (cleaned["name"] or "")
        exists = blob_path.exists()
        cleaned["local_path"] = str(blob_path.relative_to(channel_dir.parent.parent)) if exists else None
        cleaned["content"] = _extract_file_content(cleaned["mimetype"] or "", blob_path if exists else None)
        # sat-811 §8 (files_out sidecar change-detection): content_sha256
        # lets a cumulative sidecar detect a real content edit even if the
        # tabbed_canvas_updated notice that would have announced it was
        # later deleted from the channel (see _extract_canvas_modification_events).
        cleaned["content_sha256"] = (
            hashlib.sha256(cleaned["content"].encode("utf-8")).hexdigest() if cleaned["content"] is not None else None
        )
        cleaned["blob_captured_at"] = _format_utc(blob_path.stat().st_mtime) if exists else None
        cleaned["archive_status"] = _file_archive_status(data, exists, cleaned["content"])
        files.append(cleaned)

    files.sort(key=lambda f: f["created_at"] or "")
    return files


_DIGEST_ONLY_FILE_KEYS = ("content", "content_sha256", "archive_status", "blob_captured_at")


def _digest_file_view(file_entry: dict) -> dict:
    """The digest's channels[].files[] entry (schema v4, sat-811 §3):
    everything _load_channel_files produces except the extracted `content`
    itself (and the sidecar-only fields that travel with it) - content
    lives in the files_out sidecar now, joined by (workspace, channel_id,
    id). `has_content` tells a consumer whether it's worth the join."""
    out = {k: v for k, v in file_entry.items() if k not in _DIGEST_ONLY_FILE_KEYS}
    out["has_content"] = file_entry.get("content") is not None
    return out


_CANVAS_MIMETYPE = "application/vnd.slack-docs"


def _is_canvas_file(file_entry: dict) -> bool:
    return file_entry.get("mimetype") == _CANVAS_MIMETYPE or file_entry.get("pretty_type") == "Canvas"


_CANVAS_UPDATE_TEXT_RE = re.compile(r"^(.+?)\s+made updates to a canvas tab:\s*$")


_CANVAS_UPDATE_UNWRAP_LIMIT = 5


def _canvas_update_file_id(elements: list[dict]) -> str | None:
    for el in elements:
        # Verified against real archived tabbed_canvas_updated messages
        # (sat-811 §9): the canvas block element's payload key is "Raw"
        # (capital R), not "raw" - Slack's own inconsistent casing, not a
        # typo here. slackdump's own `convert -f export` has no native Go
        # struct for this rich_text sub-element type, so it round-trips the
        # unrecognized element through its own generic {"type":...,
        # "Raw": <json-string>} wrapper on top of whatever was already in
        # the archive - observed 2 levels deep on a real f3nation message
        # (once from Slack's own event shape, once more from slackdump's
        # export step), so this unwraps repeatedly (bounded) until a
        # "file_id" key surfaces, rather than assuming a fixed depth.
        payload = el
        for _ in range(_CANVAS_UPDATE_UNWRAP_LIMIT):
            if not isinstance(payload, dict):
                break
            file_id = payload.get("file_id")
            if file_id:
                return file_id
            raw = payload.get("Raw")
            if not raw:
                break
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                break
    return None


def _parse_canvas_update_message(msg: dict) -> dict | None:
    """Parses a Slack `tabbed_canvas_updated` system message (sat-811 §9)
    into {file_id, editor_name (raw, possibly compound), ts}, or None if
    the block shape doesn't match - defensive, since this subtype's block
    layout is reverse-engineered from the archive, not documented by
    Slack. user is always USLACKBOT on this subtype; the real editor is
    only present as a display-name string in the block text."""
    if msg.get("subtype") != "tabbed_canvas_updated":
        return None
    editor_text = None
    file_id = None
    for block in msg.get("blocks") or []:
        for outer in block.get("elements") or []:
            elements = outer.get("elements") or []
            if editor_text is None:
                for el in elements:
                    if el.get("type") == "text":
                        match = _CANVAS_UPDATE_TEXT_RE.match(el.get("text") or "")
                        if match:
                            editor_text = match.group(1)
                            break
            if file_id is None:
                file_id = _canvas_update_file_id(elements)
    if file_id is None or editor_text is None:
        return None
    return {"file_id": file_id, "editor_name": editor_text, "ts": msg["ts"]}


def _extract_canvas_modification_events(
    all_messages: list[dict], channel: str, channel_id: str
) -> dict[str, list[dict]]:
    """Every `tabbed_canvas_updated` system message in one channel's raw
    (unfiltered by export_scope - see sat-811 §8 "cumulative, not window-
    relative") message stream, grouped by the canvas file_id it names.
    Deduped by ts per file (resume cycles duplicate rows, like the FILE
    table itself), sorted ascending. Editor-id resolution happens later,
    once a workspace's profiles are available (see _resolve_canvas_editor)."""
    by_file: dict[str, dict[str, dict]] = {}
    for msg in all_messages:
        parsed = _parse_canvas_update_message(msg)
        if parsed is None:
            continue
        slot = by_file.setdefault(parsed["file_id"], {})
        slot[parsed["ts"]] = {
            "ts": parsed["ts"], "editor_name": parsed["editor_name"], "channel": channel, "channel_id": channel_id,
        }
    return {
        file_id: sorted(events.values(), key=lambda e: float(e["ts"]))
        for file_id, events in by_file.items()
    }


def _resolve_canvas_editor(name: str, profiles: dict[str, dict]) -> tuple[str | None, str | None]:
    """Matches a canvas-update notice's raw editor display string against
    a workspace's roster by normalized real_name. Only ever returns an id
    for an unambiguous single match - "Never guess" (sat-811 §9)."""
    norm = _normalize_name(name)
    matches = [p for p in profiles.values() if _normalize_name(p.get("real_name")) == norm]
    if len(matches) == 1:
        return matches[0]["id"], "high"
    return None, None


def _resolve_canvas_event(event: dict, profiles: dict[str, dict]) -> dict:
    out = {
        "at": _format_utc(float(event["ts"])),
        "editor_name": event["editor_name"],
        "channel": event["channel"],
        "channel_id": event["channel_id"],
        "message_ts": event["ts"],
    }
    # Compound editors ("Daniel Hüsch and Justin Kinney") can't be resolved
    # to one id - splitting them is only for detecting the compound case,
    # never to guess which half made the edit.
    if len(re.split(r"\s+and\s+", event["editor_name"])) == 1:
        uid, confidence = _resolve_canvas_editor(event["editor_name"], profiles)
        if uid is not None:
            out["editor_user_id"] = uid
            out["editor_match_confidence"] = confidence
    return out


def select_messages_in_range(
    all_messages: list[dict],
    users_map: dict[str, str],
    from_epoch: float,
    to_epoch: float,
    channel_dir: Path | None = None,
) -> list[dict]:
    """Like export_month's filtering/nesting, but range-bounded only - no
    calendar-month bucketing, since a digest spans multiple months in one
    document. channel_dir, when given, lets _clean() resolve message-attached
    files[] to their downloaded blob (local_path) - optional since not every
    caller has an archive on disk (e.g. tests exercising nesting/range logic
    in isolation)."""
    by_thread: dict[str, list[dict]] = {}
    for msg in all_messages:
        if _is_parent(msg):
            continue
        by_thread.setdefault(msg["thread_ts"], []).append(msg)
    for thread_ts, replies in by_thread.items():
        by_thread[thread_ts] = [
            _clean(m, users_map, evidence=True, channel_dir=channel_dir)
            for m in sorted(replies, key=lambda m: float(m["ts"]))
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
        cleaned = _clean(msg, users_map, evidence=True, channel_dir=channel_dir)
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


def _format_local_pacific(epoch: float) -> str:
    tz = ZoneInfo("America/Los_Angeles")
    return datetime.fromtimestamp(epoch, tz=tz).isoformat()


def _enrich_for_digest(msg: dict, workspace: str, channel: str, channel_id: str, parent_ts: str | None = None) -> None:
    msg["workspace"] = workspace
    msg["channel"] = channel
    msg["channel_id"] = channel_id
    msg["message_url"] = digest_message_url(workspace, channel_id, msg["ts"])
    msg["posted_at_local"] = _format_local_pacific(float(msg["ts"]))
    if parent_ts is not None:
        msg["thread_ts"] = parent_ts
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
            _enrich_for_digest(reply, workspace, channel, channel_id, parent_ts=msg["ts"])


def _assign_digest_seq(cleaned: list[dict]) -> None:
    """Assigns a per-channel monotonic `seq` (1..N) to every record - each
    root plus every nested reply - in true post-time order, so a downstream
    LLM can flatten a channel's thread nesting back into the chronological
    order it actually happened in (a reply posted after a later root sorts
    after that root). Mutates the dicts in place; nesting itself is
    untouched. Ties broken by the ts string itself since float(ts) can't
    distinguish Slack ts values that differ only past float precision."""
    flat = list(cleaned)
    for msg in cleaned:
        flat.extend(msg.get("replies", ()))
    flat.sort(key=lambda m: (float(m["ts"]), m["ts"]))
    for seq, msg in enumerate(flat, start=1):
        msg["seq"] = seq


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


def _collect_referenced_ids(cleaned_messages: list[dict], creator: str | None, files: list[dict]) -> set[str]:
    """Every user id actually referenced in one channel's digest slice:
    message/reply authors, mentions, reactions users, the channel creator,
    and file creators - the bounded set user_index is built from, not the
    full workspace roster."""
    ids: set[str] = set()
    if creator:
        ids.add(creator)
    for f in files:
        if f.get("creator"):
            ids.add(f["creator"])

    def _walk(msg: dict) -> None:
        uid = msg.get("user")
        if uid:
            ids.add(uid)
        for mention in msg.get("mentions", ()):
            ids.add(mention)
        for reaction in msg.get("reactions", ()):
            for ruser in reaction.get("users") or ():
                ids.add(ruser)
        for reply in msg.get("replies", ()):
            _walk(reply)

    for msg in cleaned_messages:
        _walk(msg)
    return ids


def _build_user_index(profiles_doc: dict, referenced_ids_by_workspace: dict[str, set[str]]) -> dict:
    """Per-workspace {user_id: {display_name, is_bot}}, scoped to ids
    actually referenced somewhere in that workspace's digest slice -
    intentionally not a cross-workspace merged identity table (see
    build_digest's docstring) and not the full roster."""
    profiles_by_workspace = {
        ws_entry["workspace"]: {p["id"]: p for p in ws_entry["profiles"]}
        for ws_entry in profiles_doc["workspaces"]
        if ws_entry["status"] == "ok"
    }
    index: dict[str, dict] = {}
    for workspace, ids in referenced_ids_by_workspace.items():
        profiles = profiles_by_workspace.get(workspace, {})
        entries = {}
        for uid in sorted(ids):
            profile = profiles.get(uid)
            if profile is None:
                continue
            display_name = profile["display_name"] or profile["real_name"] or profile["name"] or profile["id"]
            entries[uid] = {"display_name": display_name, "is_bot": "bot" in profile["slack_roles"]}
        if entries:
            index[workspace] = entries
    return index


# --- cross-workspace mention index (slack-llm-digest-v3 "mentions" key).
# Inverted index keyed by canonical F3 name answering "where is this PAX
# mentioned" without duplicating message bodies or URLs: only message ts,
# grouped workspace -> channel; counts, first/last dates, and Slack links
# are all derivable downstream (ts + channel_id + workspace suffice).
# Deterministic identity unification only - email_hash match, or normalized
# F3-name match with real-name/username support; conflicting evidence is
# never merged, just flagged ambiguous. Everything heuristic beyond that
# stays with the downstream LLM, per ADR-0003. ---


_MATCH_CONFIDENCE_RANK = {"medium": 0, "high": 1}


def _normalize_name(name: str | None) -> str | None:
    """Folds case, spaces, punctuation, and hyphens so simple variants of
    the same F3 name ("Bus Boy" / "bus-boy" / "BusBoy") compare equal."""
    if not name:
        return None
    return re.sub(r"[^a-z0-9]", "", name.lower()) or None


def _match_alias(profile: dict) -> str:
    """Raw display form recorded in the index's aliases list."""
    return profile.get("display_name") or profile.get("real_name") or profile.get("name") or profile["id"]


def _match_name(profile: dict) -> str:
    """Canonical-name candidate used as the matching key: the handler's
    parsed F3 name when present (strips role suffixes like "Pure LEAD" ->
    "Pure"), else the same display-form fallback chain as the alias."""
    derived = profile.get("derived_leadership") or {}
    return derived.get("possible_f3_name") or _match_alias(profile)


def _identity_conflict(a: dict, b: dict) -> bool:
    """Same name but demonstrably different people: both accounts carry an
    email hash and they differ, AND both carry a real name and those differ
    too. Either signal alone is not a conflict (one PAX may use different
    emails per workspace)."""
    a_email, b_email = a.get("email_hash"), b.get("email_hash")
    a_real, b_real = _normalize_name(a.get("real_name")), _normalize_name(b.get("real_name"))
    return bool(a_email and b_email and a_email != b_email and a_real and b_real and a_real != b_real)


def build_mentions_index(messages: list[dict], profiles_doc: dict) -> dict:
    """Digest post-pass: walks the final merged messages (roots and nested
    replies alike, each already carrying workspace/channel/channel_id/ts and
    the extracted per-message mentions[]) and inverts them into per-PAX
    mention locations. Scoped to users actually mentioned in this digest;
    a mentioned id with no roster profile still gets an entry keyed by its
    raw id with match_confidence "unknown" rather than vanishing."""
    profiles_by_workspace = {
        ws_entry["workspace"]: {p["id"]: p for p in ws_entry["profiles"]}
        for ws_entry in profiles_doc["workspaces"]
        if ws_entry["status"] == "ok"
    }

    # (workspace, uid) -> {channel_id: {"name": ..., "ts": [float-sortable ts]}}
    occurrences: dict[tuple[str, str], dict[str, dict]] = {}

    def _record(msg: dict) -> None:
        for uid in msg.get("mentions", ()):
            channels = occurrences.setdefault((msg["workspace"], uid), {})
            slot = channels.setdefault(msg["channel_id"], {"name": msg["channel"], "ts": []})
            slot["ts"].append(msg["ts"])
        for reply in msg.get("replies", ()):
            _record(reply)

    for msg in messages:
        _record(msg)

    accounts = sorted(occurrences)
    profile_of = {
        acct: (profiles_by_workspace.get(acct[0], {}).get(acct[1])) for acct in accounts
    }

    # Union-find clustering over mentioned accounts using deterministic
    # evidence only; cluster confidence is the weakest edge that formed it.
    parent = {acct: acct for acct in accounts}
    confidence: dict[tuple[str, str], str] = {acct: "high" for acct in accounts}

    def _find(acct):
        while parent[acct] != acct:
            parent[acct] = parent[parent[acct]]
            acct = parent[acct]
        return acct

    def _union(a, b, level: str) -> None:
        ra, rb = _find(a), _find(b)
        if ra == rb:
            if _MATCH_CONFIDENCE_RANK[level] > _MATCH_CONFIDENCE_RANK[confidence[ra]]:
                confidence[ra] = level
            return
        parent[rb] = ra
        confidence[ra] = min(
            (confidence[ra], confidence[rb], level), key=_MATCH_CONFIDENCE_RANK.__getitem__
        )

    for i, a in enumerate(accounts):
        pa = profile_of[a]
        if pa is None:
            continue
        for b in accounts[i + 1:]:
            pb = profile_of[b]
            if pb is None:
                continue
            a_email, b_email = pa.get("email_hash"), pb.get("email_hash")
            if a_email and a_email == b_email:
                _union(a, b, "high")
                continue
            if _normalize_name(_match_name(pa)) == _normalize_name(_match_name(pb)):
                if _identity_conflict(pa, pb):
                    continue
                support = (
                    (_normalize_name(pa.get("real_name")) and
                     _normalize_name(pa.get("real_name")) == _normalize_name(pb.get("real_name")))
                    or (_normalize_name(pa.get("name")) and
                        _normalize_name(pa.get("name")) == _normalize_name(pb.get("name")))
                )
                _union(a, b, "high" if support else "medium")

    clusters: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for acct in accounts:
        clusters.setdefault(_find(acct), []).append(acct)

    def _cluster_body(members: list[tuple[str, str]]) -> dict:
        aliases = sorted({
            _match_alias(profile_of[m]) if profile_of[m] else m[1] for m in members
        })
        workspaces: dict[str, dict] = {}
        for workspace, uid in members:
            for channel_id, slot in occurrences[(workspace, uid)].items():
                channels = workspaces.setdefault(workspace, {"channels": {}})["channels"]
                merged = channels.setdefault(channel_id, {"name": slot["name"], "message_ts": []})
                merged["message_ts"].extend(slot["ts"])
        for ws_entry in workspaces.values():
            for channel in ws_entry["channels"].values():
                channel["message_ts"] = sorted(set(channel["message_ts"]), key=float)
        return {
            "aliases": aliases,
            "accounts": [list(m) for m in sorted(members)],
            "workspaces": workspaces,
        }

    def _cluster_key(members: list[tuple[str, str]]) -> str:
        names = sorted({
            _match_name(profile_of[m]) if profile_of[m] else m[1] for m in members
        })
        return names[0]

    # Distinct clusters left sharing a normalized name are exactly the
    # conflict cases - emit them under one key, unmerged, flagged.
    by_key: dict[str, list[tuple[str, list]]] = {}
    for root, members in clusters.items():
        key = _cluster_key(members)
        norm = _normalize_name(key) or key
        by_key.setdefault(norm, []).append((key, members))

    index: dict[str, dict] = {}
    for group in by_key.values():
        if len(group) == 1:
            key, members = group[0]
            body = _cluster_body(members)
            level = confidence[_find(members[0])]
            body["match_confidence"] = level if all(profile_of[m] for m in members) else "unknown"
            index[key] = body
        else:
            key = sorted(k for k, _ in group)[0]
            identities = [
                _cluster_body(members) for _, members in sorted(group, key=lambda g: sorted(g[1]))
            ]
            index[key] = {
                "aliases": sorted({alias for ident in identities for alias in ident["aliases"]}),
                "match_confidence": "ambiguous",
                "identities": identities,
            }

    return dict(sorted(index.items()))


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


def _gather_digest_data(
    channels_file: Path,
    archive_root: Path,
    workspace_glob: str,
    days: int | None,
    as_of: str,
    convert_fn: Callable[[Path, Path], None],
    catalog_cache_dir: Path,
    handler,
    profiles_doc: dict | None,
    files_out_sink: list[dict] | None = None,
) -> tuple[list[dict], list[dict], dict[str, set[str]], dict, tuple[str | None, str]]:
    """Shared first phase of build_digest/build_monthly_digests: reads
    every (workspace, channel) in `channels_file` matching `workspace_glob`,
    converts each channel's archive (via `convert_fn`), and returns the raw
    ingredients an assembly pass needs - per-channel base metadata (no
    activity counts yet, since those depend on which message slice is being
    assembled), the full range-bounded/thread-nested message list, each
    workspace's bot-id set, the profiles doc, and the resolved
    (date_from, date_to) range. A channel with no archive on disk is
    recorded with status "missing_archive" and skipped - one un-archived
    channel must not abort a digest spanning many workspaces.

    `files_out_sink`, when given, is appended to in place with one full
    per-file entry (content, content_sha256, archive_status,
    modification_history, ...) per channel file - the raw ingredients for
    the files_out sidecar (sat-811 §3/§8/§9). The digest's own
    channels_meta only ever gets the content-stripped view
    (_digest_file_view) regardless of whether a sink was given."""
    date_from, date_to = trailing_days_range(days, as_of)
    from_epoch = _date_epoch(date_from, "00:00:00") if date_from else 0.0
    to_epoch = _date_epoch(date_to, "23:59:59")

    # Built up front because per-channel activity needs each workspace's
    # bot-id set to tell a bot/log channel apart from a human one - is_bot
    # is on the user roster, not on the cleaned message, and a bot
    # frequently posts as an ordinary "U..." user account rather than via
    # Slack's legacy bot_id field, so a bot_id-prefix check alone misses it
    # (see SlackBackup follow-up: the f3kirkland nation_bot_logs bot posts
    # as user U0A3GF12LEA).
    if profiles_doc is None:
        profiles_doc = build_user_profiles(channels_file, archive_root, workspace_glob, convert_fn, handler=handler)
    bot_ids_by_workspace: dict[str, set[str]] = {
        ws_entry["workspace"]: {p["id"] for p in ws_entry["profiles"] if "bot" in p["slack_roles"]}
        for ws_entry in profiles_doc["workspaces"]
        if ws_entry["status"] == "ok"
    }
    # For canvas-editor resolution (sat-811 §9) - same shape as the
    # analogous per-workspace profile lookups elsewhere in this module
    # (_build_user_index, build_mentions_index).
    profiles_by_workspace: dict[str, dict[str, dict]] = {
        ws_entry["workspace"]: {p["id"]: p for p in ws_entry["profiles"]}
        for ws_entry in profiles_doc["workspaces"]
        if ws_entry["status"] == "ok"
    }

    channels_meta: list[dict] = []
    messages: list[dict] = []

    catalog_cache: dict[str, dict] = {}

    entries = select_channels(channels_file, workspace_glob)
    for i, entry in enumerate(entries, 1):
        workspace, channel, channel_id = entry["workspace"], entry["name"], entry["id"]
        # Debug SlackBackup nightly hang (2026-08-04/05, see sat-811): this
        # loop shells out to `slackdump convert` once per channel with no
        # other output in between, so a stall or OOM kill here is otherwise
        # invisible in nightly.log until the whole job silently never
        # finishes. Cheap enough to leave in permanently.
        print(f"export digest: converting {workspace}/{channel} [{i}/{len(entries)}]", file=sys.stderr, flush=True)
        if workspace not in catalog_cache:
            catalog_cache[workspace] = catalog_logic.load(catalog_cache_dir, workspace)
        channel_info = _channel_context(catalog_cache[workspace], channel_id)

        channel_dir = archive_root / workspace / channel
        if not (channel_dir / "slackdump.sqlite").exists():
            channels_meta.append(
                {
                    "workspace": workspace, "channel": channel, "channel_id": channel_id,
                    "status": "missing_archive", "channel_url": digest_channel_url(workspace, channel_id),
                    "files": [], **channel_info,
                }
            )
            continue

        with tempfile.TemporaryDirectory() as export_dir:
            export_dir_path = Path(export_dir)
            convert_fn(channel_dir, export_dir_path)
            all_messages = _load_all_messages(export_dir_path)
            users_map = _load_users_map(export_dir_path)

        # Canvas edit history (sat-811 §9) is read from the whole raw
        # stream, not the range-filtered slice below - it's cumulative like
        # the files_out sidecar itself, not export_scope-bounded. Then the
        # notices are stripped before range-filtering/counting: they carry
        # no text, their author is always USLACKBOT, and left in they
        # inflate root_message_count/participant_count for a bot account
        # (see §9's "currently corrupt activity counts").
        canvas_events_by_file = _extract_canvas_modification_events(all_messages, channel, channel_id)
        all_messages = [m for m in all_messages if m.get("subtype") != "tabbed_canvas_updated"]

        cleaned = select_messages_in_range(all_messages, users_map, from_epoch, to_epoch, channel_dir=channel_dir)
        for msg in cleaned:
            _enrich_for_digest(msg, workspace, channel, channel_id)
        _assign_digest_seq(cleaned)
        messages.extend(cleaned)
        files_full = _load_channel_files(channel_dir)
        if files_out_sink is not None:
            profiles = profiles_by_workspace.get(workspace, {})
            for f in files_full:
                entry = {**f, "workspace": workspace, "channel": channel, "channel_id": channel_id}
                events = canvas_events_by_file.get(f["id"], [])
                if events:
                    entry["modification_history"] = [_resolve_canvas_event(e, profiles) for e in events]
                if _is_canvas_file(f):
                    entry.setdefault("modification_history", [])
                    entry["modification_history_completeness"] = "partial"
                files_out_sink.append(entry)
        channels_meta.append(
            {
                "workspace": workspace, "channel": channel, "channel_id": channel_id,
                "status": "ok", "channel_url": digest_channel_url(workspace, channel_id),
                "files": [_digest_file_view(f) for f in files_full], **channel_info,
            }
        )

    messages.sort(key=lambda m: float(m["ts"]))
    return channels_meta, messages, bot_ids_by_workspace, profiles_doc, (date_from, date_to)


def _channels_for_slice(
    channels_meta_base: list[dict], messages_slice: list[dict], bot_ids_by_workspace: dict[str, set[str]]
) -> tuple[list[dict], dict[tuple, dict]]:
    """Recomputes activity counts against just `messages_slice` (a full
    digest's whole message list, or one month's bucket - see
    partition_messages_by_month) and merges them onto each "ok" channel's
    base metadata; "missing_archive" entries pass through unchanged. Also
    returns the raw per-channel activity dicts (including the "_"-prefixed
    aggregation-only fields), keyed by (workspace, channel_id), for
    _build_workspace_activity_index."""
    by_key: dict[tuple, list[dict]] = {}
    for msg in messages_slice:
        by_key.setdefault((msg["workspace"], msg["channel_id"]), []).append(msg)

    channels_out: list[dict] = []
    activity_by_channel: dict[tuple, dict] = {}
    for meta in channels_meta_base:
        if meta["status"] != "ok":
            channels_out.append(meta)
            continue
        key = (meta["workspace"], meta["channel_id"])
        activity = _channel_activity(by_key.get(key, []), bot_ids_by_workspace.get(meta["workspace"], set()))
        activity_by_channel[key] = activity
        activity_fields = {k: v for k, v in activity.items() if not k.startswith("_")}
        channels_out.append({**meta, **activity_fields})
    return channels_out, activity_by_channel


def _referenced_ids_for_slice(
    channels_meta_base: list[dict], messages_slice: list[dict]
) -> dict[str, set[str]]:
    """Like build_digest's original per-channel _collect_referenced_ids
    accumulation, but driven off an already-merged/enriched message slice
    (any subset of the full digest's messages, e.g. one month's bucket)
    instead of per-channel raw cleaned messages. Files are channel-level
    metadata with no natural month, so a file's creator is folded into
    every slice that includes its channel rather than being split by the
    file's own created_at."""
    creator_by_key = {
        (m["workspace"], m["channel_id"]): m.get("creator") for m in channels_meta_base if m["status"] == "ok"
    }
    files_by_key = {
        (m["workspace"], m["channel_id"]): m.get("files", []) for m in channels_meta_base if m["status"] == "ok"
    }
    msgs_by_key: dict[tuple, list[dict]] = {}
    for msg in messages_slice:
        msgs_by_key.setdefault((msg["workspace"], msg["channel_id"]), []).append(msg)

    referenced_ids_by_workspace: dict[str, set[str]] = {}
    for key, msgs in msgs_by_key.items():
        workspace = key[0]
        ids = _collect_referenced_ids(msgs, creator_by_key.get(key), files_by_key.get(key, []))
        referenced_ids_by_workspace.setdefault(workspace, set()).update(ids)
    return referenced_ids_by_workspace


def _root_month(msg: dict) -> str:
    return _format_month(float(msg["ts"]))


def partition_messages_by_month(messages: list[dict]) -> dict[str, list[dict]]:
    """Splits a digest's top-level (thread-nested) message list into
    per-month buckets keyed by each root message's own month - a reply
    stays nested under its parent regardless of what month the reply
    itself landed in, so it is bucketed with its thread's parent, not its
    own ts. A root flagged in_scope: false (parent predates export_scope,
    kept only so its in-range reply has somewhere to nest - see
    select_messages_in_range) still buckets by its own ts, which may put
    it in a month outside export_scope entirely."""
    buckets: dict[str, list[dict]] = {}
    for msg in messages:
        buckets.setdefault(_root_month(msg), []).append(msg)
    return buckets


def merge_files_out(
    entries: list[dict], previous_sidecar: dict | None, generated_at: str
) -> dict:
    """Builds the cumulative files_out sidecar document (sat-811 §8) from
    this run's raw per-file entries (as collected via build_digest's/
    build_monthly_digests' `files_out_sink`) plus the previous sidecar
    snapshot, if any. Cumulative, not window-relative - like
    _load_channel_files itself, this reflects "what documents currently
    exist in this region", not "what changed in export_scope".

    Keyed by (workspace, channel_id, id) across runs:
    - first_seen_at carries forward from the first run a file id appeared
      in, else is stamped with this run's generated_at.
    - content_changed_at is stamped with this run's generated_at only when
      content_sha256 actually differs from the previous snapshot (and
      carried forward unchanged otherwise) - see _load_channel_files for
      why this is the durable signal even when a canvas's
      tabbed_canvas_updated notice was deleted from the channel (sat-811
      §9's "presence is authoritative, absence proves nothing").
    - last_modified_at, when a file carries modification_history, is the
      max of that history's `at` values - the primary currency signal for
      a canvas (sat-811 §8's ranking).
    """
    previous_by_key: dict[tuple, dict] = {
        (f["workspace"], f["channel_id"], f["id"]): f for f in (previous_sidecar or {}).get("files", [])
    }

    files_out: list[dict] = []
    for entry in entries:
        key = (entry["workspace"], entry["channel_id"], entry["id"])
        prev = previous_by_key.get(key)
        first_seen_at = prev["first_seen_at"] if prev is not None else generated_at
        content_changed_at = prev.get("content_changed_at") if prev is not None else None
        if prev is not None and prev.get("content_sha256") != entry.get("content_sha256"):
            content_changed_at = generated_at
        out = {**entry, "first_seen_at": first_seen_at, "content_changed_at": content_changed_at}
        history = entry.get("modification_history")
        if history:
            out["last_modified_at"] = max(h["at"] for h in history)
        files_out.append(out)

    files_out.sort(key=lambda f: (f["workspace"], f["channel_id"], f["id"]))
    return {
        "schema_version": "slack-llm-files-v1",
        "generated_at": generated_at,
        "files": files_out,
    }


def _assemble_digest(
    channels_meta_base: list[dict],
    messages_slice: list[dict],
    profiles_doc: dict,
    handler,
    date_from: str | None,
    date_to: str,
    days: int | None,
    workspace_glob: str,
    bot_ids_by_workspace: dict[str, set[str]],
    month: str | None = None,
) -> dict:
    """Second phase shared by build_digest/build_monthly_digests: turns one
    message slice (the full digest's messages, or one month's bucket) plus
    the gathered channel/profile data into a complete slack-llm-digest-v3
    document. `month`, when given, is stamped onto export_scope so a
    consumer can tell which monthly file this is without parsing the
    filename."""
    channels_out, activity_by_channel = _channels_for_slice(channels_meta_base, messages_slice, bot_ids_by_workspace)
    referenced_ids_by_workspace = _referenced_ids_for_slice(channels_meta_base, messages_slice)

    # Leadership candidates come from the full per-workspace roster
    # (build_user_profiles/profiles_doc), not just this slice's posters -
    # a leader who didn't happen to post in this window (or this month)
    # should still surface. This is the digest's *only* profile data;
    # everyone else in the roster is intentionally left out (see
    # build_user_profiles for the full list). Delegated entirely to
    # `handler` - see its module docstring in handlers/__init__.py; an
    # empty section when no handler is set.
    leadership = (
        handler.build_leadership(profiles_doc)
        if handler is not None
        else {"profile_role_matches": [], "by_region": [], "former_by_region": []}
    )

    export_scope = {"from": date_from, "to": date_to, "days": days, "workspace_glob": workspace_glob}
    if month is not None:
        export_scope["month"] = month

    return {
        "schema_version": "slack-llm-digest-v4",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "export_scope": export_scope,
        "manifest": {
            "workspaces_included": len({c["workspace"] for c in channels_meta_base}),
            "counting_rules": {
                "has_content": (
                    "v4: a channel file's extracted text moved out of this document into a "
                    "companion files_out sidecar (same job, same as_of) - join on (workspace, "
                    "channel_id, id). has_content: false means no text was ever extractable for "
                    "this file (see the sidecar's archive_status), not that the sidecar is missing. "
                    "tabbed_canvas_updated system messages (Slack's 'X made updates to a canvas "
                    "tab' notices) are also stripped from messages[] in v4 and no longer inflate "
                    "root_message_count/participant_count for the USLACKBOT account; see the "
                    "sidecar's per-file modification_history for the edit events they carried."
                ),
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
                "seq": (
                    "per-channel (not global) monotonic integer, 1..N, assigned by sorting that "
                    "channel's emitted records - every root plus every nested reply - ascending by "
                    "true post time (float(ts)); sorting a channel's records by seq is equivalent to "
                    "sorting the flattened set by ts. Lets a reply posted after a later root be placed "
                    "after that root in the true timeline despite being nested under its own thread. "
                    "No gaps; a record outside export_scope is simply not present, so not numbered."
                ),
                "mentions": (
                    "user ids parsed from <@U...> tokens in a message's text, in order of first "
                    "appearance, deduped; the key is omitted when the text has no mentions. text "
                    "itself is never modified - always the raw, unresolved Slack token."
                ),
                "links": (
                    "Slack angle-bracket link tokens (<url> / <url|label>) parsed from a message's "
                    "text, omitted when none are present; label is null for a bare url. type is "
                    "slack_message (with target_channel_id/target_ts) for a slack.com/archives/... "
                    "message link, slack_file for a slack.com/docs/ or slack.com/files/ link, else "
                    "external."
                ),
                "user_index": (
                    "top-level {workspace: {user_id: {display_name, is_bot}}}, scoped to ids actually "
                    "referenced somewhere in that workspace's slice of this digest (message/reply "
                    "authors, mentions, reactions users, channel creators, file creators) - not the "
                    "full roster, and never merged across workspaces (a shared user id in two "
                    "workspaces gets two separate entries, one per workspace)."
                ),
                "posted_at_local": (
                    "DST-aware America/Los_Angeles wall-clock timestamp, ISO-8601 with UTC offset. "
                    "Replaces v2's posted_at_utc; UTC is derivable from either the offset in this "
                    "value or the message's ts epoch."
                ),
                "mentions_index": (
                    "top-level mentions key: inverted index keyed by canonical F3 name over users "
                    "actually mentioned in this digest. Per entry: aliases (raw display forms), "
                    "accounts ([workspace, user_id] pairs - ids stay workspace-local), "
                    "match_confidence (high: email or name+real-name/username evidence; medium: "
                    "name match only; unknown: no roster profile; ambiguous: same name, conflicting "
                    "evidence - identities[] lists the unmerged clusters, never pooled), and "
                    "workspaces -> channels -> message_ts (ascending ts only; counts, first/last "
                    "dates, and Slack URLs are derived from ts + channel_id + workspace, never "
                    "duplicated here). Message text/URLs are never stored in the index."
                ),
            },
            "known_limitations": [
                "Private or inaccessible channels may be absent",
                "User profile completeness depends on Slack profile data",
                "Leadership roles may be inferred from display names unless explicitly confirmed",
            ],
        },
        "channels": channels_out,
        "workspace_activity_index": _build_workspace_activity_index(channels_out, activity_by_channel),
        "messages": messages_slice,
        "user_index": _build_user_index(profiles_doc, referenced_ids_by_workspace),
        "mentions": build_mentions_index(messages_slice, profiles_doc),
        "leadership": leadership,
    }


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
    files_out_sink: list[dict] | None = None,
) -> dict:
    """Merges messages from the trailing `days` days (or everything ever
    archived, when `days` is None) across every (workspace, channel) in
    `channels_file` matching `workspace_glob` into one chronologically-
    sorted slack-llm-digest-v4 document. See _gather_digest_data and
    _assemble_digest for the two phases this composes; see
    build_monthly_digests for the equivalent split into one document per
    calendar month.

    Has a top-level `user_index` section, but it is per-workspace (keyed by
    workspace name, never merged): the same Slack user id in two different
    workspaces is not the same identity, so an id is looked up only within
    its own workspace's profiles and never crosses workspace boundaries. It
    is also bounded to ids actually referenced somewhere in that workspace's
    digest slice (authors, mentions, reactions, channel creators, file
    creators) - not the full roster. Author info itself still stays
    embedded per-message, exactly as `_clean()` already resolves it.

    Each "ok" channel's entry also carries its files/Canvases (images
    included, see _load_channel_files) - read directly from the channel's own
    archive, not via convert_fn, since an unattached channel Canvas never
    surfaces in a message-anchored export. v4 drops each file's extracted
    `content` from this view (has_content only) - pass `files_out_sink` to
    also collect the full per-file entries (content included) for the
    companion files_out sidecar; see merge_files_out.

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
    channels_meta, messages, bot_ids_by_workspace, profiles_doc, (date_from, date_to) = _gather_digest_data(
        channels_file, archive_root, workspace_glob, days, as_of, convert_fn, catalog_cache_dir, handler, profiles_doc,
        files_out_sink=files_out_sink,
    )
    return _assemble_digest(
        channels_meta, messages, profiles_doc, handler, date_from, date_to, days, workspace_glob, bot_ids_by_workspace,
    )


def build_monthly_digests(
    channels_file: Path,
    archive_root: Path,
    workspace_glob: str,
    days: int | None,
    as_of: str,
    convert_fn: Callable[[Path, Path], None],
    catalog_cache_dir: Path = catalog_logic.DEFAULT_CACHE_DIR,
    handler=_default_handler,
    profiles_doc: dict | None = None,
    files_out_sink: list[dict] | None = None,
) -> dict[str, dict]:
    """Same data and same slack-llm-digest-v4 schema as build_digest, but
    split into one document per calendar month (keyed "YYYY-MM") instead of
    one merged document. A thread's replies stay with their parent's
    month even when a reply itself lands in a later month - see
    partition_messages_by_month - so a month's file is never missing a
    reply that belongs to a thread it started. Each month's channel/
    workspace_activity_index/user_index/mentions are recomputed against
    just that month's message slice; "leadership" is unchanged across
    months (it reflects current roster roles, not activity). files_out_sink
    is collected once by the shared gather phase, not per month - a file
    has no natural month (see build_digest)."""
    channels_meta, messages, bot_ids_by_workspace, profiles_doc, (date_from, date_to) = _gather_digest_data(
        channels_file, archive_root, workspace_glob, days, as_of, convert_fn, catalog_cache_dir, handler, profiles_doc,
        files_out_sink=files_out_sink,
    )
    buckets = partition_messages_by_month(messages)
    return {
        month: _assemble_digest(
            channels_meta, month_messages, profiles_doc, handler, date_from, date_to, days, workspace_glob,
            bot_ids_by_workspace, month=month,
        )
        for month, month_messages in sorted(buckets.items())
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
    noise-stripping philosophy as _clean() for messages. email_hash is the
    one exception to the email drop: a truncated one-way digest kept solely
    so the mentions index can match the same person across workspaces
    deterministically - the raw address is never persisted anywhere."""
    profile = user.get("profile") or {}
    email = profile.get("email")
    return {
        "id": user["id"],
        "name": user.get("name"),
        "real_name": user.get("real_name"),
        "display_name": profile.get("display_name") or None,
        "title": profile.get("title") or None,
        "deleted": user.get("deleted", False),
        "slack_roles": _slack_roles(user),
        "email_hash": hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12] if email else None,
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
