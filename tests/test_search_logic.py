"""Ports every scenario from scripts/test_search_messages.sh (since
removed - this is now the only test coverage) plus the workspace-selection
logic that's new in the Python port (the .sh version always searched every
f3*-prefixed workspace; this version takes the workspace/glob as an
argument instead).
"""
import json
import sqlite3

import pytest

from slackbackup import search_logic, workspace_logic


def test_select_workspaces_exact_name_match(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({"f3pugetsound": "xoxc-a", "f3kirkland": "xoxc-b"}))
    monkeypatch.setattr(
        workspace_logic.slackdump, "workspace_list",
        lambda: "f3pugetsound (file: ..., last modified: 2026-01-01)\n",
    )

    matched = search_logic.select_workspaces("f3pugetsound", tokens_file)

    assert [w["name"] for w in matched] == ["f3pugetsound"]
    assert matched[0]["registered"] is True


def test_select_workspaces_glob_excludes_others(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({
        "f3pugetsound": "xoxc-a", "f3kirkland": "xoxc-b", "dungeons-of-finn-hill": "xoxc-c",
    }))
    monkeypatch.setattr(workspace_logic.slackdump, "workspace_list", lambda: "")

    matched = search_logic.select_workspaces("f3*", tokens_file)

    assert {w["name"] for w in matched} == {"f3pugetsound", "f3kirkland"}


def test_select_workspaces_accepts_comma_separated_list(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({
        "f3pugetsound": "xoxc-a", "f3kirkland": "xoxc-b", "dungeons-of-finn-hill": "xoxc-c",
    }))
    monkeypatch.setattr(workspace_logic.slackdump, "workspace_list", lambda: "")

    matched = search_logic.select_workspaces("f3pugetsound,f3kirkland", tokens_file)

    assert {w["name"] for w in matched} == {"f3pugetsound", "f3kirkland"}


def test_search_messages_skips_unregistered_and_collects_registered(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({"f3pugetsound": "xoxc-a", "f3kirkland": "xoxc-b"}))
    monkeypatch.setattr(
        workspace_logic.slackdump, "workspace_list",
        lambda: "f3pugetsound (file: ..., last modified: 2026-01-01)\n",
    )

    selected_workspaces = []

    def fake_select(workspace):
        selected_workspaces.append(workspace)

    def fake_search(query_terms, out_dir):
        db = out_dir / "slackdump.sqlite"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE SEARCH_MESSAGE (CHANNEL_ID TEXT, CHANNEL_NAME TEXT, TS TEXT, TXT TEXT, DATA TEXT)")
        conn.execute(
            "INSERT INTO SEARCH_MESSAGE VALUES (?, ?, ?, ?, ?)",
            ("C1", "general", "1700000000.000000", "hello", json.dumps({"permalink": "https://x/p1"})),
        )
        conn.commit()
        conn.close()
        return True

    results, skipped = search_logic.search_messages(
        "f3*", ["hello"], fake_search, fake_select, tokens_file,
    )

    assert selected_workspaces == ["f3pugetsound"]  # f3kirkland skipped, never selected
    assert skipped == ["f3kirkland"]
    assert len(results) == 1
    assert results[0] == {
        "workspace": "f3pugetsound", "channel_id": "C1", "channel_name": "general",
        "ts": "1700000000.000000", "txt": "hello", "permalink": "https://x/p1",
    }


def test_search_messages_no_match_raises(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({"f3pugetsound": "xoxc-a"}))
    monkeypatch.setattr(workspace_logic.slackdump, "workspace_list", lambda: "")

    with pytest.raises(search_logic.NoWorkspaceMatchError):
        search_logic.search_messages("f3nonexistent", ["x"], lambda *a: True, lambda *a: None, tokens_file)


RESULTS = [
    {"workspace": "f3tundra", "channel_id": "C1", "channel_name": "general",
     "ts": "1700000000.000000", "txt": "older message", "permalink": "https://x/p1"},
    {"workspace": "f3kirkland", "channel_id": "C2", "channel_name": "chat",
     "ts": "1800000000.000000", "txt": "newer &amp; stuff <@U123|name>", "permalink": "https://x/p2"},
]


