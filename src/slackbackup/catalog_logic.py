#!/usr/bin/env python3
"""Per-workspace channel catalog: a single cache file combining the cheap
"fast tier" (`list channels -member-only`) and the expensive, rate-limit-
prone "full tier" (`list channels`, no filter) into one source of truth.

No code outside this module should call slackdump.list_channels() directly.

Fast-tier refresh upserts member=True rows; it never marks a channel
member=False. Full-tier refresh upserts any channel not already present as
member=False; it never overwrites an existing member=True row's membership
flag (name/description may still be refreshed by either tier). The two
tiers always write into the same cache file, so there's nothing to
reconcile after the fact.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from . import slackdump

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "slackbackup"
FAST_TTL_SECONDS = 900
FULL_TTL_SECONDS = 21600


def _catalog_path(cache_dir: Path, workspace: str) -> Path:
    return cache_dir / f"{workspace}.catalog.json"


def load(cache_dir: Path, workspace: str) -> dict:
    path = _catalog_path(cache_dir, workspace)
    if not path.exists():
        return {"channels": {}, "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0}
    return json.loads(path.read_text())


def save(cache_dir: Path, workspace: str, data: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _catalog_path(cache_dir, workspace)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def description_of(channel: dict) -> str:
    """.topic.value, falling back to .purpose.value - same single
    `-format JSON` call already being made for membership/name, no extra
    API call."""
    topic = (channel.get("topic") or {}).get("value") or ""
    if topic:
        return topic
    return (channel.get("purpose") or {}).get("value") or ""


def _channel_fields(ch: dict, member: bool) -> dict:
    return {
        "member": member,
        "name": ch["name"],
        "description": description_of(ch),
        "topic": (ch.get("topic") or {}).get("value") or None,
        "is_private": ch.get("is_private", False),
        "is_archived": ch.get("is_archived", False),
        "creator": ch.get("creator") or None,
        "created": ch.get("created") or None,
    }


def merge_fast(data: dict, channels: list[dict]) -> dict:
    for ch in channels:
        data["channels"][ch["id"]] = _channel_fields(ch, member=True)
    return data


def merge_full(data: dict, channels: list[dict]) -> dict:
    for ch in channels:
        existing = data["channels"].get(ch["id"])
        if existing is not None:
            existing.update(_channel_fields(ch, member=existing["member"]))
        else:
            data["channels"][ch["id"]] = _channel_fields(ch, member=False)
    return data


def refresh_fast(
    workspace: str,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    ttl: int = FAST_TTL_SECONDS,
    now: float | None = None,
) -> dict:
    data = load(cache_dir, workspace)
    now = time.time() if now is None else now
    if now - data["fast_refreshed_at"] < ttl:
        return data

    print(
        f"catalog: refreshing fast-tier channel list for '{workspace}' "
        "(cache stale or missing, member-only, usually a few seconds)...",
        file=sys.stderr,
    )
    slackdump.select_workspace_or_die(workspace)
    channels = slackdump.list_channels(member_only=True)
    data = merge_fast(data, channels)
    data["fast_refreshed_at"] = now
    save(cache_dir, workspace, data)
    return data


def refresh_full(
    workspace: str,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    ttl: int = FULL_TTL_SECONDS,
    now: float | None = None,
) -> dict:
    data = load(cache_dir, workspace)
    now = time.time() if now is None else now
    if now - data["full_refreshed_at"] < ttl:
        return data

    print(
        f"catalog: refreshing FULL channel list for '{workspace}' (cache stale "
        "or missing, no member filter — this lists every public channel, can "
        "take several minutes and may hit Slack's rate limit; slackdump will "
        "back off and retry automatically, just wait)...",
        file=sys.stderr,
    )
    slackdump.select_workspace_or_die(workspace)
    channels = slackdump.list_channels(member_only=False)
    data = merge_full(data, channels)
    data["full_refreshed_at"] = now
    save(cache_dir, workspace, data)
    return data


_CHANNEL_ID_RE = re.compile(r"^C[A-Z0-9]+$")


def match_channels(channels: dict, query: str) -> list[tuple[str, dict]]:
    if _CHANNEL_ID_RE.match(query):
        return [(cid, ch) for cid, ch in channels.items() if cid == query]
    query_lower = query.lower()
    return [(cid, ch) for cid, ch in channels.items() if ch["name"].lower() == query_lower]


def lookup(
    workspace: str, query: str, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[tuple[str, dict]]:
    """Checks the fast tier first; on a miss, triggers a (cached) full-tier
    refresh and retries - the expensive call becomes an explicit, cached
    fallback instead of an inline call on every lookup."""
    data = refresh_fast(workspace, cache_dir)
    member_channels = {cid: ch for cid, ch in data["channels"].items() if ch["member"]}
    matches = match_channels(member_channels, query)
    if matches:
        return matches

    data = refresh_full(workspace, cache_dir)
    return match_channels(data["channels"], query)


def name_by_id(workspace: str, channel_id: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> str:
    """Read-only: never triggers a refresh, never calls slackdump."""
    data = load(cache_dir, workspace)
    channel = data["channels"].get(channel_id)
    return channel["name"] if channel else ""


def set_registered_at(cache_dir: Path, workspace: str, channel_id: str, when: str) -> None:
    """Stamps the moment we started tracking this channel (ISO8601 UTC) -
    idempotent, never overwrites an existing value. Fallback sort key for
    effective_recency before any backup has ever found real message data
    for this channel. No-op if the channel isn't in the catalog yet
    (shouldn't happen in practice - callers always look a channel up via
    the catalog before registering it)."""
    data = load(cache_dir, workspace)
    channel = data["channels"].get(channel_id)
    if channel is None or channel.get("registered_at"):
        return
    channel["registered_at"] = when
    save(cache_dir, workspace, data)


def update_last_posted(cache_dir: Path, workspace: str, channel_id: str, last_posted: str | None) -> None:
    """Records the real last-message timestamp (ISO8601 UTC) seen in this
    channel's local archive, called after a successful backup that found
    at least one message. A channel that yields zero messages leaves this
    untouched - callers fall back to registered_at via effective_recency
    instead, so a channel that never gets traffic keeps "aging" against
    the clock rather than looking falsely fresh."""
    if not last_posted:
        return
    data = load(cache_dir, workspace)
    channel = data["channels"].get(channel_id)
    if channel is None:
        return
    channel["last_posted"] = last_posted
    save(cache_dir, workspace, data)


def effective_recency(catalog: dict, channel_id: str) -> str:
    """Sort key for backup ordering: real last_posted if a backup has ever
    found message data, else registered_at (when we started tracking it),
    else "" (totally unknown - sorts oldest/last). ISO8601 strings sort
    correctly as plain strings."""
    channel = catalog.get("channels", {}).get(channel_id, {})
    return channel.get("last_posted") or channel.get("registered_at") or ""
