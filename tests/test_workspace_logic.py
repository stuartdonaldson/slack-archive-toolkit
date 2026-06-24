import json

import pytest

from slackbackup import workspace_logic


REAL_LIST_OUTPUT = """Workspaces in "/home/user/.cache/slackdump":

   dungeons-of-finn-hill (file: dungeons-of-finn-hill.bin, last modified: 2026-06-21 07:29:39)
   f3cascades (file: f3cascades.bin, last modified: 2026-06-21 07:45:26)
   f3kirkland.slack.com (file: f3kirkland.slack.com.bin, last modified: 2026-06-20 22:09:12)
=> f3tundra (file: f3tundra.bin, last modified: 2026-06-22 22:30:48)

Current workspace is marked with ' => '.
"""


def test_normalize_strips_scheme_and_slack_com_suffix():
    assert workspace_logic.normalize("https://F3Kirkland.slack.com") == "f3kirkland"
    assert workspace_logic.normalize("f3kirkland") == "f3kirkland"
    assert workspace_logic.normalize("F3KIRKLAND.SLACK.COM") == "f3kirkland"


def test_parse_registered_extracts_name_current_and_timestamp():
    registered = workspace_logic.parse_registered(REAL_LIST_OUTPUT)
    assert registered["f3cascades"]["current"] is False
    assert registered["f3cascades"]["last_modified"] == "2026-06-21 07:45:26"
    assert registered["f3tundra"]["current"] is True


def test_parse_registered_strips_slack_com_suffix_from_name():
    registered = workspace_logic.parse_registered(REAL_LIST_OUTPUT)
    assert "f3kirkland" in registered
    assert "f3kirkland.slack.com" not in registered


def test_status_distinguishes_known_registered_and_others(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({"f3cascades": "xoxc-a", "f3seattle": "xoxc-b"}))
    monkeypatch.setattr(workspace_logic.slackdump, "workspace_list", lambda: REAL_LIST_OUTPUT)

    result = workspace_logic.status(tokens_file)
    by_name = {row["name"]: row for row in result["known"]}

    assert by_name["f3cascades"]["registered"] is True
    assert by_name["f3seattle"]["registered"] is False
    assert "dungeons-of-finn-hill" in result["others"]


def test_register_uses_token_and_calls_workspace_import(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({"f3tundra": "xoxc-secret"}))

    captured = {}

    def fake_import(env_file):
        captured["content"] = env_file.read_text()

    monkeypatch.setattr(workspace_logic.slackdump, "workspace_import", fake_import)

    workspace = workspace_logic.register("F3Tundra.slack.com", "xoxd-cookie", tokens_file)

    assert workspace == "f3tundra"
    assert "SLACK_TOKEN=xoxc-secret" in captured["content"]
    assert "SLACK_COOKIE=xoxd-cookie" in captured["content"]


def test_register_raises_when_no_token_on_file(tmp_path):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({"f3cascades": "xoxc-a"}))

    with pytest.raises(workspace_logic.WorkspaceError, match="no token found"):
        workspace_logic.register("f3tundra", "xoxd-cookie", tokens_file)


def test_status_raises_when_tokens_file_missing(tmp_path):
    with pytest.raises(workspace_logic.WorkspaceError, match="tokens file not found"):
        workspace_logic.status(tmp_path / "nonexistent.json")
