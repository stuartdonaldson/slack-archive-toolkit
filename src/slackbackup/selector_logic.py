from __future__ import annotations

import fnmatch
import glob


def split_selector_list(selector: str) -> list[str]:
    return [part.strip() for part in selector.split(",") if part.strip()]


def matches_selector(selector: str, value: str) -> bool:
    return any(fnmatch.fnmatch(value, part) for part in split_selector_list(selector))


def expand_path_selector(selector: str) -> list[str]:
    """Comma-separated list of filesystem glob patterns (e.g. 'jobs/*.json'
    or 'jobs/f3-*.json,jobs/extra.json') expanded to actual paths on disk,
    deduped and sorted for stable ordering. A part with no glob metacharacters
    that matches nothing is passed through as-is so a typo'd literal path
    still surfaces as a clear "file not found" downstream, rather than
    silently vanishing the way a genuinely-empty wildcard match should."""
    paths: set[str] = set()
    for part in split_selector_list(selector):
        matches = glob.glob(part)
        if matches:
            paths.update(matches)
        elif not glob.has_magic(part):
            paths.add(part)
    return sorted(paths)