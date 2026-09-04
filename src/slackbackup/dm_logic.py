#!/usr/bin/env python3
"""dms.json load/save/registration - the DM/group-DM counterpart to
channel_logic.py's channels.json handling.

dms.json is deliberately a SEPARATE file from channels.json, in the exact
same {id, name, workspace} shape channel_logic.validate()/load()/save()
already handle - reused unchanged here rather than duplicated. Keeping the
two files separate is what keeps a DM/group-DM conversation out of every
channels.json-driven digest without any extra filtering logic: nothing
downstream (backup_logic.run, export_logic.select_channels) distinguishes
"channel" from "DM" at all - it only ever sees whichever tracked-list file
it was pointed at.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import channel_logic, selector_logic, slackdump, workspace_logic


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dm_name(entry: dict) -> str:
    """A tracked-list entry needs a non-empty `name` (channel_logic.validate()
    requires it, and it doubles as the archive directory slug - see
    backup_logic.channel_dir()). Slack's raw listing gives a group DM a
    usable name already (`mpdm-...`, the same name that motivated filtering
    it out of channels.json for). A plain 1:1 DM's raw name is always
    blank, so it's synthesized from the other participant's user id, which
    Slack's `is_im` entries always carry as `user`."""
    if entry.get("is_im"):
        return f"dm-{entry.get('user') or entry['id']}"
    return entry["name"]


def register_matching(
    workspace_glob: str, dms_file: Path, include_group: bool = True,
) -> dict:
    """Bulk-discovers DM (and, unless include_group is False, group-DM)
    conversations across every registered workspace matching
    `workspace_glob`, and reconciles `dms_file` against them - mirrors
    channel_logic.register_matching's add/prune shape, minus the
    private/archived/shuttered-name concepts that don't apply to DMs.
    Always the cheap member-only tier (see slackdump.list_dms) - no
    full-tier cost, no rate-limit risk.

    A DM no longer present in the fresh listing (the conversation was
    closed, or the operator was removed from a group DM) is pruned as
    "removed"/"missing" - the listing is a complete membership snapshot,
    not a scan that can plausibly be truncated the way channel_logic's
    full-tier scan can, so there's no separate "trust this prune" flag to
    check first.

    Returns {"added": [...], "removed": [...], "workspaces_checked": [...],
    "workspaces_skipped_unregistered": [...]}.
    """
    status = workspace_logic.status()
    matched_workspaces = [w for w in status["known"] if selector_logic.matches_selector(workspace_glob, w["name"])]
    workspaces_checked = sorted(w["name"] for w in matched_workspaces if w["registered"])
    workspaces_skipped = sorted(w["name"] for w in matched_workspaces if not w["registered"])

    entries = channel_logic.load(dms_file)
    existing = {(e["id"], e["workspace"]) for e in entries}
    added = []
    removed = []

    for workspace in workspaces_checked:
        slackdump.select_workspace_or_die(workspace)
        raw_dms = slackdump.list_dms(include_group=include_group)
        live_ids = {dm["id"] for dm in raw_dms}

        for dm in raw_dms:
            if (dm["id"], workspace) in existing:
                continue
            name = _dm_name(dm)
            entries.append({"id": dm["id"], "name": name, "workspace": workspace})
            existing.add((dm["id"], workspace))
            added.append({"id": dm["id"], "name": name, "workspace": workspace})

        kept_entries = []
        for entry in entries:
            if entry["workspace"] != workspace:
                kept_entries.append(entry)
                continue
            if entry["id"] in live_ids:
                kept_entries.append(entry)
                continue
            removed.append({"id": entry["id"], "name": entry["name"], "workspace": workspace, "reason": "missing"})
            existing.discard((entry["id"], workspace))
        entries = kept_entries

    if added or removed:
        channel_logic.save(dms_file, entries)

    return {
        "added": added,
        "removed": removed,
        "workspaces_checked": workspaces_checked,
        "workspaces_skipped_unregistered": workspaces_skipped,
    }
