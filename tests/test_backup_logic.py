import json
import sqlite3
import re

import pytest

from slackbackup import backup_logic, channel_logic, slackdump


def _make_db(path, message_count):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE MESSAGE (ts TEXT)")
    for i in range(message_count):
        conn.execute("INSERT INTO MESSAGE (ts) VALUES (?)", (f"170000000{i}.000000",))
    conn.commit()
    conn.close()


def test_channel_dir_keys_by_workspace_and_slug(tmp_path):
    d = backup_logic.channel_dir(tmp_path, "f3test", "general")
    assert d == tmp_path / "f3test" / "general"


def test_backup_channel_archives_when_no_existing_db(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: calls.append(("archive", cid, out)))
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: calls.append(("resume", d)))

    archive_root = tmp_path / "archive"
    kind = backup_logic.backup_channel("C1", "general", "f3test", archive_root, cache_dir=tmp_path / "cache")

    assert calls == [("archive", "C1", archive_root / "f3test" / "general")]
    assert kind == "archive"


def test_backup_channel_resumes_when_db_already_exists(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    channel_directory = archive_root / "f3test" / "general"
    channel_directory.mkdir(parents=True)
    _make_db(channel_directory / "slackdump.sqlite", message_count=5)

    calls = []
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: calls.append(("archive", cid, out)))
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: calls.append(("resume", d)))

    kind = backup_logic.backup_channel("C1", "general", "f3test", archive_root, cache_dir=tmp_path / "cache")

    assert calls == [("resume", channel_directory)]
    assert kind == "resume"


def test_backup_channel_wipes_and_rearchives_when_existing_db_has_zero_messages(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    channel_directory = archive_root / "f3test" / "all-pax"
    channel_directory.mkdir(parents=True)
    db_path = channel_directory / "slackdump.sqlite"
    _make_db(db_path, message_count=0)
    (channel_directory / "leftover-attachment.txt").write_text("stale")

    calls = []
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: calls.append(("archive", cid, out)))
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: calls.append(("resume", d)))

    kind = backup_logic.backup_channel(
        "C77PPNCUT", "all-pax", "f3test", archive_root, cache_dir=tmp_path / "cache"
    )

    assert calls == [("archive", "C77PPNCUT", channel_directory)]
    assert kind == "archive"
    assert not (channel_directory / "leftover-attachment.txt").exists()  # stale dir wiped, not archived-on-top-of


def test_backup_channel_wipes_and_rearchives_when_existing_db_is_unreadable(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    channel_directory = archive_root / "f3test" / "general"
    channel_directory.mkdir(parents=True)
    (channel_directory / "slackdump.sqlite").write_text("not a sqlite file")

    calls = []
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: calls.append(("archive", cid, out)))
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: calls.append(("resume", d)))

    kind = backup_logic.backup_channel("C1", "general", "f3test", archive_root, cache_dir=tmp_path / "cache")

    assert calls == [("archive", "C1", channel_directory)]
    assert kind == "archive"


def test_backup_channel_full_resync_always_archives_into_a_fresh_dated_dir(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    channel_directory = archive_root / "f3test" / "general"
    channel_directory.mkdir(parents=True)
    (channel_directory / "slackdump.sqlite").touch()

    calls = []
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: calls.append(("archive", cid, out)))
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: calls.append(("resume", d)))

    kind = backup_logic.backup_channel(
        "C1", "general", "f3test", archive_root, full=True, cache_dir=tmp_path / "cache"
    )

    assert kind == "archive"
    assert len(calls) == 1
    call_kind, cid, out_dir = calls[0]
    assert call_kind == "archive"
    assert cid == "C1"
    assert out_dir != channel_directory  # fresh dir, not the incremental one
    assert out_dir.parent == archive_root / "f3test"
    assert out_dir.name.startswith("general-full-")


