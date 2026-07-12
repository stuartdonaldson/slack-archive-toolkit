import json
import sqlite3
import re
from datetime import date, timedelta

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


def test_backup_channel_writes_last_backup_stamp_on_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: None)
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: None)

    archive_root = tmp_path / "archive"
    backup_logic.backup_channel("C1", "general", "f3test", archive_root, cache_dir=tmp_path / "cache")

    stamp = (archive_root / "f3test" / "general" / ".last_backup").read_text().strip()
    # Must match the exact format the exporter parses (see export_logic).
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp)


def test_backup_channel_writes_last_backup_stamp_on_resume(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    channel_directory = archive_root / "f3test" / "general"
    channel_directory.mkdir(parents=True)
    _make_db(channel_directory / "slackdump.sqlite", message_count=5)

    monkeypatch.setattr(backup_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(backup_logic.slackdump, "archive", lambda cid, out: None)
    monkeypatch.setattr(backup_logic.slackdump, "resume", lambda d: None)

    backup_logic.backup_channel("C1", "general", "f3test", archive_root, cache_dir=tmp_path / "cache")

    stamp = (channel_directory / ".last_backup").read_text().strip()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp)


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


def test_run_skips_workspace_whose_catalog_refresh_fails_and_backs_up_the_rest(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "A1", "name": "a1", "workspace": "f3live"},
        {"id": "B1", "name": "b1", "workspace": "f3dead"},
        {"id": "A2", "name": "a2", "workspace": "f3live"},
    ]))

    def fake_refresh(ws, cache_dir=None):
        if ws == "f3dead":
            raise slackdump.SlackdumpError("authentication error: invalid_auth")

    attempted = []
    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", fake_refresh)
    monkeypatch.setattr(
        backup_logic, "backup_channel",
        lambda cid, slug, ws, root, full=False, cache_dir=None: attempted.append((ws, slug)) or "archive",
    )

    all_ok = backup_logic.run(channels_file, tmp_path / "archive", cache_dir=tmp_path / "cache")

    # one workspace's expired session must not abort the others
    assert ("f3live", "a1") in attempted and ("f3live", "a2") in attempted
    assert all(ws != "f3dead" for ws, _ in attempted)  # dead workspace's channels skipped
    assert all_ok is False  # but a skipped workspace marks the run not-ok


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
    assert "done - 1 channel(s), 0 archive(s), 1 resume(s), 0 not-due skip(s), 0 failure(s)" in out


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


# --- Tiered backup cadence (SlackBackup-2ut) ---

TODAY = date(2026, 7, 7)


def _iso_days_ago(today, days):
    return (today - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")


def test_cadence_days_active_channel_is_nightly():
    # posted 3 weeks ago -> youngest tier -> checked every night
    assert backup_logic._cadence_days_for_age(3.0) == 1


def test_cadence_days_empty_channel_uses_oldest_tier():
    # no recorded last activity -> oldest (longest) cadence
    oldest = backup_logic.BACKUP_CADENCE_TIERS[-1][1]
    assert backup_logic._cadence_days_for_age(None) == oldest


@pytest.mark.parametrize(
    "age_weeks,expected",
    [(0.0, 1), (5.0, 1), (7.9, 1), (8.0, 2), (10.0, 2), (11.9, 2), (12.0, 10), (30.0, 10)],
)
def test_cadence_tiers_boundaries(age_weeks, expected):
    assert backup_logic._cadence_days_for_age(age_weeks) == expected


def test_should_check_tonight_active_channel_always_due():
    record = {"last_posted": _iso_days_ago(TODAY, 7), "last_checked": _iso_days_ago(TODAY, 1)}
    assert backup_logic.should_check_tonight({"id": "C1"}, record, TODAY) is True


def test_should_check_tonight_dormant_skipped_on_non_due_night():
    # 20 weeks dormant -> 10-day cadence; find a channel id + today where the
    # stagger phase does NOT line up, and last_checked is recent enough that the
    # downtime backstop stays silent.
    record = {"last_posted": _iso_days_ago(TODAY, 20 * 7), "last_checked": _iso_days_ago(TODAY, 1)}
    skipped_any = any(
        backup_logic.should_check_tonight({"id": f"C{i}"}, record, TODAY) is False
        for i in range(50)
    )
    assert skipped_any  # at least some dormant channels are skipped on a given night


def test_should_check_tonight_dormant_due_when_last_checked_older_than_cadence():
    # backstop: never let a dormant channel drift past its cadence, regardless of stagger
    record = {"last_posted": _iso_days_ago(TODAY, 20 * 7), "last_checked": _iso_days_ago(TODAY, 11)}
    assert backup_logic.should_check_tonight({"id": "C1"}, record, TODAY) is True


def test_should_check_tonight_empty_never_checked_is_due():
    # empty channel, never checked -> must be picked up
    assert backup_logic.should_check_tonight({"id": "C1"}, {}, TODAY) is True


def test_should_check_tonight_staggers_tier_and_covers_within_cadence():
    cadence = backup_logic.BACKUP_CADENCE_TIERS[-1][1]  # oldest tier cadence
    ids = [f"C{i}" for i in range(100)]
    due_by_day = []
    seen_due = set()
    for offset in range(cadence):
        day = TODAY + timedelta(days=offset)
        # last_checked one day back each night so the backstop never fires -> pure stagger
        record = {"last_checked": (day - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")}
        due_today = {cid for cid in ids if backup_logic.should_check_tonight({"id": cid}, record, day)}
        due_by_day.append(len(due_today))
        seen_due |= due_today

    assert max(due_by_day) < len(ids)  # never the whole tier on one night
    assert seen_due == set(ids)  # every channel checked at least once within its cadence


def test_run_logs_per_workspace_progress_counter(tmp_path, monkeypatch, capsys):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "A1", "name": "a1", "workspace": "f3a"},
        {"id": "A2", "name": "a2", "workspace": "f3a"},
        {"id": "B1", "name": "b1", "workspace": "f3b"},
    ]))

    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    monkeypatch.setattr(backup_logic, "backup_channel", lambda *a, **kw: "archive")

    backup_logic.run(channels_file, tmp_path / "archive", cache_dir=tmp_path / "cache", today=TODAY)

    out = capsys.readouterr().out
    # f3a has two channels, f3b one - each workspace counts independently
    assert "backing up a1 (A1) in f3a [1/2 in f3a]" in out
    assert "backing up a2 (A2) in f3a [2/2 in f3a]" in out
    assert "backing up b1 (B1) in f3b [1/1 in f3b]" in out


