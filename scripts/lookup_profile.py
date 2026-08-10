#!/usr/bin/env python3
"""Look up Slack profile fields (name, email, phone, title, etc.) for members
of an archived workspace, by nickname/real-name/display-name substring match.

Reuses `slackdump convert -f export`'s users.json output (same boundary as
export_logic.build_user_profiles) rather than parsing S_USER blobs directly.
Unlike build_user_profiles, this does NOT strip email/phone - it's a personal
lookup tool over your own workspace data, not digest output meant for
LLM/report consumption.

Usage:
    scripts/lookup_profile.py f3kirkland Ariel Montoya Falseto Headspace
    scripts/lookup_profile.py f3kirkland "Ariel" --archive-root ~/slack-backups
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from slackbackup import channel_lock, slackdump  # noqa: E402

DEFAULT_ARCHIVE_ROOT = Path.home() / "slack-backups"

FIELDS = ("name", "real_name", "display_name", "title", "email", "phone")


def _find_archived_channel(workspace_dir: Path) -> Path | None:
    if not workspace_dir.is_dir():
        return None
    for channel_dir in sorted(workspace_dir.iterdir()):
        if (channel_dir / "slackdump.sqlite").exists():
            return channel_dir
    return None


def load_users(workspace: str, archive_root: Path) -> list[dict]:
    channel_dir = _find_archived_channel(archive_root / workspace)
    if channel_dir is None:
        raise SystemExit(f"no archived channel found for workspace {workspace!r} under {archive_root}")

    try:
        with channel_lock.channel_lock(channel_dir):
            with tempfile.TemporaryDirectory() as export_dir:
                export_dir_path = Path(export_dir)
                slackdump.convert_export(channel_dir, export_dir_path)
                users_file = export_dir_path / "users.json"
                return json.loads(users_file.read_text()) if users_file.exists() else []
    except channel_lock.ChannelLockedError as exc:
        raise SystemExit(f"{workspace}: channel busy (backup/dedupe in progress) - {exc}")


def flatten(user: dict) -> dict:
    profile = user.get("profile") or {}
    return {
        "id": user.get("id"),
        "name": user.get("name"),
        "real_name": user.get("real_name"),
        "display_name": profile.get("display_name") or None,
        "title": profile.get("title") or None,
        "email": profile.get("email") or None,
        "phone": profile.get("phone") or None,
        "deleted": user.get("deleted", False),
    }


def matches(profile: dict, query: str) -> bool:
    query = query.lower()
    return any(query in (profile.get(f) or "").lower() for f in ("name", "real_name", "display_name"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workspace", help="workspace name, e.g. f3kirkland")
    parser.add_argument("query", nargs="+", help="name/nickname substrings to search for (case-insensitive)")
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    users = [flatten(u) for u in load_users(args.workspace, args.archive_root)]

    results = {q: [u for u in users if matches(u, q)] for q in args.query}

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for query, matched in results.items():
        print(f"=== {query} ===")
        if not matched:
            print("  (no match)")
            continue
        for u in matched:
            print(f"  {u['real_name'] or u['name']}  (@{u['name']}, id={u['id']})")
            print(f"    display_name: {u['display_name']}")
            print(f"    title:        {u['title']}")
            print(f"    email:        {u['email']}")
            print(f"    phone:        {u['phone']}")
        print()


if __name__ == "__main__":
    main()
