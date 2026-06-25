import argparse
import json
import sqlite3

from slackbackup import catalog, catalog_logic


def _make_db(path, message_count):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE MESSAGE (ts TEXT)")
    for i in range(message_count):
        conn.execute("INSERT INTO MESSAGE (ts) VALUES (?)", (f"170000000{i}.000000",))
    conn.commit()
    conn.close()


def _args(**kwargs):
    defaults = {
        "workspace": "f3test",
        "channels_file": None,
        "archive_root": None,
        "description": False,
        "topic": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_message_count_local_reads_real_archive(tmp_path):
    db_path = tmp_path / "f3test" / "general" / "slackdump.sqlite"
    _make_db(db_path, message_count=4)
    assert catalog._message_count_local(str(tmp_path), "f3test", "general") == 4


def test_message_count_local_none_without_archive_root():
    assert catalog._message_count_local(None, "f3test", "general") is None


def test_message_count_local_none_when_archive_missing(tmp_path):
    assert catalog._message_count_local(str(tmp_path), "f3test", "general") is None


def test_list_sorts_most_recently_updated_first(tmp_path, monkeypatch, capsys):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "stale", "workspace": "f3test"},
        {"id": "C2", "name": "fresh", "workspace": "f3test"},
    ]))
    catalog_logic.save(
        cache_dir, "f3test",
        {
            "channels": {
                "C1": {"member": True, "name": "stale", "last_posted": "2020-01-01T00:00:00Z"},
                "C2": {"member": True, "name": "fresh", "last_posted": "2026-06-20T00:00:00Z"},
            },
            "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0,
        },
    )
    monkeypatch.setattr(catalog.catalog_logic, "DEFAULT_CACHE_DIR", cache_dir)

    catalog._list(_args(channels_file=str(channels_file)))

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[1].startswith("fresh")
    assert lines[2].startswith("stale")


def test_list_shows_dash_for_message_count_without_archive_root(tmp_path, monkeypatch, capsys):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3test"}]))
    catalog_logic.save(
        cache_dir, "f3test",
        {"channels": {"C1": {"member": True, "name": "general"}}, "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )
    monkeypatch.setattr(catalog.catalog_logic, "DEFAULT_CACHE_DIR", cache_dir)

    catalog._list(_args(channels_file=str(channels_file)))

    out = capsys.readouterr().out
    assert "-" in out.splitlines()[1]


def test_list_includes_message_count_with_archive_root(tmp_path, monkeypatch, capsys):
    cache_dir = tmp_path / "cache"
    archive_root = tmp_path / "archive"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3test"}]))
    catalog_logic.save(
        cache_dir, "f3test",
        {"channels": {"C1": {"member": True, "name": "general"}}, "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )
    _make_db(archive_root / "f3test" / "general" / "slackdump.sqlite", message_count=7)
    monkeypatch.setattr(catalog.catalog_logic, "DEFAULT_CACHE_DIR", cache_dir)

    catalog._list(_args(channels_file=str(channels_file), archive_root=str(archive_root)))

    out = capsys.readouterr().out
    assert "7" in out.splitlines()[1]


def test_list_optionally_includes_description_and_topic(tmp_path, monkeypatch, capsys):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3test"}]))
    catalog_logic.save(
        cache_dir, "f3test",
        {
            "channels": {"C1": {"member": True, "name": "general", "description": "Desc here", "topic": "Topic here"}},
            "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0,
        },
    )
    monkeypatch.setattr(catalog.catalog_logic, "DEFAULT_CACHE_DIR", cache_dir)

    catalog._list(_args(channels_file=str(channels_file), description=True, topic=True))

    out = capsys.readouterr().out
    assert "Desc here" in out
    assert "Topic here" in out


def test_list_shows_unknown_when_no_recency_signal(tmp_path, monkeypatch, capsys):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3test"}]))
    catalog_logic.save(
        cache_dir, "f3test",
        {"channels": {"C1": {"member": True, "name": "general"}}, "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )
    monkeypatch.setattr(catalog.catalog_logic, "DEFAULT_CACHE_DIR", cache_dir)

    catalog._list(_args(channels_file=str(channels_file)))

    out = capsys.readouterr().out
    assert "unknown" in out.splitlines()[1]
