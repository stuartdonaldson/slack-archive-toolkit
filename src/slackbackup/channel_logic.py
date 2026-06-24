#!/usr/bin/env python3
"""channels.json validation, registration, and per-workspace listing.
Ported from validate-channels.sh + register-channel.sh's file-mutation
parts. Channel lookup-by-name/id is delegated to catalog_logic.lookup().
"""
from __future__ import annotations

import json
from pathlib import Path

from . import catalog_logic


class ChannelError(RuntimeError):
    pass


def validate(channels_file: Path) -> list[dict]:
    """Raises ChannelError if `channels_file` isn't a non-empty array of
    {id, name, workspace} objects with non-empty string values. Returns the
    parsed list on success."""
    if not channels_file.exists():
        raise ChannelError(f"file not found: {channels_file}")

    try:
        data = json.loads(channels_file.read_text())
    except json.JSONDecodeError as exc:
        raise ChannelError(f"{channels_file} is not valid JSON: {exc}") from exc

    if not isinstance(data, list) or not data:
        raise ChannelError(f"{channels_file} is not valid — expected a non-empty array")

    for entry in data:
        for field in ("id", "name", "workspace"):
            if not isinstance(entry.get(field), str) or not entry.get(field):
                raise ChannelError(
                    f"{channels_file} is not valid — expected a non-empty array of "
                    '{"id": string, "name": string, "workspace": string}'
                )
    return data


def load(channels_file: Path) -> list[dict]:
    if not channels_file.exists():
        return []
    return json.loads(channels_file.read_text())


def save(channels_file: Path, entries: list[dict]) -> None:
    tmp = channels_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2) + "\n")
    tmp.replace(channels_file)


def register(workspace: str, query: str, channels_file: Path) -> tuple[str, str, bool]:
    """Looks up `query` (a channel name, optionally with a leading '#', or a
    raw channel id) in `workspace` via the catalog, and appends it to
    `channels_file` if not already present.

    Returns (channel_id, channel_name, already_present).
    Raises ChannelError on no match or an ambiguous (>1) match.
    """
    query = query.lstrip("#")
    matches = catalog_logic.lookup(workspace, query)

    if not matches:
        raise ChannelError(f"no channel matching '{query}' found in workspace '{workspace}'")
    if len(matches) > 1:
        names = ", ".join(f"{cid} ({ch['name']})" for cid, ch in matches)
        raise ChannelError(f"'{query}' matched more than one channel in '{workspace}': {names}")

    channel_id, channel = matches[0]
    channel_name = channel["name"]

    entries = load(channels_file)
    for entry in entries:
        if entry["id"] == channel_id and entry["workspace"] == workspace:
            return channel_id, channel_name, True

    entries.append({"id": channel_id, "name": channel_name, "workspace": workspace})
    save(channels_file, entries)
    return channel_id, channel_name, False


def list_for_workspace(workspace: str, channels_file: Path) -> list[dict]:
    """One row per channel visible in the fast tier: {id, name, registered}."""
    registered_ids = {
        entry["id"] for entry in load(channels_file) if entry["workspace"] == workspace
    }
    data = catalog_logic.refresh_fast(workspace)
    rows = []
    for channel_id, channel in data["channels"].items():
        if not channel["member"]:
            continue
        rows.append(
            {
                "id": channel_id,
                "name": channel["name"],
                "registered": channel_id in registered_ids,
            }
        )
    return rows
