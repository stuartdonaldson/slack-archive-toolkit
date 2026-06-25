#!/usr/bin/env python3
"""channels.json validation, registration, and per-workspace listing.
Ported from validate-channels.sh + register-channel.sh's file-mutation
parts. Channel lookup-by-name/id is delegated to catalog_logic.lookup().
"""
from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path

from . import catalog_logic, workspace_logic


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ChannelError(RuntimeError):
    pass


_GLOB_CHARS = set("*?[")


def is_glob(query: str) -> bool:
    return any(c in _GLOB_CHARS for c in query)


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


def register(
    workspace: str, query: str, channels_file: Path,
    cache_dir: Path = catalog_logic.DEFAULT_CACHE_DIR,
) -> tuple[str, str, bool]:
    """Looks up `query` (a channel name, optionally with a leading '#', or a
    raw channel id) in `workspace` via the catalog, and appends it to
    `channels_file` if not already present.

    Returns (channel_id, channel_name, already_present).
    Raises ChannelError on no match or an ambiguous (>1) match.
    """
    query = query.lstrip("#")
    matches = catalog_logic.lookup(workspace, query, cache_dir=cache_dir)

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
    catalog_logic.set_registered_at(cache_dir, workspace, channel_id, _now_iso())
    return channel_id, channel_name, False


def register_matching(
    workspace_glob: str, channel_glob: str, channels_file: Path,
    cache_dir: Path = catalog_logic.DEFAULT_CACHE_DIR,
) -> dict:
    """Bulk variant of register(): registers every not-yet-tracked, public,
    non-archived channel whose name matches `channel_glob`, in every
    known+registered workspace matching `workspace_glob` (e.g.
    workspace_glob="f3*", channel_glob="*" picks up every new public
    channel across all f3* workspaces - run nightly to stop catching
    missed channels like "disc-it" by hand).

    Always matches against the FULL catalog tier (every public channel,
    not just ones we're a member of) - membership isn't required to read
    or archive a public channel (confirmed empirically, see
    docs/DESIGN-files.md). Private and archived channels are always
    skipped regardless of the glob - this is meant to catch newly-created
    *public* channels, not to silently sweep in archived/closed-out
    channels (confirmed ~30% of a real workspace's full channel list) or
    private ones the session happens to be a member of. Channels named
    "shuttered*" are also always skipped - this F3 community's own naming
    convention for a closed-out AO, which Slack's is_archived flag does
    not reliably reflect (confirmed: most shuttered-named channels are
    not actually archived in Slack's own data). Returns {"added": [...],
    "workspaces_checked": [...], "workspaces_skipped_unregistered": [...]}.
    """
    status = workspace_logic.status()
    matched_workspaces = [w for w in status["known"] if fnmatch.fnmatch(w["name"], workspace_glob)]
    workspaces_checked = sorted(w["name"] for w in matched_workspaces if w["registered"])
    workspaces_skipped = sorted(w["name"] for w in matched_workspaces if not w["registered"])

    entries = load(channels_file)
    existing = {(e["id"], e["workspace"]) for e in entries}
    added = []
    now = _now_iso()

    for workspace in workspaces_checked:
        catalog = catalog_logic.refresh_full(workspace, cache_dir=cache_dir)
        for channel_id, channel in catalog["channels"].items():
            if channel.get("is_private") or channel.get("is_archived"):
                continue
            if channel["name"].lower().startswith("shuttered"):
                continue
            if not fnmatch.fnmatch(channel["name"], channel_glob):
                continue
            if (channel_id, workspace) in existing:
                continue
            entries.append({"id": channel_id, "name": channel["name"], "workspace": workspace})
            existing.add((channel_id, workspace))
            added.append({"id": channel_id, "name": channel["name"], "workspace": workspace})
            catalog_logic.set_registered_at(cache_dir, workspace, channel_id, now)

    if added:
        save(channels_file, entries)

    return {
        "added": added,
        "workspaces_checked": workspaces_checked,
        "workspaces_skipped_unregistered": workspaces_skipped,
    }


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
