#!/usr/bin/env python3
"""channels.json validation, registration, and per-workspace listing.
Ported from validate-channels.sh + register-channel.sh's file-mutation
parts. Channel lookup-by-name/id is delegated to catalog_logic.lookup().
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import catalog_logic, selector_logic, workspace_logic


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ChannelError(RuntimeError):
    pass


_GLOB_CHARS = set("*?[")


def is_glob(query: str) -> bool:
    return "," in query or any(c in _GLOB_CHARS for c in query)


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
    not actually archived in Slack's own data). Every channel matching
    `channel_glob` (whether or not it ends up added) is reported: skipped
    channels appear in "skipped" with a single reason - "private",
    "archived", "shuttered-name", or "already-registered", in that priority
    order (a channel that's both private and archived reports "private").
    Channels that don't match `channel_glob` at all are not reported in
    either list.

    Also prunes (sat-21k): for the same matched-workspace/matched-channel-glob
    scope, an ALREADY-tracked channel is removed from channels.json - reported
    under "removed", never "skipped" - when either:
      - it's now archived in the catalog ("archived"), or
      - it's entirely absent from this workspace's full-tier catalog
        ("missing") - but ONLY when this run's full-tier scan for that
        workspace came back complete (catalog["full_scan_complete"]); a
        truncated/untrustworthy scan (see sat-dnr) must never be read as
        proof a channel is gone, so nothing is pruned as "missing" for that
        workspace this run.
    shuttered*-named channels are exempt from both prune reasons - same
    manual-retention rationale as their registration exemption above.
    Pruning never touches the channel's local backup data on disk, only
    this channels.json entry.

    Returns {"added": [...], "skipped": [...], "removed": [...],
    "workspaces_checked": [...], "workspaces_skipped_unregistered": [...]}.
    """
    status = workspace_logic.status()
    matched_workspaces = [w for w in status["known"] if selector_logic.matches_selector(workspace_glob, w["name"])]
    workspaces_checked = sorted(w["name"] for w in matched_workspaces if w["registered"])
    workspaces_skipped = sorted(w["name"] for w in matched_workspaces if not w["registered"])

    entries = load(channels_file)
    existing = {(e["id"], e["workspace"]) for e in entries}
    added = []
    skipped = []
    removed = []
    now = _now_iso()

    for workspace in workspaces_checked:
        catalog = catalog_logic.refresh_full(workspace, cache_dir=cache_dir)
        catalog_channels = catalog["channels"]
        for channel_id, channel in catalog_channels.items():
            if not selector_logic.matches_selector(channel_glob, channel["name"]):
                continue

            reason = None
            if channel.get("is_private"):
                reason = "private"
            elif channel.get("is_archived"):
                reason = "archived"
            elif channel["name"].lower().startswith("shuttered"):
                reason = "shuttered-name"
            elif (channel_id, workspace) in existing:
                reason = "already-registered"

            if reason is not None:
                skipped.append({"id": channel_id, "name": channel["name"], "workspace": workspace, "reason": reason})
                continue

            entries.append({"id": channel_id, "name": channel["name"], "workspace": workspace})
            existing.add((channel_id, workspace))
            added.append({"id": channel_id, "name": channel["name"], "workspace": workspace})
            catalog_logic.set_registered_at(cache_dir, workspace, channel_id, now)

        scan_complete = catalog.get("full_scan_complete", False)
        kept_entries = []
        for entry in entries:
            if entry["workspace"] != workspace or not selector_logic.matches_selector(channel_glob, entry["name"]):
                kept_entries.append(entry)
                continue
            if entry["name"].lower().startswith("shuttered"):
                kept_entries.append(entry)
                continue

            channel = catalog_channels.get(entry["id"])
            reason = None
            if channel is not None and channel.get("is_archived"):
                reason = "archived"
            elif channel is None and scan_complete:
                reason = "missing"

            if reason is None:
                kept_entries.append(entry)
                continue
            removed.append({"id": entry["id"], "name": entry["name"], "workspace": workspace, "reason": reason})
            existing.discard((entry["id"], workspace))
        entries = kept_entries

        # An already-tracked archived channel matches the add-loop's own
        # "archived" skip check above (that check doesn't know about tracking
        # status - it also fires for never-tracked archived channels, where
        # "skipped" is the only correct outcome). Once it's in `removed`,
        # drop the redundant `skipped` entry - "removed" is the more specific
        # and accurate outcome for a channel that was actually being tracked.
        removed_this_workspace = {(r["id"], r["workspace"]) for r in removed if r["workspace"] == workspace}
        skipped = [s for s in skipped if (s["id"], s["workspace"]) not in removed_this_workspace]

    if added or removed:
        save(channels_file, entries)

    return {
        "added": added,
        "skipped": skipped,
        "removed": removed,
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
                "private": channel.get("is_private", False),
            }
        )
    return rows
