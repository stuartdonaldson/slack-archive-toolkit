import json

import pytest

from slackbackup import backup_logic, channel_logic, slackdump


def test_channel_dir_keys_by_workspace_and_slug(tmp_path):
    d = backup_logic.channel_dir(tmp_path, "f3test", "general")
    assert d == tmp_path / "f3test" / "general"


def test_backup_channel_archives_when_no_existing_db(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: calls.append(("archive", cid, out)))
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: calls.append(("resume", d)))

    archive_root = tmp_path / "archive"
    backup_logic.backup_channel("C1", "general", "f3test", archive_root)

    assert calls == [("archive", "C1", archive_root / "f3test" / "general")]


def test_backup_channel_resumes_when_db_already_exists(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    channel_directory = archive_root / "f3test" / "general"
    channel_directory.mkdir(parents=True)
    (channel_directory / "slackdump.sqlite").touch()

    calls = []
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: calls.append(("archive", cid, out)))
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: calls.append(("resume", d)))

    backup_logic.backup_channel("C1", "general", "f3test", archive_root)

    assert calls == [("resume", channel_directory)]


def test_backup_channel_full_resync_always_archives_into_a_fresh_dated_dir(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    channel_directory = archive_root / "f3test" / "general"
    channel_directory.mkdir(parents=True)
    (channel_directory / "slackdump.sqlite").touch()

    calls = []
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: calls.append(("archive", cid, out)))
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: calls.append(("resume", d)))

    backup_logic.backup_channel("C1", "general", "f3test", archive_root, full=True)

    assert len(calls) == 1
    kind, cid, out_dir = calls[0]
    assert kind == "archive"
    assert cid == "C1"
    assert out_dir != channel_directory  # fresh dir, not the incremental one
    assert out_dir.parent == archive_root / "f3test"
    assert out_dir.name.startswith("general-full-")


def test_run_validates_first_and_raises_on_invalid_channels_file(tmp_path):
    bad_file = tmp_path / "channels.json"
    bad_file.write_text("[]")
    with pytest.raises(channel_logic.ChannelError):
        backup_logic.run(bad_file, tmp_path / "archive")


def test_run_warms_fast_tier_catalog_once_per_distinct_workspace(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "general", "workspace": "f3a"},
        {"id": "C2", "name": "random", "workspace": "f3a"},
        {"id": "C3", "name": "general", "workspace": "f3b"},
    ]))

    warmed = []
    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws: warmed.append(ws))
    monkeypatch.setattr(backup_logic, "backup_channel", lambda *a, **kw: None)

    backup_logic.run(channels_file, tmp_path / "archive")

    assert sorted(warmed) == ["f3a", "f3b"]


def test_run_continues_on_per_channel_failure_and_reports_overall_failure(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "good", "workspace": "f3a"},
        {"id": "C2", "name": "bad", "workspace": "f3a"},
        {"id": "C3", "name": "also-good", "workspace": "f3a"},
    ]))

    attempted = []

    def fake_backup_channel(channel_id, slug, workspace, archive_root, full=False):
        attempted.append(slug)
        if slug == "bad":
            raise slackdump.SlackdumpError("boom")

    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws: None)
    monkeypatch.setattr(backup_logic, "backup_channel", fake_backup_channel)

    all_ok = backup_logic.run(channels_file, tmp_path / "archive")

    assert attempted == ["good", "bad", "also-good"]  # all attempted despite the failure
    assert all_ok is False
