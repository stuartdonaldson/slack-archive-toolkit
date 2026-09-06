"""Tests for the full per-workspace user-profile export - everyone
slackdump has cached, not just digest posters (see test_export_digest_logic.py
for the "is identity scoped per-workspace" reasoning this builds on).
"""
import json
from pathlib import Path

from slackbackup import export_logic
from slackbackup.slackdump import SlackdumpError

FIXTURE = Path(__file__).parent.parent / "scripts" / "test_fixtures" / "export-archive"
_FIXTURE_USERS = json.loads((FIXTURE / "users.json").read_text())


def test_clean_user_strips_noise_and_resolves_display_name():
    raw = {
        "id": "U0A", "name": "alice.a", "real_name": "Alice Anderson", "is_bot": False,
        "deleted": False, "profile": {"display_name": "Al", "email": "alice@example.com"},
    }
    cleaned = export_logic._clean_user(raw)
    import hashlib
    assert cleaned == {
        "id": "U0A", "name": "alice.a", "real_name": "Alice Anderson",
        "display_name": "Al", "title": None, "deleted": False, "slack_roles": [],
        "email_hash": hashlib.sha256(b"alice@example.com").hexdigest()[:12],
    }
    assert "alice@example.com" not in json.dumps(cleaned)


def test_clean_user_includes_title_when_present():
    raw = {
        "id": "U0X", "name": "combine", "real_name": "Combine", "deleted": False,
        "profile": {"display_name": "Combine", "title": "Redmond Ridge Site Q, Redmond Comz Q"},
    }
    cleaned = export_logic._clean_user(raw)
    assert cleaned["title"] == "Redmond Ridge Site Q, Redmond Comz Q"


def test_clean_user_collects_slack_roles():
    raw = {
        "id": "U0Z", "name": "zoe.z", "real_name": "Zoe Z", "deleted": False,
        "profile": {"display_name": "Zoe"}, "is_admin": True, "is_owner": True, "is_primary_owner": False,
    }
    cleaned = export_logic._clean_user(raw)
    assert cleaned["slack_roles"] == ["owner", "admin"]


def test_clean_user_bot_is_a_slack_role():
    raw = {"id": "U0BOT", "name": "bot", "real_name": "Bot", "deleted": False, "is_bot": True, "profile": {}}
    cleaned = export_logic._clean_user(raw)
    assert cleaned["slack_roles"] == ["bot"]


def test_clean_user_restricted_and_app_user_roles():
    raw = {
        "id": "U0R", "name": "guest", "real_name": "Guest", "deleted": False,
        "is_restricted": True, "is_app_user": True, "profile": {},
    }
    cleaned = export_logic._clean_user(raw)
    assert set(cleaned["slack_roles"]) == {"restricted", "app_user"}


def test_clean_user_empty_display_name_becomes_none():
    raw = {"id": "U0B", "name": "bob.b", "real_name": "Bob Baker", "profile": {"display_name": ""}}
    cleaned = export_logic._clean_user(raw)
    assert cleaned["display_name"] is None


def test_build_user_profiles_groups_by_workspace(tmp_path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "helpdesk", "workspace": "f3kirkland"},
        {"id": "C3", "name": "ai-coding", "workspace": "dungeons-of-finn-hill"},
    ]))

    result = export_logic.build_user_profiles(channels_file, "f3*", lambda ws: _FIXTURE_USERS)

    assert result["schema_version"] == "slack-user-profiles-v1"
    workspaces = {w["workspace"]: w for w in result["workspaces"]}
    assert set(workspaces) == {"f3pugetsound", "f3kirkland"}
    assert workspaces["f3pugetsound"]["status"] == "ok"
    assert {p["id"] for p in workspaces["f3pugetsound"]["profiles"]} == {u["id"] for u in _FIXTURE_USERS}


def test_build_user_profiles_calls_list_users_once_per_matched_workspace(tmp_path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "mumblechatter", "workspace": "f3pugetsound"},
        {"id": "C3", "name": "helpdesk", "workspace": "f3kirkland"},
    ]))

    calls = []

    def fake_list_users(workspace):
        calls.append(workspace)
        return _FIXTURE_USERS

    export_logic.build_user_profiles(channels_file, "f3*", fake_list_users)
    assert calls == ["f3kirkland", "f3pugetsound"]


def test_build_user_profiles_list_users_failure_marks_workspace_error(tmp_path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "helpdesk", "workspace": "f3kirkland"},
    ]))

    def flaky_list_users(workspace):
        if workspace == "f3kirkland":
            raise SlackdumpError("session expired")
        return _FIXTURE_USERS

    result = export_logic.build_user_profiles(channels_file, "f3*", flaky_list_users)

    workspaces = {w["workspace"]: w for w in result["workspaces"]}
    assert workspaces["f3pugetsound"]["status"] == "ok"
    assert workspaces["f3kirkland"] == {"workspace": "f3kirkland", "status": "error", "profiles": []}
