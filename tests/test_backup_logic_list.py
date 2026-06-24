import json
import sqlite3

from slackbackup import backup_logic


def _make_archive(db_path, message_count):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE MESSAGE (ID INTEGER)")
    conn.executemany("INSERT INTO MESSAGE VALUES (?)", [(i,) for i in range(message_count)])
    conn.commit()
    conn.close()


def test_list_status_reports_archived_with_message_count(tmp_path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3test"}]))
    archive_root = tmp_path / "archive"
    _make_archive(archive_root / "f3test" / "general" / "slackdump.sqlite", 42)

    rows = backup_logic.list_status(channels_file, archive_root)
    assert len(rows) == 1
    assert rows[0]["archived"] is True
    assert rows[0]["message_count"] == 42
    assert rows[0]["last_modified"] is not None


def test_list_status_reports_not_archived_when_no_local_db(tmp_path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([{"id": "C1", "name": "general", "workspace": "f3test"}]))

    rows = backup_logic.list_status(channels_file, tmp_path / "archive")
    assert rows[0]["archived"] is False
    assert rows[0]["message_count"] is None
    assert rows[0]["last_modified"] is None


def test_list_status_covers_every_tracked_channel(tmp_path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "general", "workspace": "f3a"},
        {"id": "C2", "name": "random", "workspace": "f3b"},
    ]))

    rows = backup_logic.list_status(channels_file, tmp_path / "archive")
    assert {(r["id"], r["workspace"]) for r in rows} == {("C1", "f3a"), ("C2", "f3b")}
