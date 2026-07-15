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
import json
import re
import sqlite3
import tempfile
from calendar import monthrange
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, AbstractSet

from . import catalog_logic

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


# --- digest: one merged document spanning the trailing N months across every
# workspace matching a glob, separate from the per-channel-month exporter
# above (different schema, different purpose - see docs/llm-export-suggestion.md). ---


def select_channels(channels_file: Path, workspace_glob: str = "f3*") -> list[dict]:
    entries = json.loads(channels_file.read_text())
    return [e for e in entries if fnmatch.fnmatch(e["workspace"], workspace_glob)]


def trailing_months_range(months: int, as_of: str) -> tuple[str, str]:
    """`months` calendar months ending at `as_of`: from = the 1st of the
    month (months - 1) before as_of's month; to = as_of itself."""
    year, mon = (int(part) for part in as_of[:7].split("-"))
    total = year * 12 + (mon - 1) - (months - 1)
    from_year, from_mon = divmod(total, 12)
    return f"{from_year}-{from_mon + 1:02d}-01", as_of


def digest_message_url(workspace: str, channel_id: str, ts: str) -> str:
    return f"https://{workspace}.slack.com/archives/{channel_id}/p{ts.replace('.', '')}"


def generate_calendar_reference(date_from_str: str, date_to_str: str) -> dict[str, str]:
    """Generates a dict mapping 'YYYY-MM-DD' to 'DayOfWeek' for every day
    between date_from_str and date_to_str (inclusive) to help the LLM
    avoid date/day-of-week hallucinations.
    """
    fmt = "%Y-%m-%d"
    try:
        start_dt = datetime.strptime(date_from_str, fmt)
        end_dt = datetime.strptime(date_to_str, fmt)
    except ValueError:
        return {}

    reference = {}
    curr = start_dt
    while curr <= end_dt:
        date_str = curr.strftime(fmt)
        day_name = curr.strftime("%A")
        reference[date_str] = day_name
        curr += timedelta(days=1)
    return reference


def derive_channel_category(name: str, description: str | None = None) -> tuple[str, str]:
    name_lower = name.lower()
    desc_lower = (description or "").lower()

    if name_lower.startswith("ao-"):
        return "ao", "channel name starts with ao-"
    elif name_lower.startswith("event-"):
        return "event", "channel name starts with event-"
    elif name_lower == "events":
        return "event", "channel name is events"
    elif name_lower.startswith("all-f3-") or name_lower == "all-events" or name_lower == "all-pax":
        return "all_region", "channel name matches regional all-hands pattern"
    elif name_lower in ("1st-f", "1stf"):
        return "first_f", "channel name is 1st-f"
    elif name_lower in ("2nd-f", "2ndf"):
        return "second_f", "channel name is 2nd-f"
    elif name_lower in ("3rd-f", "3rdf"):
        return "third_f", "channel name is 3rd-f"
    elif name_lower in ("helpdesk", "help"):
        return "helpdesk", "channel name matches help pattern"
    elif name_lower == "mumblechatter":
        return "mumblechatter", "channel name is mumblechatter"
    elif name_lower == "classifieds":
        return "classifieds", "channel name is classifieds"
    elif "nation_bot_logs" in name_lower or "bot-logs" in name_lower:
        return "bot_log", "channel name matches bot log pattern"

    if "workout" in desc_lower or "beatdown" in desc_lower:
        return "ao", "description mentions workout/beatdown"
    if "event" in desc_lower:
        return "event", "description mentions event"
    if "first f" in desc_lower:
        return "first_f", "description mentions first f"
    if "second f" in desc_lower or "social" in desc_lower or "fellowship" in desc_lower:
        return "second_f", "description mentions second f / social / fellowship"
    if "third f" in desc_lower or "faith" in desc_lower or "service" in desc_lower or "study" in desc_lower:
        return "third_f", "description mentions third f / faith / study"

    return "unknown", "no matching patterns in name or description"


