"""Tiered retention for ~/slack-exports snapshot files (sat-v4t).

Pure planning + one tiny apply step; no CLI, no Slack, no archive access.

Every nightly run writes a fresh snapshot of the same report, so the folder
fills with near-duplicates. A snapshot is identified by its as_of date (the
run date); the group it belongs to is (prefix, kind, report_month) because one
run emits several report months. Within a group three tiers each pick files
independently from the FULL candidate list, and a file is deleted only if
NO tier keeps it:

  daily   every snapshot whose as_of is <= DAILY_DAYS old
  weekly  the latest snapshot per ISO week, as_of <= WEEKLY_DAYS old
  monthly one snapshot per as_of calendar month, however old:
          earliest in the month when the month is after the report month
          (the snapshot covers a closed month); otherwise (as_of month <=
          report month, so the report month was still open) the latest,
          flagged partial.

Because the weekly tier only ever adds to the keep set, it can never drop a
monthly keeper. Candidates are validated lazily (must parse as a JSON
object); an invalid file is never deleted, and a month with no valid
snapshot is reported as a gap and left entirely alone.

`files` sidecars are cumulative and not regenerable (docs/OPERATIONS.md), so
they are skipped unless include_files is set, and then the latest is always
kept as well.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional

DAILY_DAYS = 7
WEEKLY_DAYS = 35

_DATE = r"(?P<d>\d{4}-\d{2}-\d{2})"
_MONTH = r"(?P<m>\d{4}-\d{2})"
# Order matters only for readability: the three patterns cannot match the same name.
_OLD_DIGEST_RE = re.compile(rf"^(?P<prefix>.+)-(?P<kind>digest)-{_DATE}-{_MONTH}\.json$")
_NEW_DIGEST_RE = re.compile(rf"^(?P<prefix>.+)-(?P<kind>digest)-{_MONTH}\.{_DATE}\.json$")
_SNAPSHOT_RE = re.compile(rf"^(?P<prefix>.+)-(?P<kind>digest|users|files)-{_DATE}\.json$")


@dataclass(frozen=True)
class Parsed:
    prefix: str
    kind: str
    as_of: date
    report_month: Optional[str]


def parse_name(name: str) -> Optional[Parsed]:
    """Parses a snapshot filename in either digest naming scheme (or the
    users/files/dm-digest `{prefix}-{kind}-{as_of}.json` form). Returns None
    for anything else (placeholders, directories, other file families)."""
    for pattern in (_OLD_DIGEST_RE, _NEW_DIGEST_RE, _SNAPSHOT_RE):
        m = pattern.match(name)
        if not m:
            continue
        try:
            as_of = date.fromisoformat(m["d"])
        except ValueError:
            return None
        return Parsed(m["prefix"], m["kind"], as_of, m.groupdict().get("m"))
    return None


@dataclass
class PrunePlan:
    keep: dict[Path, list[str]] = field(default_factory=dict)  # path -> reasons
    delete: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)   # not a pruned family; never touched
    invalid: list[Path] = field(default_factory=list)   # failed validation; never deleted
    partial: list[str] = field(default_factory=list)    # months whose keeper is an open-month snapshot
    gaps: list[str] = field(default_factory=list)       # as_of months with files but no valid keeper


def is_valid_snapshot(path: Path) -> bool:
    try:
        return isinstance(json.loads(path.read_text()), dict)
    except (OSError, ValueError):
        return False


def plan_prune(
    files: list[Path],
    today: date,
    include_files: bool = False,
    validate: Callable[[Path], bool] = is_valid_snapshot,
) -> PrunePlan:
    plan = PrunePlan()
    groups: dict[tuple, list[tuple[Parsed, Path]]] = {}
    for path in files:
        parsed = parse_name(path.name) if path.is_file() else None
        if parsed is None or (parsed.kind == "files" and not include_files):
            plan.skipped.append(path)
            continue
        groups.setdefault((parsed.prefix, parsed.kind, parsed.report_month), []).append((parsed, path))

    valid_cache: dict[Path, bool] = {}

    def is_valid(path: Path) -> bool:
        if path not in valid_cache:
            valid_cache[path] = validate(path)
            if not valid_cache[path]:
                plan.invalid.append(path)
                keep(path, "invalid-untouched")
        return valid_cache[path]

    def keep(path: Path, reason: str) -> None:
        plan.keep.setdefault(path, []).append(reason)

    def first_valid(cands):
        return next((c for c in cands if is_valid(c[1])), None)

    for (prefix, kind, report_month), members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        label = f"{prefix} {kind}" + (f" {report_month}" if report_month else "")
        members.sort(key=lambda c: (c[0].as_of, c[1].name))

        for parsed, path in members:
            if (today - parsed.as_of).days <= DAILY_DAYS:
                keep(path, "daily")

        by_week: dict[tuple, list] = {}
        for c in members:
            if (today - c[0].as_of).days <= WEEKLY_DAYS:
                by_week.setdefault(c[0].as_of.isocalendar()[:2], []).append(c)
        for cands in by_week.values():
            hit = first_valid(reversed(cands))
            if hit:
                keep(hit[1], "weekly")

        by_month: dict[str, list] = {}
        for c in members:
            by_month.setdefault(c[0].as_of.strftime("%Y-%m"), []).append(c)
        for month, cands in sorted(by_month.items()):
            open_month = report_month is not None and month <= report_month
            hit = first_valid(reversed(cands) if open_month else cands)
            if hit is None:
                plan.gaps.append(f"{label}: as_of {month}: no valid snapshot")
                for _, path in cands:
                    keep(path, "gap")
                continue
            keep(hit[1], "monthly-partial" if open_month else "monthly")
            if open_month:
                plan.partial.append(f"{label}: as_of {month}: kept latest {hit[1].name} (as_of month not after report month; latest of that month)")

        if kind == "files":
            hit = first_valid(reversed(members))
            if hit:
                keep(hit[1], "latest")

        for _, path in members:
            if path not in plan.keep:
                plan.delete.append(path)

    return plan


def apply_plan(plan: PrunePlan) -> int:
    for path in plan.delete:
        path.unlink()
    return len(plan.delete)