def test_run_skips_dormant_channel_not_due_and_records_skip(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "dormant", "workspace": "f3a"}]))
    backup_logic.catalog_logic.save(
        cache_dir, "f3a",
        {
            "channels": {
                "C1": {
                    "member": True, "name": "dormant",
                    "last_posted": _iso_days_ago(TODAY, 20 * 7),
                    "last_checked": _iso_days_ago(TODAY, 1),
                }
            },
            "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0,
        },
    )

    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    # force this channel onto a non-due stagger night
    monkeypatch.setattr(backup_logic, "should_check_tonight", lambda entry, record, today: False)

    attempted = []
    monkeypatch.setattr(
        backup_logic, "backup_channel",
        lambda *a, **kw: attempted.append(a) or "resume",
    )

    backup_logic.run(channels_file, tmp_path / "archive", cache_dir=cache_dir, today=TODAY)

    assert attempted == []  # no backup, no slackdump, no sqlite touch
    catalog = backup_logic.catalog_logic.load(cache_dir, "f3a")
    assert catalog["channels"]["C1"]["last_action"] == "skip"
    assert catalog["channels"]["C1"]["last_checked"] == TODAY.isoformat()


def test_run_records_last_checked_and_last_action_for_checked_channel(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "active", "workspace": "f3a"}]))
    backup_logic.catalog_logic.save(
        cache_dir, "f3a",
        {"channels": {"C1": {"member": True, "name": "active"}}, "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )

    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    monkeypatch.setattr(backup_logic, "backup_channel", lambda *a, **kw: "resume")

    backup_logic.run(channels_file, tmp_path / "archive", cache_dir=cache_dir, today=TODAY)

    catalog = backup_logic.catalog_logic.load(cache_dir, "f3a")
    assert catalog["channels"]["C1"]["last_checked"] == TODAY.isoformat()
    assert catalog["channels"]["C1"]["last_action"] == "resume"


def test_run_full_resync_ignores_cadence_and_checks_everything(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "dormant", "workspace": "f3a"}]))
    backup_logic.catalog_logic.save(
        cache_dir, "f3a",
        {
            "channels": {
                "C1": {
                    "member": True, "name": "dormant",
                    "last_posted": _iso_days_ago(TODAY, 20 * 7),
                    "last_checked": _iso_days_ago(TODAY, 1),
                }
            },
            "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0,
        },
    )

    monkeypatch.setattr(backup_logic.catalog_logic, "refresh_fast", lambda ws, cache_dir=None: None)
    # even if cadence would skip, -full must run
    monkeypatch.setattr(backup_logic, "should_check_tonight", lambda entry, record, today: False)

    attempted = []
    monkeypatch.setattr(
        backup_logic, "backup_channel",
        lambda cid, slug, ws, root, full=False, cache_dir=None: attempted.append(slug) or "archive",
    )

    backup_logic.run(channels_file, tmp_path / "archive", full=True, cache_dir=cache_dir, today=TODAY)

    assert attempted == ["dormant"]
