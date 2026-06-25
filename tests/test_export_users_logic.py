"""Tests for the full per-workspace user-profile export - everyone
slackdump has cached, not just digest posters (see test_export_digest_logic.py
for the "is identity scoped per-workspace" reasoning this builds on).
"""
import json
import shutil
from pathlib import Path

from slackbackup import export_logic

FIXTURE = Path(__file__).parent.parent / "scripts" / "test_fixtures" / "export-archive"


def _fake_convert(channel_dir: Path, out_dir: Path) -> None:
    shutil.copytree(FIXTURE / "helpdesk", out_dir / "helpdesk")
    shutil.copy(FIXTURE / "users.json", out_dir / "users.json")


def test_clean_user_strips_noise_and_resolves_display_name():
    raw = {
        "id": "U0A", "name": "alice.a", "real_name": "Alice Anderson", "is_bot": False,
        "deleted": False, "profile": {"display_name": "Al", "email": "alice@example.com"},
    }
    cleaned = export_logic._clean_user(raw)
    assert cleaned == {
        "id": "U0A", "name": "alice.a", "real_name": "Alice Anderson",
        "display_name": "Al", "deleted": False, "slack_roles": [],
    }


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
    archive_root = tmp_path / "archive"
    for ws in ("f3pugetsound", "f3kirkland"):
        channel_dir = archive_root / ws / "helpdesk"
        channel_dir.mkdir(parents=True)
        (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "helpdesk", "workspace": "f3kirkland"},
        {"id": "C3", "name": "ai-coding", "workspace": "dungeons-of-finn-hill"},
    ]))

    result = export_logic.build_user_profiles(channels_file, archive_root, "f3*", _fake_convert)

    assert result["schema_version"] == "slack-user-profiles-v1"
    workspaces = {w["workspace"]: w for w in result["workspaces"]}
    assert set(workspaces) == {"f3pugetsound", "f3kirkland"}
    assert workspaces["f3pugetsound"]["status"] == "ok"
    assert {p["id"] for p in workspaces["f3pugetsound"]["profiles"]} == {"U0A", "U0B", "U0C", "U0D"}


def test_build_user_profiles_missing_archive_per_workspace(tmp_path):
    archive_root = tmp_path / "archive"  # no channel dirs created

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    result = export_logic.build_user_profiles(channels_file, archive_root, "f3*", _fake_convert)

    assert result["workspaces"] == [{"workspace": "f3pugetsound", "status": "missing_archive", "profiles": []}]


def test_build_user_profiles_only_converts_one_channel_per_workspace(tmp_path):
    """Two archived channels in the same workspace - users.json is
    workspace-scoped, so only the first archived channel should get
    converted, not both."""
    archive_root = tmp_path / "archive"
    converted = []

    def counting_convert(channel_dir: Path, out_dir: Path) -> None:
        converted.append(channel_dir.name)
        _fake_convert(channel_dir, out_dir)

    for name in ("helpdesk", "mumblechatter"):
        channel_dir = archive_root / "f3pugetsound" / name
        channel_dir.mkdir(parents=True)
        (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "mumblechatter", "workspace": "f3pugetsound"},
    ]))

    export_logic.build_user_profiles(channels_file, archive_root, "f3*", counting_convert)
    assert converted == ["helpdesk"]
