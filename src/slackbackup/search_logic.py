#!/usr/bin/env python3
"""Cross-workspace message search -> one HTML report. Ported from
search-messages.sh + lib/message_search_helpers.sh (since removed - this
is now the only implementation).

Unlike the backup/digest pipeline, this makes a live Slack API search call
per matched workspace every run - no caching. `slackdump search messages`
treats multiple query words as an implicit AND (no OR operator).
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import selector_logic, workspace_logic


class NoWorkspaceMatchError(RuntimeError):
    pass


def select_workspaces(workspace_glob: str, tokens_file: Path = workspace_logic.DEFAULT_TOKENS_FILE) -> list[dict]:
    """Workspaces from the tokens file matching `workspace_glob` (exact
    name, glob, or comma-separated list of selectors - registered or not; callers
    decide whether to skip unregistered ones."""
    data = workspace_logic.status(tokens_file)
    return [w for w in data["known"] if selector_logic.matches_selector(workspace_glob, w["name"])]


def _read_search_results(db_path: Path, workspace: str) -> list[dict]:
    """`SEARCH_MESSAGE` already carries channel_id/channel_name/ts and a
    ready permalink in its DATA blob - no channel-catalog lookup needed
    (unlike `search files`' CHANNEL_ID placeholder rows)."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT CHANNEL_ID, CHANNEL_NAME, TS, TXT, DATA FROM SEARCH_MESSAGE").fetchall()
    finally:
        conn.close()

    results = []
    for channel_id, channel_name, ts, txt, data in rows:
        permalink = None
        if data:
            try:
                permalink = json.loads(data).get("permalink")
            except (json.JSONDecodeError, AttributeError):
                permalink = None
        results.append(
            {
                "workspace": workspace,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "ts": ts,
                "txt": txt,
                "permalink": permalink,
            }
        )
    return results


def search_messages(
    workspace_glob: str,
    query_terms: list[str],
    search_fn: Callable[[list[str], Path], bool],
    select_fn: Callable[[str], None],
    tokens_file: Path = workspace_logic.DEFAULT_TOKENS_FILE,
) -> tuple[list[dict], list[str]]:
    """Returns (results, skipped_unregistered_workspace_names). `search_fn`
    is normally slackdump.search_messages and `select_fn` normally
    slackdump.select_workspace_or_die - injected so tests can fake both
    without a live API call."""
    matched = select_workspaces(workspace_glob, tokens_file)
    if not matched:
        raise NoWorkspaceMatchError(f"no workspace matching '{workspace_glob}' found in tokens file")
    skipped = [w["name"] for w in matched if not w["registered"]]
    results: list[dict] = []

    for w in matched:
        if not w["registered"]:
            continue
        select_fn(w["name"])
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            if not search_fn(query_terms, out_dir):
                continue
            db_path = out_dir / "slackdump.sqlite"
            if not db_path.exists():
                continue
            results.extend(_read_search_results(db_path, w["name"]))

    return results, skipped


_MENTION_UNESCAPE = (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"))

# Slack mrkdwn basic marks, applied AFTER html.escape (see _render_text) so
# these only ever insert new tags into already-escaped text - they can
# never reinterpret message content as raw HTML. Matches Slack's own
# constraint that the mark must hug non-whitespace content (so "5 * 3"
# doesn't become bold) and, for italics, sit at a word boundary (so
# "f3_pugetsound" doesn't become partly italic). Not a full mrkdwn parser
# (no nesting, no lists/blockquotes) - good enough for a plain-text-safe
# report, not pixel-perfect Slack rendering.
_CODE_BLOCK_RE = re.compile(r"```([^`]+?)```", re.S)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*(\S(?:[^*\n]*\S)?)\*")
_STRIKE_RE = re.compile(r"~(\S(?:[^~\n]*\S)?)~")
_ITALIC_RE = re.compile(r"(?<![\w_])_(\S(?:[^_\n]*\S)?)_(?![\w_])")


def _render_mrkdwn(escaped_text: str) -> str:
    text = _CODE_BLOCK_RE.sub(lambda m: f"<code>{m.group(1)}</code>", escaped_text)
    text = _INLINE_CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", text)
    text = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = _STRIKE_RE.sub(lambda m: f"<del>{m.group(1)}</del>", text)
    text = _ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", text)
    return text


def _render_text(txt: str | None) -> str:
    """Slack's raw TXT already HTML-entity-escapes bare '&' etc, but
    leaves its own <@U..|name>/<#C..>/<url|label> mention/link syntax as
    literal, unescaped angle brackets (Slack mrkdwn syntax, not HTML).
    Decode that partial escaping back to raw text first, then escape the
    whole string uniformly exactly once - mentions/links render as escaped
    literal text, not resolved names. Slack's basic mrkdwn marks
    (*bold*/_italic_/~strike~/`code`) are then rendered as real HTML tags
    on top of the escaped text - this is plain-text-safe, not a full
    mrkdwn-to-HTML renderer."""
    text = txt or ""
    for entity, raw in _MENTION_UNESCAPE:
        text = text.replace(entity, raw)
    return _render_mrkdwn(html.escape(text))


def render_messages_html(results: list[dict], query_label: str) -> str:
    ordered = sorted(results, key=lambda r: float(r["ts"]), reverse=True)

    if not ordered:
        body = '<p class="empty">No results.</p>'
    else:
        blocks = []
        for r in ordered:
            when = datetime.fromtimestamp(float(r["ts"]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            channel_display = html.escape(r.get("channel_name") or r["channel_id"])
            ws_display = html.escape(r["workspace"])
            permalink_href = html.escape(r.get("permalink") or "")
            blocks.append(
                f'<div class="msg"><div class="meta"><span class="when">{when}</span> '
                f'<a class="channel" href="https://{r["workspace"]}.slack.com/archives/{r["channel_id"]}">'
                f'#{channel_display}</a> '
                f'<span class="ws">({ws_display})</span> '
                f'<a class="permalink" href="{permalink_href}">view in Slack ↗</a></div>'
                f'<pre class="text">{_render_text(r.get("txt"))}</pre></div>'
            )
        body = "\n".join(blocks)

    escaped_label = html.escape(query_label)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Slack search: {escaped_label}</title>
<style>
body {{ font-family: sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; }}
h1 {{ font-size: 1.2em; }}
.msg {{ border-bottom: 1px solid #ddd; padding: 1em 0; }}
.meta {{ color: #555; font-size: 0.9em; margin-bottom: 0.3em; }}
.when {{ font-weight: bold; }}
.ws {{ color: #888; }}
.text {{ white-space: pre-wrap; font-family: inherit; margin: 0; }}
a {{ color: #1264a3; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.empty {{ color: #888; }}
</style>
</head><body>
<h1>Slack search: {escaped_label}</h1>
<p class="count">{len(ordered)} result(s), most recent first.</p>
{body}
</body></html>
"""