def test_backup_channel_updates_last_posted_after_successful_resume(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    cache_dir = tmp_path / "cache"
    channel_directory = archive_root / "f3test" / "general"
    channel_directory.mkdir(parents=True)
    db_path = channel_directory / "slackdump.sqlite"
    _make_db(db_path, message_count=3)  # ts values 1700000000.000000 .. 1700000002.000000
    backup_logic.catalog_logic.save(
        cache_dir, "f3test",
        {"channels": {"C1": {"member": True, "name": "general", "description": ""}},
         "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )

    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: None)

    backup_logic.backup_channel("C1", "general", "f3test", archive_root, cache_dir=cache_dir)

    catalog = backup_logic.catalog_logic.load(cache_dir, "f3test")
    assert catalog["channels"]["C1"]["last_posted"] is not None


def test_backup_channel_does_not_update_last_posted_when_archive_stays_empty(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    cache_dir = tmp_path / "cache"
    backup_logic.catalog_logic.save(
        cache_dir, "f3test",
        {"channels": {"C1": {"member": True, "name": "general", "description": ""}},
         "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )

    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: None)  # never writes a db - stays "empty"

    backup_logic.backup_channel("C1", "general", "f3test", archive_root, cache_dir=cache_dir)

    catalog = backup_logic.catalog_logic.load(cache_dir, "f3test")
    assert "last_posted" not in catalog["channels"]["C1"]


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
    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: warmed.append(ws))
    monkeypatch.setattr(backup_logic, "backup_channel", lambda *a, **kw: "archive")

    backup_logic.run(channels_file, tmp_path / "archive", cache_dir=tmp_path / "cache")

    assert sorted(warmed) == ["f3a", "f3b"]


def test_run_continues_on_per_channel_failure_and_reports_overall_failure(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "good", "workspace": "f3a"},
        {"id": "C2", "name": "bad", "workspace": "f3a"},
        {"id": "C3", "name": "also-good", "workspace": "f3a"},
    ]))

    attempted = []

    def fake_backup_channel(channel_id, slug, workspace, archive_root, full=False, cache_dir=None):
        attempted.append(slug)
        if slug == "bad":
            raise slackdump.SlackdumpError("boom")
        return "archive"

    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    monkeypatch.setattr(backup_logic, "backup_channel", fake_backup_channel)

    all_ok = backup_logic.run(channels_file, tmp_path / "archive", cache_dir=tmp_path / "cache")

    assert attempted == ["good", "bad", "also-good"]  # all attempted despite the failure
    assert all_ok is False


def test_run_processes_most_recently_active_channels_first(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "stale", "workspace": "f3a"},
        {"id": "C2", "name": "fresh", "workspace": "f3a"},
        {"id": "C3", "name": "middling", "workspace": "f3a"},
    ]))
    backup_logic.catalog_logic.save(
        cache_dir, "f3a",
        {
            "channels": {
                "C1": {"member": True, "name": "stale", "last_posted": "2020-01-01T00:00:00Z"},
                "C2": {"member": True, "name": "fresh", "last_posted": "2026-06-20T00:00:00Z"},
                "C3": {"member": True, "name": "middling", "registered_at": "2025-01-01T00:00:00Z"},
            },
            "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0,
        },
    )

    attempted = []
    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    monkeypatch.setattr(
        backup_logic, "backup_channel",
        lambda cid, slug, ws, root, full=False, cache_dir=None: attempted.append(slug) or "resume",
    )

    backup_logic.run(channels_file, tmp_path / "archive", cache_dir=cache_dir)

    assert attempted == ["fresh", "middling", "stale"]


def test_interleave_by_workspace_alternates_across_evenly_sized_groups():
    entries = [
        {"id": "C1", "name": "a1", "workspace": "f3a"},
        {"id": "C2", "name": "a2", "workspace": "f3a"},
        {"id": "C3", "name": "b1", "workspace": "f3b"},
        {"id": "C4", "name": "b2", "workspace": "f3b"},
    ]
    result = backup_logic._interleave_by_workspace(entries)
    workspaces = [e["workspace"] for e in result]
    assert workspaces[0] != workspaces[1]
    assert workspaces[2] != workspaces[3]
    assert sorted(workspaces) == ["f3a", "f3a", "f3b", "f3b"]


def test_interleave_by_workspace_preserves_recency_order_within_a_workspace():
    entries = [
        {"id": "A1", "name": "a-fresh", "workspace": "f3a"},
        {"id": "A2", "name": "a-stale", "workspace": "f3a"},
        {"id": "B1", "name": "b-only", "workspace": "f3b"},
    ]
    result = backup_logic._interleave_by_workspace(entries)
    a_order = [e["name"] for e in result if e["workspace"] == "f3a"]
    assert a_order == ["a-fresh", "a-stale"]


def test_interleave_by_workspace_only_repeats_a_workspace_when_no_alternative():
    entries = (
        [{"id": f"A{i}", "name": f"a{i}", "workspace": "f3a"} for i in range(5)]
        + [{"id": "B1", "name": "b1", "workspace": "f3b"}]
    )
    result = backup_logic._interleave_by_workspace(entries)
    workspaces = [e["workspace"] for e in result]
    # f3b (the only other workspace) gets used immediately, then f3a runs
    # out the rest since there's nothing left to alternate with.
    assert workspaces[1] == "f3b"
    assert workspaces[2:] == ["f3a"] * 4


