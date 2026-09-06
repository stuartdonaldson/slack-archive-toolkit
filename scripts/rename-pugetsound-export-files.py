#!/usr/bin/env python3
"""One-off rename of ~/slack-exports/f3-pugetsound-* files to the naming
convention jobs/f3-pugetsound.json now uses (month before as_of):

  digest: f3-pugetsound-digest-{as_of}-{month}.json  -> f3-pugetsound-digest-{month}.{as_of}.json
  users:  f3-pugetsound-users-{as_of}.json            -> f3-pugetsound-users-{month}.json
  files:  f3-pugetsound-files-{as_of}.json            -> f3-pugetsound-files-{month}.json

digest renames are 1:1 (both {month} and {as_of} survive in the new name).

users/files renames are NOT 1:1: the new pattern drops {as_of}, so every
as_of snapshot within the same month collapses onto one filename. This
script keeps only the newest as_of per month (by filename date, not mtime)
and deletes the older same-month snapshots for that prefix. Digest files are
never deleted - only renamed.

Dry-run by default; pass --apply to actually touch the filesystem.

    python3 scripts/rename-pugetsound-export-files.py            # preview
    python3 scripts/rename-pugetsound-export-files.py --apply    # do it
"""
import argparse
import re
import sys
from pathlib import Path

EXPORT_DIR = Path("~/slack-exports").expanduser()
PREFIX = "f3-pugetsound"

DIGEST_RE = re.compile(rf"^{re.escape(PREFIX)}-digest-(\d{{4}}-\d{{2}}-\d{{2}})-(\d{{4}}-\d{{2}})\.json$")
SNAPSHOT_RE = re.compile(rf"^{re.escape(PREFIX)}-(users|files)-(\d{{4}}-\d{{2}}-\d{{2}})\.json$")


def plan_digest_renames(files: list[Path]) -> list[tuple[Path, Path]]:
    renames = []
    for f in files:
        m = DIGEST_RE.match(f.name)
        if not m:
            continue
        as_of, month = m.groups()
        new_name = f"{PREFIX}-digest-{month}.{as_of}.json"
        renames.append((f, f.with_name(new_name)))
    return renames


def plan_snapshot_renames(files: list[Path]) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """Returns (renames, deletes). For each (kind, month), keeps the file
    with the newest as_of and renames it to the month-only name; every
    older same-month file for that kind is marked for deletion."""
    by_kind_month: dict[tuple[str, str], list[tuple[str, Path]]] = {}
    for f in files:
        m = SNAPSHOT_RE.match(f.name)
        if not m:
            continue
        kind, as_of = m.groups()
        month = as_of[:7]
        by_kind_month.setdefault((kind, month), []).append((as_of, f))

    renames = []
    deletes = []
    for (kind, month), entries in by_kind_month.items():
        entries.sort(key=lambda e: e[0])  # by as_of, ascending
        newest_as_of, newest_path = entries[-1]
        new_name = f"{PREFIX}-{kind}-{month}.json"
        renames.append((newest_path, newest_path.with_name(new_name)))
        deletes.extend(path for as_of, path in entries[:-1])
    return renames, deletes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="actually rename/delete (default: dry-run preview)")
    args = parser.parse_args()

    if not EXPORT_DIR.is_dir():
        print(f"no such directory: {EXPORT_DIR}", file=sys.stderr)
        return 1

    files = sorted(EXPORT_DIR.glob(f"{PREFIX}-*.json"))
    digest_renames = plan_digest_renames(files)
    snapshot_renames, snapshot_deletes = plan_snapshot_renames(files)

    print(f"digest: {len(digest_renames)} rename(s)")
    for src, dst in digest_renames:
        print(f"  {src.name}  ->  {dst.name}")

    print(f"\nusers/files: {len(snapshot_renames)} rename(s) (newest as_of per month kept)")
    for src, dst in snapshot_renames:
        print(f"  {src.name}  ->  {dst.name}")

    print(f"\nusers/files: {len(snapshot_deletes)} delete(s) (superseded same-month snapshots)")
    for path in snapshot_deletes:
        print(f"  {path.name}")

    all_renames = digest_renames + snapshot_renames
    dest_names = [dst.name for _, dst in all_renames]
    dupes = {n for n in dest_names if dest_names.count(n) > 1}
    if dupes:
        print(f"\nERROR: rename plan produces duplicate targets: {sorted(dupes)}", file=sys.stderr)
        return 1

    if not args.apply:
        print("\nDry run only - pass --apply to execute.")
        return 0

    for src, dst in all_renames:
        if dst.exists():
            print(f"SKIP (target exists): {src.name} -> {dst.name}", file=sys.stderr)
            continue
        src.rename(dst)
    for path in snapshot_deletes:
        path.unlink()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