def _channel_context(catalog: dict, channel_id: str) -> dict:
    """description/creator/created_at for one channel, read-only from an
    already-loaded catalog cache (no API call, no refresh - the digest
    stays local-only; if the cache was never warmed for this channel, e.g.
    a fresh checkout, these are just None rather than triggering a live
    fetch). created_at is an ISO8601 string, not the raw epoch, matching
    this module's posted_at_utc convention elsewhere."""
    channel = catalog["channels"].get(channel_id, {})
    created = channel.get("created")
    name = channel.get("name") or ""
    desc = channel.get("description") or ""
    category, basis = derive_channel_category(name, desc)
    return {
        "description": channel.get("description") or None,
        "creator": channel.get("creator") or None,
        "created_at": (
            datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if created else None
        ),
        "channel_category": category,
        "channel_category_basis": basis,
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


# --- leadership inference: best-effort, display-name-only signal per
# docs/llm-export-suggestion.md's "profile-inferred roles" proposal, tuned
# per docs/llm-leadership-improvement.md's feedback (dedup, wider role
# coverage, compact-name-region parsing). Extend the two data lists freely
# - they're config, not logic; the patterns list needs a regex if a new
# title doesn't fit \bword\b matching, but most will.

_LEADERSHIP_TITLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Nantan", re.compile(r"nantan", re.I)),
    ("Weasel Shaker", re.compile(r"weasel\s*shaker", re.I)),
    ("1st F", re.compile(r"\b1st\s*f\b|\bfirst\s*f\b", re.I)),
    ("2nd F", re.compile(r"\b2nd\s*f\b|\bsecond\s*f\b", re.I)),
    ("3rd F", re.compile(r"\b3rd\s*f\b|\bthird\s*f\b", re.I)),
    ("Comz", re.compile(r"\bcomz\b|\bcommunications?\b", re.I)),
    ("Site Q", re.compile(r"\bsite[-\s]?q\b", re.I)),
    ("Region Q", re.compile(r"\bregion\s*q\b", re.I)),
    ("AOQ", re.compile(r"\baoq\b|\bao[-\s]q\b", re.I)),
    ("Q Lead", re.compile(r"\bq\s*lead\b", re.I)),
    ("SLT", re.compile(r"\bslt\b|\bshared\s+leadership\s+team\b", re.I)),
    ("OIC", re.compile(r"\boic\b", re.I)),
    ("EH Lead", re.compile(r"\beh\s*lead\b", re.I)),
    ("Fight Lead", re.compile(r"\bfight\s*lead\b", re.I)),
    ("FNG Lead", re.compile(r"\bfng\s*lead\b", re.I)),
    # Bare "Q" last and lowest-confidence signal of the bunch - dropped
    # below when a more specific Q-variant above already matched, so a
    # single mention doesn't produce two redundant role entries.
    ("Q", re.compile(r"\bq\b", re.I)),
]

_SPECIFIC_Q_TITLES = {"Q Lead", "Site Q", "Region Q", "AOQ"}

# Roles scoped to a specific AO/channel rather than the whole region.
# "Redmond Ridge Site Q" → Site Q for the ao-redmond-ridge channel.
_AO_SCOPED_ROLES = {"Site Q", "AOQ", "OIC"}

_REGION_NAMES = {
    "f3pugetsound": "Puget Sound",
    "f3kirkland": "Kirkland",
    "f3cascades": "Cascades",
    "f3tundra": "Tundra",
    "f3redmond": "Redmond",
    "f3seattle": "Seattle",
}

_NAME_SEPARATORS = (" - ", " – ", " — ", "|")
_PAREN_RE = re.compile(r"\s*\(")
_COMPACT_HYPHEN_REGION_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_]+)-(?:" + "|".join(re.escape(r) for r in _REGION_NAMES.values()) + r")\b",
    re.I,
)


def _match_titles(display_name: str) -> list[str]:
    matched = [
        canonical
        for canonical, pattern in _LEADERSHIP_TITLE_PATTERNS
        if pattern.search(display_name)
    ]
    if "Q" in matched and any(title in matched for title in _SPECIFIC_Q_TITLES):
        matched.remove("Q")
    return matched


