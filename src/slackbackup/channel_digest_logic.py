#!/usr/bin/env python3
"""General-purpose, on-demand extraction of a workspace's channels into a
single JSON digest of their surviving messages, files, and canvases - for
any channel-name glob pattern, not just tracked channels.

Original motivation: Slack's "move channel to another workspace" migration
moves message history to the destination but does not reliably take a
channel's standalone Canvas with it (see docs/references/slackdump-cli-
notes.md's FILE.MESSAGE_ID note - a channel canvas isn't a reply to
anything, so there's no message for the migration to carry along). f3
regions rename these channels `shuttered-*` and keep them around only for
reference, so anything still findable in them is a leftover the
destination workspace may be missing. That's a specific case of a general
need - pull down whatever's left in some slice of a workspace's channels,
on demand, without adding them to the nightly `channels.json` cadence.
SlackBackup-ie2.

Reuses export_logic's message/file cleaning so the shape here matches a
normal export - this is not a new data model, just a narrower scope.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from . import export_logic, selector_logic

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _sanitize_error(message: str) -> str:
    """Collapses a slackdump CLI error (ANSI color codes, multi-line log
    output) into one plain-text line safe to embed in a markdown table
    cell."""
    stripped = _ANSI_RE.sub("", message)
    return " ".join(stripped.split())


def filter_channels(catalog: dict, pattern: str) -> list[dict]:
    channels = catalog.get("channels", {})
    return sorted(
        (
            {
                "id": cid,
                "name": c["name"],
                "description": c.get("description") or "",
                "is_archived": bool(c.get("is_archived")),
                "member": bool(c.get("member")),
            }
            for cid, c in channels.items()
            if selector_logic.matches_selector(pattern, c.get("name", ""))
        ),
        key=lambda c: c["name"],
    )


def extract_channel(channel_dir: Path, export_dir: Path) -> dict:
    """channel_dir must already hold a freshly `archive`d slackdump.sqlite;
    export_dir must already hold that same archive's `convert -f export`
    output (day-bucketed message JSON + users.json)."""
    users_map = export_logic._load_users_map(export_dir)
    messages = [
        export_logic._clean(m, users_map) for m in export_logic._load_all_messages(export_dir)
    ]
    files = export_logic._load_channel_files(channel_dir)
    for f in files:
        f["creator_name"] = users_map.get(f["creator"]) if f.get("creator") else None
    return {"messages": messages, "files": files}


SCHEMA_VERSION = "slack-channel-digest-v2"

_KNOWN_LIMITATIONS = [
    "Only channels matching the glob pattern in the local catalog cache are scanned - a "
    "stale cache can miss a recently created/renamed channel",
    "Message/file content reflects whatever is still in the channel at scan time - a Slack "
    "channel migration may have already moved most of it elsewhere",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_digest(workspace: str, pattern: str, results: list[dict]) -> dict:
    """results: [{channel: {id,name,description,is_archived,member},
    messages: [...], files: [...], error: str|None}]

    JSON, not markdown - schema_version'd like export_logic.build_digest /
    build_user_profiles, since the main consumer is an LLM/downstream
    tool reading the whole document, not a human skimming it. Per-channel
    structure is kept (rather than flattening into one messages list)
    because channel identity/description/status is exactly what a reader
    needs to judge whether a leftover canvas still matters.

    Every channel/message/file is stamped with first_seen_at/last_seen_at
    (both equal to this run's timestamp on a fresh digest) so a later
    merge_digests() call has provenance to work with from run one - no
    separate "legacy" shape to special-case."""
    generated_at = _now()
    with_content = [r for r in results if r.get("messages") or r.get("files")]
    errored = [r for r in results if r.get("error")]

    channels_out = []
    for r in results:
        c = r["channel"]
        channels_out.append(
            {
                "id": c["id"],
                "name": c["name"],
                "description": c["description"],
                "slack_archived": c["is_archived"],
                "member": c["member"],
                "error": _sanitize_error(r["error"]) if r.get("error") else None,
                "first_seen_at": generated_at,
                "last_seen_at": generated_at,
                "messages": [
                    {**m, "first_seen_at": generated_at, "last_seen_at": generated_at}
                    for m in r.get("messages", [])
                ],
                "files": [
                    {
                        **f,
                        "first_seen_at": generated_at,
                        "last_seen_at": generated_at,
                        "content_last_changed_at": generated_at,
                    }
                    for f in r.get("files", [])
                ],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "first_generated_at": generated_at,
        "last_generated_at": generated_at,
        "workspace": workspace,
        "pattern": pattern,
        "manifest": {
            "channels_total": len(results),
            "channels_with_content": len(with_content),
            "channels_scanned_this_run": len(results),
            "errors_this_run": len(errored),
            "known_limitations": _KNOWN_LIMITATIONS,
        },
        "channels": channels_out,
    }


def _merge_items(old_items: list[dict], new_items: list[dict], key: str, new_seen_at: str, track_content: bool) -> list[dict]:
    old_by_key = {item[key]: item for item in old_items}
    new_by_key = {item[key]: item for item in new_items}
    merged = []
    for k in dict.fromkeys([*old_by_key, *new_by_key]):
        old_item = old_by_key.get(k)
        new_item = new_by_key.get(k)
        if old_item is None:
            merged.append(new_item)
        elif new_item is None:
            # not present in this run (channel not rescanned, or item removed
            # upstream) - keep the last-known copy rather than dropping history
            merged.append(old_item)
        else:
            item = {**new_item, "first_seen_at": old_item.get("first_seen_at", new_seen_at)}
            if track_content:
                changed = old_item.get("content") != new_item.get("content")
                item["content_last_changed_at"] = (
                    new_seen_at if changed else old_item.get("content_last_changed_at", new_seen_at)
                )
            merged.append(item)
    return merged


def _merge_channel(old_c: dict | None, new_c: dict | None, new_seen_at: str) -> dict:
    if old_c is None:
        return new_c
    if new_c is None:
        return old_c
    return {
        "id": new_c["id"],
        "name": new_c["name"],
        "description": new_c["description"],
        "slack_archived": new_c["slack_archived"],
        "member": new_c["member"],
        "error": new_c["error"],
        "first_seen_at": old_c.get("first_seen_at", new_seen_at),
        "last_seen_at": new_seen_at,
        "messages": _merge_items(old_c.get("messages", []), new_c.get("messages", []), "ts", new_seen_at, track_content=False),
        "files": _merge_items(old_c.get("files", []), new_c.get("files", []), "id", new_seen_at, track_content=True),
    }


def merge_digests(old: dict, new: dict) -> dict:
    """Merges a freshly built digest (`new`, from build_digest()) into a
    previously saved one (`old`, loaded back from disk), keyed by channel
    id / message ts / file id. Channels/items missing from `new` (e.g. the
    pattern changed, or a channel got rescanned less often) are kept as-is
    from `old` rather than dropped - this is a cumulative record, not a
    replacement. See docs/DESIGN-files.md's first_seen/last_seen convention
    for the same "no real edit history from the Slack API" tradeoff applied
    to file content here via content_last_changed_at."""
    if old.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"cannot merge - old digest schema_version {old.get('schema_version')!r} != {SCHEMA_VERSION!r}")

    new_seen_at = new["last_generated_at"]
    old_channels_by_id = {c["id"]: c for c in old.get("channels", [])}
    new_channels_by_id = {c["id"]: c for c in new["channels"]}

    merged_channels = [
        _merge_channel(old_channels_by_id.get(cid), new_channels_by_id.get(cid), new_seen_at)
        for cid in dict.fromkeys([*old_channels_by_id, *new_channels_by_id])
    ]
    merged_channels.sort(key=lambda c: c["name"])

    with_content = [c for c in merged_channels if c["messages"] or c["files"]]
    errored_this_run = [c for c in new["channels"] if c.get("error")]

    return {
        "schema_version": SCHEMA_VERSION,
        "first_generated_at": old.get("first_generated_at", new_seen_at),
        "last_generated_at": new_seen_at,
        "workspace": new["workspace"],
        "pattern": new["pattern"],
        "manifest": {
            "channels_total": len(merged_channels),
            "channels_with_content": len(with_content),
            "channels_scanned_this_run": len(new["channels"]),
            "errors_this_run": len(errored_this_run),
            "known_limitations": _KNOWN_LIMITATIONS,
        },
        "channels": merged_channels,
    }