def test_render_html_includes_query_in_title():
    assert "Slack search: test query" in search_logic.render_messages_html(RESULTS, "test query")


def test_render_html_result_count():
    assert "2 result(s)" in search_logic.render_messages_html(RESULTS, "test query")


def test_render_html_channel_link_built_from_workspace_and_channel_id():
    html_doc = search_logic.render_messages_html(RESULTS, "test query")
    assert 'href="https://f3kirkland.slack.com/archives/C2"' in html_doc


def test_render_html_permalink_rendered():
    html_doc = search_logic.render_messages_html(RESULTS, "test query")
    assert 'href="https://x/p2"' in html_doc


def test_render_html_preescaped_ampersand_not_double_escaped():
    html_doc = search_logic.render_messages_html(RESULTS, "test query")
    assert "newer &amp; stuff" in html_doc
    assert "&amp;amp;" not in html_doc


def test_render_html_mention_syntax_escaped_not_left_as_literal_tag():
    html_doc = search_logic.render_messages_html(RESULTS, "test query")
    assert "&lt;@U123|name&gt;" in html_doc
    assert "<@U123|name>" not in html_doc


def test_render_html_most_recent_first():
    html_doc = search_logic.render_messages_html(RESULTS, "test query")
    assert html_doc.index('href="https://x/p2"') < html_doc.index('href="https://x/p1"')


def test_render_html_empty_results():
    html_doc = search_logic.render_messages_html([], "no matches query")
    assert "No results" in html_doc
    assert "0 result(s)" in html_doc


def test_render_html_missing_channel_name_falls_back_to_channel_id():
    results = [{"workspace": "f3tundra", "channel_id": "C3", "channel_name": None,
                "ts": "1700000000.000000", "txt": "x", "permalink": "https://x/p3"}]
    html_doc = search_logic.render_messages_html(results, "fallback test")
    assert ">#C3<" in html_doc


def _text_of(html_doc: str) -> str:
    start = html_doc.index('<pre class="text">') + len('<pre class="text">')
    end = html_doc.index("</pre>", start)
    return html_doc[start:end]


def _doc_for(txt: str) -> str:
    results = [{"workspace": "f3tundra", "channel_id": "C1", "channel_name": "general",
                "ts": "1700000000.000000", "txt": txt, "permalink": "https://x/p1"}]
    return search_logic.render_messages_html(results, "mrkdwn test")


def test_mrkdwn_bold_renders_as_strong():
    assert "<strong>Backblast! Borderlands - MONOPOLY (maybe)</strong>" in _text_of(
        _doc_for("*Backblast! Borderlands - MONOPOLY (maybe)*")
    )


def test_mrkdwn_bold_does_not_fire_on_bare_asterisk_math():
    text = _text_of(_doc_for("5 * 3 = 15"))
    assert "<strong>" not in text
    assert "5 * 3 = 15" in text


def test_mrkdwn_italic_renders_as_em():
    assert "<em>so good</em>" in _text_of(_doc_for("that was _so good_ today"))


def test_mrkdwn_italic_does_not_fire_mid_word():
    text = _text_of(_doc_for("check f3_pugetsound_archive please"))
    assert "<em>" not in text


def test_mrkdwn_strikethrough_renders_as_del():
    assert "<del>cancelled</del>" in _text_of(_doc_for("~cancelled~ moved to next week"))


def test_mrkdwn_inline_code_renders_as_code():
    assert "<code>slackdump archive</code>" in _text_of(_doc_for("run `slackdump archive` first"))


def test_mrkdwn_code_block_renders_as_code():
    assert "<code>line1\nline2</code>" in _text_of(_doc_for("```line1\nline2```"))


def test_mrkdwn_does_not_reinterpret_mention_syntax_as_html():
    # *bold* around a mention should still escape the mention's angle
    # brackets, not let them leak through as a raw tag once <strong> is
    # inserted around them.
    text = _text_of(_doc_for("*hey <@U123|name>*"))
    assert "<strong>hey &lt;@U123|name&gt;</strong>" in text
    assert "<@U123|name>" not in text