def _split_possible_name(display_name: str) -> tuple[str, bool]:
    """Returns (possible_f3_name, structured) - structured is True when a
    recognized name/region delimiter was found, used to set confidence.
    Handles "<Name> - <Region> Region <Role>", "<Name> (<Region> <Role>)",
    and the compact "<Name>-<Region> Region <Role>" form (no spaces around
    the hyphen) - reported broken for "Montoya-Kirkland Region Nantan"."""
    for sep in _NAME_SEPARATORS:
        if sep in display_name:
            return display_name.split(sep, 1)[0].strip(), True

    paren_match = _PAREN_RE.search(display_name)
    if paren_match:
        return display_name[: paren_match.start()].strip(), True

    compact_match = _COMPACT_HYPHEN_REGION_RE.match(display_name)
    if compact_match:
        return compact_match.group("name"), True

    return display_name.strip(), False


def _title_segment_prefix(segment: str, position: str) -> str | None:
    """Text before the role keyword in a title segment — the location part
    of '<Location> <Role>', e.g. 'Redmond Ridge' from 'Redmond Ridge Site Q'."""
    _, pattern = next(((p, r) for p, r in _LEADERSHIP_TITLE_PATTERNS if p == position), (None, None))
    if pattern is None:
        return None
    m = pattern.search(segment)
    return segment[: m.start()].strip() or None if m else None


def _parse_title_segments(title: str) -> list[dict]:
    """Parse a Slack profile title field into per-segment role entries.
    Each comma-separated segment is treated as '<Location> <Role>', e.g.
    'Redmond Ridge Site Q, Redmond Comz Q'. Title is explicitly set so
    these roles carry higher confidence than display-name inference.

    AO-scoped roles (Site Q, AOQ, OIC) emit possible_ao (the AO/channel
    name, e.g. 'Redmond Ridge') alongside possible_region. Regional roles
    emit only possible_region."""
    roles = []
    for segment in re.split(r"\s*,\s*", title):
        segment = segment.strip()
        if not segment:
            continue
        matched = _match_titles(segment)
        if not matched:
            continue
        matched_region = next(
            (region for region in _REGION_NAMES.values() if region.lower() in segment.lower()),
            None,
        )
        for position in matched:
            entry: dict = {
                "position": position,
                "basis": "title",
                "confidence": "high",
                "needs_confirmation": False,
                "possible_region": f"F3 {matched_region}" if matched_region else None,
            }
            if position in _AO_SCOPED_ROLES:
                entry["possible_ao"] = _title_segment_prefix(segment, position)
            roles.append(entry)
    return roles


def derive_leadership(display_name: str | None, title: str | None = None) -> dict | None:
    """Display names and profile titles are both practical working signals
    for "who currently holds this role". Display-name inference is
    best-effort (needs_confirmation=True); title-field roles carry higher
    confidence since the field is set explicitly. Returns None when neither
    source matches any known F3 role pattern."""
    dn_roles: list[dict] = []
    dn_region: str | None = None
    possible_f3_name: str | None = None

    if display_name:
        matched_titles = _match_titles(display_name)
        possible_f3_name, structured = _split_possible_name(display_name)
        if matched_titles:
            confidence = "medium_high" if structured else "medium"
            dn_region = next(
                (region for region in _REGION_NAMES.values() if region.lower() in display_name.lower()),
                None,
            )
            dn_roles = [
                {"position": t, "basis": "display_name", "confidence": confidence, "needs_confirmation": True}
                for t in matched_titles
            ]

    title_roles = _parse_title_segments(title) if title else []

    if not dn_roles and not title_roles:
        return None

    return {
        "possible_f3_name": possible_f3_name,
        "possible_region": f"F3 {dn_region}" if dn_region else None,
        "possible_roles": dn_roles + title_roles,
    }


