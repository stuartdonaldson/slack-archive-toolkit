#!/usr/bin/env python3
"""File index summary. Operates purely on an existing index.json - works
regardless of whether `files fetch`/`files index` (still unported) produced
it; the index.json schema is the contract, not the tool that wrote it.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def load_index(index_json: Path) -> list[dict]:
    if not index_json.exists():
        return []
    return json.loads(index_json.read_text())


def summarize(index_json: Path) -> dict:
    """Returns {total, by_workspace: {ws: count}, by_mimetype: {mimetype:
    count}, by_context_type: {type: count}}."""
    entries = load_index(index_json)
    return {
        "total": len(entries),
        "by_workspace": dict(Counter(e.get("workspace", "") for e in entries)),
        "by_mimetype": dict(Counter(e.get("mimetype", "") for e in entries)),
        "by_context_type": dict(
            Counter((e.get("message_context") or {}).get("type", "") for e in entries)
        ),
    }