def test_interleave_by_workspace_handles_single_workspace_as_passthrough():
    entries = [
        {"id": "C1", "name": "fresh", "workspace": "f3a"},
        {"id": "C2", "name": "stale", "workspace": "f3a"},
    ]
    assert backup_logic._interleave_by_workspace(entries) == entries


def test_run_interleaves_across_workspaces_instead_of_draining_one_first(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "A1", "name": "a1", "workspace": "f3a"},
        {"id": "A2", "name": "a2", "workspace": "f3a"},
        {"id": "B1", "name": "b1", "workspace": "f3b"},
        {"id": "B2", "name": "b2", "workspace": "f3b"},
    ]))

    attempted_workspaces = []
    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    monkeypatch.setattr(
        backup_logic, "backup_channel",
        lambda cid, slug, ws, root, full=False, cache_dir=None: attempted_workspaces.append(ws) or "archive",
    )

    backup_logic.run(channels_file, tmp_path / "archive", cache_dir=cache_dir)

    assert attempted_workspaces[0] != attempted_workspaces[1]


def test_run_logs_a_final_summary(tmp_path, monkeypatch, capsys):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3a"}]))

    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    monkeypatch.setattr(backup_logic, "backup_channel", lambda *a, **kw: "resume")

    backup_logic.run(channels_file, tmp_path / "archive", cache_dir=tmp_path / "cache")

    out = capsys.readouterr().out
    assert "done - 1 channel(s), 0 archive(s), 1 resume(s), 0 failure(s)" in out


def test_run_log_lines_are_timestamped(tmp_path, monkeypatch, capsys):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3a"}]))

    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    monkeypatch.setattr(backup_logic, "backup_channel", lambda *a, **kw: "resume")

    backup_logic.run(channels_file, tmp_path / "archive", cache_dir=tmp_path / "cache")

    out = capsys.readouterr().out
    first_line = out.splitlines()[0]
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z backup run: backing up", first_line)


def test_sync_catalog_from_local_sets_last_posted_when_archive_has_data(tmp_path):
    archive_root = tmp_path / "archive"
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3a"}]))

    channel_directory = archive_root / "f3a" / "general"
    channel_directory.mkdir(parents=True)
    _make_db(channel_directory / "slackdump.sqlite", message_count=3)
    backup_logic.catalog_logic.save(
        cache_dir, "f3a",
        {"channels": {"C1": {"member": True, "name": "general"}}, "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )

    counts = backup_logic.sync_catalog_from_local(channels_file, archive_root, cache_dir=cache_dir)

    catalog = backup_logic.catalog_logic.load(cache_dir, "f3a")
    assert catalog["channels"]["C1"]["last_posted"] is not None
    assert counts == {"last_posted": 1, "registered_at": 0, "total": 1}


def test_sync_catalog_from_local_stamps_registered_at_when_no_data(tmp_path):
    archive_root = tmp_path / "archive"
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3a"}]))
    backup_logic.catalog_logic.save(
        cache_dir, "f3a",
        {"channels": {"C1": {"member": True, "name": "general"}}, "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )

    counts = backup_logic.sync_catalog_from_local(channels_file, archive_root, cache_dir=cache_dir)

    catalog = backup_logic.catalog_logic.load(cache_dir, "f3a")
    assert catalog["channels"]["C1"]["registered_at"] is not None
    assert "last_posted" not in catalog["channels"]["C1"]
    assert counts == {"last_posted": 0, "registered_at": 1, "total": 1}


def test_sync_catalog_from_local_does_not_overwrite_existing_registered_at(tmp_path):
    archive_root = tmp_path / "archive"
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3a"}]))
    backup_logic.catalog_logic.save(
        cache_dir, "f3a",
        {
            "channels": {"C1": {"member": True, "name": "general", "registered_at": "2020-01-01T00:00:00Z"}},
            "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0,
        },
    )

    backup_logic.sync_catalog_from_local(channels_file, archive_root, cache_dir=cache_dir)

    catalog = backup_logic.catalog_logic.load(cache_dir, "f3a")
    assert catalog["channels"]["C1"]["registered_at"] == "2020-01-01T00:00:00Z"
