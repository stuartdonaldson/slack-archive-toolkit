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
import tempfile
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

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


def derive_leadership(display_name: str | None) -> dict | None:
    """Display names are visible and self-correcting, so they're a
    practical working signal for "who currently holds this role" even
    without a maintained roster - but they're never confirmation. Returns
    None for the common case (no known title keyword present). basis is
    always "display_name" and needs_confirmation always True here: this
    function has no maintained-reference signal to upgrade either field -
    that would be a different basis this digest does not have access to.
    """
    if not display_name:
        return None

    matched_titles = _match_titles(display_name)
    if not matched_titles:
        return None

    possible_f3_name, structured = _split_possible_name(display_name)
    confidence = "medium_high" if structured else "medium"

    matched_region = next(
        (region for region in _REGION_NAMES.values() if region.lower() in display_name.lower()),
        None,
    )

    return {
        "possible_f3_name": possible_f3_name,
        "possible_region": f"F3 {matched_region}" if matched_region else None,
        "possible_roles": [
            {"position": title, "basis": "display_name", "confidence": confidence, "needs_confirmation": True}
            for title in matched_titles
        ],
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
        region = derived["possible_region"] or "Unknown"
        f3_name = derived["possible_f3_name"]
        for role in derived["possible_roles"]:
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
        {"region": region, "roles": sorted(by_region[region], key=lambda r: (r["position"], r["f3_name"]))}
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


def _enrich_for_digest(msg: dict, workspace: str, channel: str, channel_id: str) -> None:
    msg["workspace"] = workspace
    msg["channel"] = channel
    msg["channel_id"] = channel_id
    msg["message_url"] = digest_message_url(workspace, channel_id, msg["ts"])
    msg["posted_at_utc"] = datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    for reply in msg.get("replies", ()):
        _enrich_for_digest(reply, workspace, channel, channel_id)


def build_digest(
    channels_file: Path,
    archive_root: Path,
    workspace_glob: str,
    months: int,
    as_of: str,
    convert_fn: Callable[[Path, Path], None],
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
    """
    date_from, date_to = trailing_months_range(months, as_of)
    from_epoch = _date_epoch(date_from, "00:00:00")
    to_epoch = _date_epoch(date_to, "23:59:59")

    channels_meta: list[dict] = []
    messages: list[dict] = []

    for entry in select_channels(channels_file, workspace_glob):
        workspace, channel, channel_id = entry["workspace"], entry["name"], entry["id"]
        channel_dir = archive_root / workspace / channel
        if not (channel_dir / "slackdump.sqlite").exists():
            channels_meta.append(
                {"workspace": workspace, "channel": channel, "channel_id": channel_id, "status": "missing_archive"}
            )
            continue

        with tempfile.TemporaryDirectory() as export_dir:
            export_dir_path = Path(export_dir)
            convert_fn(channel_dir, export_dir_path)
            all_messages = _load_all_messages(export_dir_path)
            users_map = _load_users_map(export_dir_path)

        cleaned = select_messages_in_range(all_messages, users_map, from_epoch, to_epoch)
        for msg in cleaned:
            _enrich_for_digest(msg, workspace, channel, channel_id)
        messages.extend(cleaned)
        channels_meta.append(
            {"workspace": workspace, "channel": channel, "channel_id": channel_id, "status": "ok"}
        )

    messages.sort(key=lambda m: float(m["ts"]))

    # Leadership candidates: scanned from the full per-workspace roster
    # (build_user_profiles), not just this digest's posters - a leader who
    # didn't happen to post in this window should still surface. This is
    # the digest's *only* profile data; everyone else in the roster is
    # intentionally left out (see build_user_profiles for the full list).
    leadership: list[dict] = []
    profiles_doc = build_user_profiles(channels_file, archive_root, workspace_glob, convert_fn)
    for ws_entry in profiles_doc["workspaces"]:
        if ws_entry["status"] != "ok":
            continue
        for profile in ws_entry["profiles"]:
            signal = derive_leadership(profile["display_name"])
            if signal is None:
                continue
            leadership.append(
                {
                    "id": profile["id"],
                    "workspace": ws_entry["workspace"],
                    "display_name": profile["display_name"],
                    "real_name": profile["real_name"],
                    "is_bot": profile["is_bot"],
                    "derived": signal,
                }
            )

    return {
        "schema_version": "slack-llm-digest-v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "export_scope": {"from": date_from, "to": date_to, "months": months, "workspace_glob": workspace_glob},
        "channels": channels_meta,
        "messages": messages,
        "leadership": {
            "raw_profile_matches": leadership,
            "by_region": _build_leadership_by_region(leadership),
        },
    }


# --- user profiles: the full per-workspace roster (everyone slackdump has
# cached, not just digest posters), kept as a separate document since
# profile identity does not carry across workspaces - see build_digest's
# docstring. ---


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
        "is_bot": user.get("is_bot", False),
        "deleted": user.get("deleted", False),
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