_CONFIDENCE_RANK = {"medium": 1, "medium_high": 2}


def _build_leadership_by_region(raw_matches: list[dict]) -> list[dict]:
    """Dedupes raw_matches by (region, f3_name, position) - the same
    person commonly has a separate Slack account per workspace, each
    independently matching the same self-reported role; without this, the
    same leader is repeated once per workspace (reported in
    docs/llm-leadership-improvement.md)."""
    groups: dict[tuple[str, str, str], dict] = {}
    for record in raw_matches:
        derived = record["derived"]
        if derived is None:
            # Admin/owner-only entries (no display-name title match) have
            # no role/region to group by - they still appear in
            # profile_role_matches, just not in this rollup.
            continue
        f3_name = derived["possible_f3_name"]
        for role in derived["possible_roles"]:
            region = role.get("possible_region") or derived["possible_region"] or "Unknown"
            key = (region, f3_name, role["position"])
            group = groups.setdefault(
                key, {"workspaces": set(), "display_names": set(), "profile_ids": set(), "confidence": role["confidence"]}
            )
            group["workspaces"].add(record["workspace"])
            group["display_names"].add(record["display_name"])
            group["profile_ids"].add(record["id"])
            if _CONFIDENCE_RANK.get(role["confidence"], 0) > _CONFIDENCE_RANK.get(group["confidence"], 0):
                group["confidence"] = role["confidence"]

    by_region: dict[str, list[dict]] = {}
    for (region, f3_name, position), group in groups.items():
        by_region.setdefault(region, []).append(
            {
                "position": position,
                "f3_name": f3_name,
                "confidence": group["confidence"],
                "basis": "display_name",
                "seen_in_workspaces": sorted(group["workspaces"]),
                "source_display_names": sorted(group["display_names"]),
                "source_profile_ids": sorted(group["profile_ids"]),
                # Always True, deliberately not matching the literal example
                # in docs/llm-leadership-improvement.md: the same self-
                # reported display name repeated across a person's per-
                # workspace accounts is not independent corroboration, so it
                # doesn't earn "confirmed" - basis is still display_name-only.
                "needs_confirmation": True,
            }
        )

    return [
        {"region": region, "roles": sorted(by_region[region], key=lambda r: (r["position"], r["f3_name"] or ""))}
        for region in sorted(by_region)
    ]


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
        if not (from_epoch <= parent_ts <= to_epoch):
            continue
        cleaned = _clean(msg, users_map)
        replies = by_thread.get(msg["ts"])
        if replies:
            cleaned["replies"] = replies
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
    for msg in messages:
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

    root_count = len(messages)
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
    months: int,
    as_of: str,
    convert_fn: Callable[[Path, Path], None],
    catalog_cache_dir: Path = catalog_logic.DEFAULT_CACHE_DIR,
) -> dict:
    """Reads every (workspace, channel) in `channels_file` matching
    `workspace_glob`, converts each channel's archive (via `convert_fn` -
    normally `slackdump.convert_export`, injected so tests can fake it),
    and merges the trailing `months` months of messages into one
    chronologically-sorted document. A channel with no archive on disk is
    recorded with status "missing_archive" and skipped - one un-archived
    channel must not abort a digest spanning many workspaces.

    Deliberately has no top-level merged "users"/"authors" table: the same
    Slack user id (or display name) in two different workspaces is not the
    same identity, so author info stays embedded per-message, scoped to
    that message's own workspace, exactly as `_clean()` already resolves it.

    Each "ok" channel's entry also carries its non-image files/Canvases
    (see _load_channel_files) - read directly from the channel's own
    archive, not via convert_fn, since an unattached channel Canvas never
    surfaces in a message-anchored export.
    """
    date_from, date_to = trailing_months_range(months, as_of)
    from_epoch = _date_epoch(date_from, "00:00:00")
    to_epoch = _date_epoch(date_to, "23:59:59")

    # Built up front (not after the channel loop) because per-channel
    # activity needs each workspace's bot-id set to tell a bot/log channel
    # apart from a human one - is_bot is on the user roster, not on the
    # cleaned message, and a bot frequently posts as an ordinary "U..."
    # user account rather than via Slack's legacy bot_id field, so a
    # bot_id-prefix check alone misses it (see SlackBackup follow-up: the
    # f3kirkland nation_bot_logs bot posts as user U0A3GF12LEA).
    profiles_doc = build_user_profiles(channels_file, archive_root, workspace_glob, convert_fn)
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
                    "is_probably_bot_or_log_channel": (channel_info.get("channel_category") == "bot_log"),
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
        is_bot = (channel_info.get("channel_category") == "bot_log") or (
            activity_fields["total_message_count"] > 0 and activity["_human_total_message_count"] == 0
        )
        channels_meta.append(
            {
                "workspace": workspace, "channel": channel, "channel_id": channel_id,
                "status": "ok", "files": _load_channel_files(channel_dir), **channel_info,
                **activity_fields,
                "is_probably_bot_or_log_channel": is_bot,
            }
        )

    messages.sort(key=lambda m: float(m["ts"]))

    # Leadership candidates: scanned from the full per-workspace roster
    # (build_user_profiles), not just this digest's posters - a leader who
    # didn't happen to post in this window should still surface. This is
    # the digest's *only* profile data; everyone else in the roster is
    # intentionally left out (see build_user_profiles for the full list).
    leadership: list[dict] = []
    for ws_entry in profiles_doc["workspaces"]:
        if ws_entry["status"] != "ok":
            continue
        for profile in ws_entry["profiles"]:
            signal = derive_leadership(profile["display_name"], profile.get("title"))
            # admin/owner/primary_owner is an authoritative Slack-platform
            # role, not an inferred one - include the profile even when its
            # display name doesn't match any F3 title pattern, so a
            # workspace admin/owner is never silently dropped from the
            # leadership list just because derive_leadership() found nothing.
            has_workspace_role = bool({"admin", "owner", "primary_owner"} & set(profile["slack_roles"]))
            if signal is None and not has_workspace_role:
                continue
            leadership.append(
                {
                    "id": profile["id"],
                    "workspace": ws_entry["workspace"],
                    "display_name": profile["display_name"],
                    "real_name": profile["real_name"],
                    "title": profile.get("title"),
                    "slack_roles": profile["slack_roles"],
                    "derived": signal,
                }
            )

    return {
        "schema_version": "slack-llm-digest-v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "export_scope": {"from": date_from, "to": date_to, "months": months, "workspace_glob": workspace_glob},
        "manifest": {
            "workspaces_included": len({c["workspace"] for c in channels_meta}),
            "counting_rules": {
                "root_message_count": "top-level messages only",
                "reply_count": "nested replies under root messages",
                "total_message_count": "root_message_count plus reply_count",
                "activity_status": "active when total_message_count > 0 in export_scope, else inactive",
            },
            "calendar_reference_2026": generate_calendar_reference(date_from, date_to),
            "known_limitations": [
                "Private or inaccessible channels may be absent",
                "User profile completeness depends on Slack profile data",
                "Leadership roles may be inferred from display names unless explicitly confirmed",
            ],
        },
        "channels": channels_meta,
        "workspace_activity_index": _build_workspace_activity_index(channels_meta, activity_by_channel),
        "messages": messages,
        "leadership": {
            "profile_role_matches": leadership,
            "by_region": _build_leadership_by_region(leadership),
        },
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
) -> dict:
    """users.json from `convert -f export` is workspace-scoped, identical
    no matter which of that workspace's channels you convert - so this
    converts just one archived channel per workspace (whichever is
    archived first) to fetch it, rather than every channel."""
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

        workspaces_out.append(
            {"workspace": workspace, "status": "ok", "profiles": [_clean_user(u) for u in raw_users]}
        )

    return {
        "schema_version": "slack-user-profiles-v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace_glob": workspace_glob,
        "workspaces": workspaces_out,
    }
