"""Tests for the LLM digest export: one merged document spanning the
trailing N months across every f3* workspace. Separate from
test_export_logic.py (the per-channel-month exporter) - different schema,
same underlying fixtures.
"""
import json
import shutil
import sqlite3
from pathlib import Path

from slackbackup import catalog_logic, export_logic

FIXTURE = Path(__file__).parent.parent / "scripts" / "test_fixtures" / "export-archive"


def _make_file_db(path: Path, files: list[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE FILE (ID TEXT, DATA TEXT)")
    for f in files:
        conn.execute("INSERT INTO FILE (ID, DATA) VALUES (?, ?)", (f["id"], json.dumps(f)))
    conn.commit()
    conn.close()

A_TS = "1775811600.000100"
A1_TS = "1775811900.000100"
A2_TS = "1775901600.000100"
B_TS = "1776686400.000100"
B1_TS = "1777708800.000100"
C_TS = "1778853600.000100"


def test_select_channels_matches_glob_excludes_others(tmp_path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "1st-f", "workspace": "f3kirkland"},
        {"id": "C3", "name": "ai-coding", "workspace": "dungeons-of-finn-hill"},
    ]))

    selected = export_logic.select_channels(channels_file, "f3*")
    assert {e["workspace"] for e in selected} == {"f3pugetsound", "f3kirkland"}


def test_trailing_months_range_within_year():
    assert export_logic.trailing_months_range(3, "2026-06-23") == ("2026-04-01", "2026-06-23")


def test_trailing_months_range_crosses_year_boundary():
    assert export_logic.trailing_months_range(3, "2026-01-15") == ("2025-11-01", "2026-01-15")


def test_digest_message_url():
    url = export_logic.digest_message_url("f3pugetsound", "C123", "1718990400.123456")
    assert url == "https://f3pugetsound.slack.com/archives/C123/p1718990400123456"


def test_select_messages_in_range_nests_threads_without_month_bucketing():
    daydir = FIXTURE
    all_messages = export_logic._load_all_messages(daydir / "helpdesk")
    users_map = export_logic._load_users_map(daydir)

    from_epoch = export_logic._date_epoch("2026-04-01", "00:00:00")
    to_epoch = export_logic._date_epoch("2026-05-31", "23:59:59")
    messages = export_logic.select_messages_in_range(all_messages, users_map, from_epoch, to_epoch)

    parent_a = next(m for m in messages if m["ts"] == A_TS)
    assert [r["ts"] for r in parent_a["replies"]] == [A1_TS, A2_TS]

    parent_b = next(m for m in messages if m["ts"] == B_TS)
    assert [r["ts"] for r in parent_b["replies"]] == [B1_TS]

    assert any(m["ts"] == C_TS for m in messages)
    assert not any(m["ts"] == A1_TS for m in messages)


def _fake_convert(channel_dir: Path, out_dir: Path) -> None:
    """Stands in for slackdump.convert_export: copies the pre-converted
    fixture day-files/users.json for whichever channel `channel_dir`'s name
    points at, keyed by directory name (helpdesk is the only fixture
    channel; tests reuse it under different workspace/channel labels by
    naming tmp dirs "helpdesk")."""
    shutil.copytree(FIXTURE / "helpdesk", out_dir / "helpdesk")
    shutil.copy(FIXTURE / "users.json", out_dir / "users.json")


def test_build_digest_merges_across_workspaces_chronologically(tmp_path):
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

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["schema_version"] == "slack-llm-digest-v1"
    assert {c["workspace"] for c in result["channels"]} == {"f3pugetsound", "f3kirkland"}

    ts_values = [float(m["ts"]) for m in result["messages"]]
    assert ts_values == sorted(ts_values)

    parent_a = next(m for m in result["messages"] if m["ts"] == A_TS and m["workspace"] == "f3pugetsound")
    assert parent_a["channel_id"] == "C1"
    assert parent_a["message_url"] == "https://f3pugetsound.slack.com/archives/C1/p1775811600000100"
    assert "posted_at_utc" in parent_a
    assert parent_a["replies"][0]["message_url"].startswith("https://f3pugetsound.slack.com/archives/C1/")

    # No top-level merged author/users table - identity stays per-message.
    assert "users" not in result
    assert "authors" not in result

    # Fixture display names ("Al", "Caz", ...) carry no leadership signal.
    assert result["leadership"] == {"profile_role_matches": [], "by_region": [], "former_by_region": []}


def test_build_digest_thread_rollup_fields_on_parent_message(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    parent_a = next(m for m in result["messages"] if m["ts"] == A_TS)
    # parent_a (U0A) has two replies, both from U0B - 2 distinct
    # participants across root + replies, not 3.
    assert parent_a["reply_count"] == 2
    assert parent_a["thread_participant_count"] == 2
    assert parent_a["thread_last_reply_utc"] == "2026-04-11T10:00:00Z"

    parent_b = next(m for m in result["messages"] if m["ts"] == B_TS)
    assert parent_b["reply_count"] == 1
    assert parent_b["thread_participant_count"] == 2
    assert parent_b["thread_last_reply_utc"] == "2026-05-02T08:00:00Z"

    standalone_c = next(m for m in result["messages"] if m["ts"] == C_TS)
    assert "reply_count" not in standalone_c


def test_build_digest_manifest_describes_counting_rules(tmp_path):
    archive_root = tmp_path / "archive"
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["manifest"]["workspaces_included"] == 0
    assert "root_message_count" in result["manifest"]["counting_rules"]
    assert result["manifest"]["known_limitations"]


def test_build_digest_workspace_activity_index_excludes_bot_channel_from_human_variant(tmp_path):
    archive_root = tmp_path / "archive"
    active_dir = archive_root / "f3pugetsound" / "helpdesk"
    active_dir.mkdir(parents=True)
    (active_dir / "slackdump.sqlite").write_bytes(b"")
    bot_dir = archive_root / "f3pugetsound" / "bot-logs"
    bot_dir.mkdir(parents=True)
    (bot_dir / "slackdump.sqlite").write_bytes(b"")
    quiet_dir = archive_root / "f3pugetsound" / "quiet"
    quiet_dir.mkdir(parents=True)
    (quiet_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "bot-logs", "workspace": "f3pugetsound"},
        {"id": "C3", "name": "quiet", "workspace": "f3pugetsound"},
    ]))

    def convert_fn(channel_dir: Path, out_dir: Path) -> None:
        if channel_dir.name == "bot-logs":
            (out_dir / "bot-logs").mkdir(parents=True)
            day = out_dir / "bot-logs" / "2026-06-01.json"
            day.write_text(json.dumps([
                {"type": "message", "bot_id": "BBOT1", "username": "Log Bot", "ts": "1780300800.000100",
                 "text": "bot-only channel, 500 messages worth of logs"},
            ]))
            (out_dir / "users.json").write_text("[]")
        elif channel_dir.name == "quiet":
            (out_dir / "quiet").mkdir(parents=True)
            (out_dir / "users.json").write_text("[]")
        else:
            _fake_convert(channel_dir, out_dir)

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", convert_fn,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    index = next(w for w in result["workspace_activity_index"] if w["workspace"] == "f3pugetsound")
    assert index["channel_count"] == 3
    assert index["active_channel_count"] == 2
    assert index["inactive_channel_count"] == 1
    assert index["inactive_channels"] == ["quiet"]
    # bot-logs has more total messages than helpdesk would on its own in a
    # single-message comparison, but here helpdesk (8) beats bot-logs (1)
    # on total_message_count, so most_active_channel is still helpdesk -
    # the human-exclusion only matters when a bot channel would otherwise win.
    assert index["most_active_channel"]["channel"] == "helpdesk"
    assert index["most_active_human_channel"]["channel"] == "helpdesk"


def test_build_digest_most_active_human_channel_excludes_bot_posting_as_ordinary_user(tmp_path):
    """Regression for the real f3kirkland nation_bot_logs bot: it posts
    via an ordinary "U..." user account flagged is_bot in the roster, not
    via Slack's legacy bot_id field, so only the roster's is_bot flag (not
    a bot_id-prefix check) catches it."""
    archive_root = tmp_path / "archive"
    quiet_human_dir = archive_root / "f3pugetsound" / "quiet-human"
    quiet_human_dir.mkdir(parents=True)
    (quiet_human_dir / "slackdump.sqlite").write_bytes(b"")
    bot_dir = archive_root / "f3pugetsound" / "bot-logs"
    bot_dir.mkdir(parents=True)
    (bot_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "quiet-human", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "bot-logs", "workspace": "f3pugetsound"},
    ]))

    def convert_fn(channel_dir: Path, out_dir: Path) -> None:
        out = out_dir / channel_dir.name
        out.mkdir(parents=True)
        (out_dir / "users.json").write_text(json.dumps([
            {"id": "U0A", "name": "alice.a", "real_name": "Alice Anderson", "profile": {"display_name": "Al"}},
            {"id": "U0BOT", "name": "f3_nation", "real_name": "F3 Nation", "profile": {}, "is_bot": True},
        ]))
        if channel_dir.name == "bot-logs":
            (out / "2026-06-01.json").write_text(json.dumps([
                {"type": "message", "user": "U0BOT", "ts": f"178030{i:04d}.000100", "text": f"log line {i}"}
                for i in range(5)
            ]))
        else:
            (out / "2026-06-02.json").write_text(json.dumps([
                {"type": "message", "user": "U0A", "ts": "1780387200.000100", "text": "one human post"},
            ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", convert_fn,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    index = next(w for w in result["workspace_activity_index"] if w["workspace"] == "f3pugetsound")
    assert index["most_active_channel"]["channel"] == "bot-logs"
    assert index["most_active_human_channel"]["channel"] == "quiet-human"


def test_build_digest_most_active_channel_excludes_bot_only_channel_when_it_would_otherwise_win(tmp_path):
    archive_root = tmp_path / "archive"
    quiet_human_dir = archive_root / "f3pugetsound" / "quiet-human"
    quiet_human_dir.mkdir(parents=True)
    (quiet_human_dir / "slackdump.sqlite").write_bytes(b"")
    bot_dir = archive_root / "f3pugetsound" / "bot-logs"
    bot_dir.mkdir(parents=True)
    (bot_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "quiet-human", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "bot-logs", "workspace": "f3pugetsound"},
    ]))

    def convert_fn(channel_dir: Path, out_dir: Path) -> None:
        out = out_dir / channel_dir.name
        out.mkdir(parents=True)
        (out_dir / "users.json").write_text(json.dumps([
            {"id": "U0A", "name": "alice.a", "real_name": "Alice Anderson", "profile": {"display_name": "Al"}},
        ]))
        if channel_dir.name == "bot-logs":
            (out / "2026-06-01.json").write_text(json.dumps([
                {"type": "message", "bot_id": "BBOT1", "username": "Log Bot", "ts": f"178030{i:04d}.000100",
                 "text": f"log line {i}"}
                for i in range(5)
            ]))
        else:
            (out / "2026-06-02.json").write_text(json.dumps([
                {"type": "message", "user": "U0A", "ts": "1780387200.000100", "text": "one human post"},
            ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", convert_fn,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    index = next(w for w in result["workspace_activity_index"] if w["workspace"] == "f3pugetsound")
    assert index["most_active_channel"]["channel"] == "bot-logs"
    assert index["most_active_human_channel"]["channel"] == "quiet-human"


CANVAS_FILE = {
    "id": "F05KESM0B7C", "name": "Upcoming_Q_Schedule", "title": "Upcoming Q/Schedule",
    "mimetype": "application/vnd.slack-docs", "filetype": "quip", "pretty_type": "Canvas",
    "user": "U77PPNBFD", "created": 1690756854, "size": 2776,
    "permalink": "https://f3pugetsound.slack.com/docs/T78NKT50E/F05KESM0B7C",
}
IMAGE_FILE = {
    "id": "F0BBJTND1KR", "name": "1014.jpg", "title": "1014.jpg", "mimetype": "image/jpeg",
    "filetype": "jpg", "pretty_type": "JPEG", "user": "U01FVGV2QJZ", "created": 1700000500, "size": 605011,
    "permalink": "https://f3pugetsound.slack.com/files/U05DA6X8ZUZ/F0BBJTND1KR/1014.jpg",
}


def test_load_channel_files_excludes_images_and_includes_canvases(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)
    _make_file_db(channel_dir / "slackdump.sqlite", [CANVAS_FILE, IMAGE_FILE])

    files = export_logic._load_channel_files(channel_dir)

    assert [f["id"] for f in files] == ["F05KESM0B7C"]
    canvas = files[0]
    assert canvas["name"] == "Upcoming_Q_Schedule"
    assert canvas["title"] == "Upcoming Q/Schedule"
    assert canvas["pretty_type"] == "Canvas"
    assert canvas["creator"] == "U77PPNBFD"
    assert canvas["created_at"] == "2023-07-30T22:40:54Z"
    assert canvas["permalink"] == CANVAS_FILE["permalink"]


def test_load_channel_files_sets_local_path_only_when_file_exists_on_disk(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    upload_dir = channel_dir / "__uploads" / "F05KESM0B7C"
    upload_dir.mkdir(parents=True)
    (upload_dir / "Upcoming_Q_Schedule").write_text("<html>schedule</html>")
    _make_file_db(channel_dir / "slackdump.sqlite", [CANVAS_FILE])

    files = export_logic._load_channel_files(channel_dir)

    assert files[0]["local_path"] == "f3pugetsound/ao-active-book-club/__uploads/F05KESM0B7C/Upcoming_Q_Schedule"


def test_html_to_text_extracts_blocks_and_table_cells():
    raw = (
        "<div class=\"quip-canvas-content\"><h1>Schedule</h1>"
        "<p>Intro line.</p>"
        "<table><tr><td>Date</td><td>Q</td></tr>"
        "<tr><td>May 31</td><td><a>@U123</a></td></tr></table></div>"
    )
    text = export_logic._html_to_text(raw)
    assert "Schedule" in text.splitlines()
    assert "Intro line." in text
    assert "Date | Q" in text
    assert "May 31 | @U123" in text


def test_extract_file_content_parses_html_like_mimetype(tmp_path):
    path = tmp_path / "Upcoming_Q_Schedule"
    path.write_text("<p>Read this</p>")
    content = export_logic._extract_file_content("application/vnd.slack-docs", path)
    assert content == "Read this"


def test_extract_file_content_reads_plain_text_verbatim(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("plain notes\nline two")
    content = export_logic._extract_file_content("text/plain", path)
    assert content == "plain notes\nline two"


def test_extract_file_content_none_for_unsupported_mimetype(tmp_path):
    path = tmp_path / "report.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    assert export_logic._extract_file_content("application/pdf", path) is None


def test_extract_file_content_none_when_no_local_path():
    assert export_logic._extract_file_content("text/plain", None) is None


def test_load_channel_files_includes_extracted_content_for_canvas(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    upload_dir = channel_dir / "__uploads" / "F05KESM0B7C"
    upload_dir.mkdir(parents=True)
    (upload_dir / "Upcoming_Q_Schedule").write_text("<h1>Upcoming Q/Schedule</h1><p>Coverage needed.</p>")
    _make_file_db(channel_dir / "slackdump.sqlite", [CANVAS_FILE])

    files = export_logic._load_channel_files(channel_dir)

    assert "Upcoming Q/Schedule" in files[0]["content"]
    assert "Coverage needed." in files[0]["content"]


def test_load_channel_files_content_is_none_when_blob_never_downloaded(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)
    _make_file_db(channel_dir / "slackdump.sqlite", [CANVAS_FILE])

    files = export_logic._load_channel_files(channel_dir)

    assert files[0]["content"] is None


def test_load_channel_files_local_path_is_none_when_blob_was_never_downloaded(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)
    _make_file_db(channel_dir / "slackdump.sqlite", [CANVAS_FILE])

    files = export_logic._load_channel_files(channel_dir)

    assert files[0]["local_path"] is None


def test_load_channel_files_dedupes_by_id_across_resume_cycles(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)
    _make_file_db(channel_dir / "slackdump.sqlite", [CANVAS_FILE, CANVAS_FILE])

    files = export_logic._load_channel_files(channel_dir)

    assert len(files) == 1


def test_load_channel_files_returns_empty_for_malformed_or_missing_archive(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)
    assert export_logic._load_channel_files(channel_dir) == []  # no slackdump.sqlite at all

    (channel_dir / "slackdump.sqlite").write_bytes(b"")  # 0-byte placeholder
    assert export_logic._load_channel_files(channel_dir) == []


def test_build_digest_includes_non_image_files_per_channel(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)

    db_path = channel_dir / "slackdump.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE FILE (ID TEXT, DATA TEXT)")
    conn.execute("INSERT INTO FILE (ID, DATA) VALUES (?, ?)", (CANVAS_FILE["id"], json.dumps(CANVAS_FILE)))
    conn.execute("INSERT INTO FILE (ID, DATA) VALUES (?, ?)", (IMAGE_FILE["id"], json.dumps(IMAGE_FILE)))
    conn.commit()
    conn.close()

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "ao-active-book-club", "workspace": "f3pugetsound"},
    ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    meta = next(c for c in result["channels"] if c["channel_id"] == "C1")
    assert [f["id"] for f in meta["files"]] == ["F05KESM0B7C"]


def test_build_digest_enriches_channels_meta_from_catalog_cache(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    cache_dir = tmp_path / "cache"
    catalog = catalog_logic.load(cache_dir, "f3pugetsound")
    catalog["channels"]["C1"] = {
        "member": True, "name": "helpdesk", "description": "Ask anything here",
        "is_private": False, "is_archived": False, "creator": "U999", "created": 1700000000,
    }
    catalog_logic.save(cache_dir, "f3pugetsound", catalog)

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", _fake_convert,
        catalog_cache_dir=cache_dir,
    )

    meta = next(c for c in result["channels"] if c["channel_id"] == "C1")
    assert meta["description"] == "Ask anything here"
    assert meta["creator"] == "U999"
    assert meta["created_at"] == "2023-11-14T22:13:20Z"


def test_build_digest_channel_context_is_none_when_catalog_never_warmed(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "never-warmed-cache",
    )

    meta = next(c for c in result["channels"] if c["channel_id"] == "C1")
    assert meta == {
        "workspace": "f3pugetsound", "channel": "helpdesk", "channel_id": "C1", "status": "ok", "files": [],
        "description": None, "creator": None, "created_at": None,
        "root_message_count": 5, "reply_count": 3, "total_message_count": 8, "participant_count": 7,
        "first_message_utc": "2026-04-10T09:00:00Z", "last_message_utc": "2026-06-05T12:00:00Z",
        "activity_status": "active", "activity_status_basis": "has messages during export_scope",
    }


def test_build_digest_leadership_includes_workspace_admin_without_title_match(tmp_path):
    """A Slack workspace admin/owner is an authoritative leadership signal
    on its own - they should surface in leadership even if their display
    name carries no F3 title keyword."""
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    def convert_with_admin(channel_dir: Path, out_dir: Path) -> None:
        _fake_convert(channel_dir, out_dir)
        users = json.loads((out_dir / "users.json").read_text())
        users.append({
            "id": "UADMIN", "name": "plainjane", "real_name": "Plain Jane",
            "profile": {"display_name": "Jane"}, "is_admin": True, "is_owner": False,
        })
        (out_dir / "users.json").write_text(json.dumps(users))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", convert_with_admin,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    matches = result["leadership"]["profile_role_matches"]
    admin_entry = next(m for m in matches if m["id"] == "UADMIN")
    assert admin_entry["slack_roles"] == ["admin"]
    assert admin_entry["derived"] is None
    # No derived role/region to group by - doesn't appear in by_region.
    assert result["leadership"]["by_region"] == []


def test_derive_leadership_none_for_plain_display_name():
    assert export_logic.derive_leadership("Al") is None
    assert export_logic.derive_leadership(None) is None
    assert export_logic.derive_leadership("") is None


def test_derive_leadership_matches_title_and_region():
    signal = export_logic.derive_leadership("Columbia - Cascades Region Nantan")
    assert signal["possible_f3_name"] == "Columbia"
    assert signal["possible_region"] == "F3 Cascades"
    assert signal["possible_roles"] == [
        {
            "position": "Nantan", "basis": "display_name", "confidence": "medium_high",
            "needs_confirmation": True, "status": "unclear", "is_current": None,
            "modifier_detected": None, "source_text": "Columbia - Cascades Region Nantan",
        }
    ]


def test_derive_leadership_no_separator_is_lower_confidence_no_region():
    signal = export_logic.derive_leadership("Comz Guy")
    assert signal["possible_f3_name"] == "Comz Guy"
    assert signal["possible_region"] is None
    assert signal["possible_roles"][0]["confidence"] == "medium"


def test_derive_leadership_compact_hyphen_region_parses_name_correctly():
    # Reported broken in docs/llm-leadership-improvement.md: no spaces
    # around the hyphen, so the old separator-only logic fell back to the
    # whole string as the "name".
    signal = export_logic.derive_leadership("Montoya-Kirkland Region Nantan")
    assert signal["possible_f3_name"] == "Montoya"
    assert signal["possible_region"] == "F3 Kirkland"
    assert signal["possible_roles"][0]["confidence"] == "medium_high"


def test_derive_leadership_paren_region_form():
    signal = export_logic.derive_leadership("Quesadillah (F3 Ellensburg Nantan)")
    assert signal["possible_f3_name"] == "Quesadillah"
    # Ellensburg isn't a tracked f3* region - correctly left unresolved
    # rather than guessed.
    assert signal["possible_region"] is None
    assert signal["possible_roles"][0]["confidence"] == "medium_high"


def test_derive_leadership_name_then_role_then_region_order():
    signal = export_logic.derive_leadership("Tardy - Kirkland 3rd F")
    assert signal["possible_f3_name"] == "Tardy"
    assert signal["possible_region"] == "F3 Kirkland"
    assert {r["position"] for r in signal["possible_roles"]} == {"3rd F"}


def test_derive_leadership_weaselshaker_no_space_variant():
    signal = export_logic.derive_leadership("Voltaire - Weaselshaker Tundra")
    assert signal["possible_f3_name"] == "Voltaire"
    assert signal["possible_region"] == "F3 Tundra"
    assert {r["position"] for r in signal["possible_roles"]} == {"Weasel Shaker"}


def test_derive_leadership_multiple_roles_no_redundant_bare_q():
    signal = export_logic.derive_leadership("Columbia - 1stF Q Cascades")
    assert signal["possible_f3_name"] == "Columbia"
    assert signal["possible_region"] == "F3 Cascades"
    assert {r["position"] for r in signal["possible_roles"]} == {"1st F", "Q"}


def test_derive_leadership_specific_q_variant_suppresses_bare_q():
    signal = export_logic.derive_leadership("Sitwell - Site Q Kirkland")
    positions = {r["position"] for r in signal["possible_roles"]}
    assert positions == {"Site Q"}
    assert "Q" not in positions


def test_derive_leadership_title_two_segments_different_regions():
    # "Redmond Ridge Site Q, Redmond Comz Q" — real title format per user feedback.
    signal = export_logic.derive_leadership("Combine", title="Redmond Ridge Site Q, Redmond Comz Q")
    assert signal["possible_f3_name"] == "Combine"
    roles = signal["possible_roles"]
    site_q = next(r for r in roles if r["position"] == "Site Q")
    comz = next(r for r in roles if r["position"] == "Comz")
    # Site Q is AO-scoped: emits possible_ao for the workout location and
    # possible_region derived from known region names within the prefix.
    assert site_q["basis"] == "title"
    assert site_q["confidence"] == "high"
    assert site_q["needs_confirmation"] is False
    assert site_q["possible_ao"] == "Redmond Ridge"
    assert site_q["possible_region"] == "F3 Redmond"
    # Comz Q is region-scoped: possible_region only, no possible_ao.
    assert comz["basis"] == "title"
    assert comz["possible_region"] == "F3 Redmond"
    assert "possible_ao" not in comz


def test_derive_leadership_title_only_no_display_name_match():
    # Title alone (plain display name) should still surface roles.
    signal = export_logic.derive_leadership("Dude", title="Kirkland Nantan")
    assert signal is not None
    positions = {r["position"] for r in signal["possible_roles"]}
    assert "Nantan" in positions
    title_roles = [r for r in signal["possible_roles"] if r["basis"] == "title"]
    assert all(r["confidence"] == "high" for r in title_roles)
    assert all(r["needs_confirmation"] is False for r in title_roles)


def test_derive_leadership_none_when_both_sources_empty():
    assert export_logic.derive_leadership("Dude", title="Community Manager") is None
    assert export_logic.derive_leadership(None, title=None) is None


def test_build_digest_leadership_pulled_from_full_roster_not_just_posters(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    def convert_with_leader(channel_dir: Path, out_dir: Path) -> None:
        _fake_convert(channel_dir, out_dir)
        users = json.loads((out_dir / "users.json").read_text())
        users.append({
            "id": "ULEADER", "name": "columbia", "real_name": "Real Columbia",
            "profile": {"display_name": "Columbia - Cascades Region Nantan"},
        })
        (out_dir / "users.json").write_text(json.dumps(users))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", convert_with_leader,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    # The leader never posted in-range, so doesn't appear in messages...
    assert not any(m.get("user") == "ULEADER" for m in result["messages"])
    # ...but still surfaces in leadership, since that's scanned from the
    # full roster, not just posters.
    assert result["leadership"]["profile_role_matches"] == [
        {
            "id": "ULEADER",
            "workspace": "f3pugetsound",
            "display_name": "Columbia - Cascades Region Nantan",
            "real_name": "Real Columbia",
            "title": None,
            "slack_roles": [],
            "derived": {
                "possible_f3_name": "Columbia",
                "possible_region": "F3 Cascades",
                "possible_roles": [
                    {
                        "position": "Nantan", "basis": "display_name", "confidence": "medium_high",
                        "needs_confirmation": True, "status": "unclear", "is_current": None,
                        "modifier_detected": None, "source_text": "Columbia - Cascades Region Nantan",
                    }
                ],
            },
        }
    ]
    assert result["leadership"]["by_region"] == [
        {
            "region": "F3 Cascades",
            "roles": [
                {
                    "position": "Nantan",
                    "f3_name": "Columbia",
                    "status": "unclear",
                    "is_current": None,
                    "confidence": "medium_high",
                    "basis": "display_name",
                    "seen_in_workspaces": ["f3pugetsound"],
                    "source_display_names": ["Columbia - Cascades Region Nantan"],
                    "source_profile_ids": ["ULEADER"],
                    "needs_confirmation": True,
                }
            ],
        }
    ]
    assert result["leadership"]["former_by_region"] == []


def test_build_digest_leadership_dedupes_same_person_across_workspaces(tmp_path):
    archive_root = tmp_path / "archive"
    for ws in ("f3pugetsound", "f3kirkland"):
        channel_dir = archive_root / ws / "helpdesk"
        channel_dir.mkdir(parents=True)
        (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "helpdesk", "workspace": "f3kirkland"},
    ]))

    def convert_with_leader(channel_dir: Path, out_dir: Path) -> None:
        _fake_convert(channel_dir, out_dir)
        # Same person, same self-reported role, separate per-workspace
        # account id - this is the duplication reported in
        # docs/llm-leadership-improvement.md.
        workspace = channel_dir.parent.name
        users = json.loads((out_dir / "users.json").read_text())
        users.append({
            "id": f"ULEADER-{workspace}", "name": "columbia", "real_name": "Real Columbia",
            "profile": {"display_name": "Columbia - Cascades Region Nantan"},
        })
        (out_dir / "users.json").write_text(json.dumps(users))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", convert_with_leader,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert len(result["leadership"]["profile_role_matches"]) == 2  # one per workspace account
    by_region = result["leadership"]["by_region"]
    assert len(by_region) == 1
    role = by_region[0]["roles"][0]
    assert role["position"] == "Nantan"
    assert role["f3_name"] == "Columbia"
    assert role["seen_in_workspaces"] == ["f3kirkland", "f3pugetsound"]
    assert set(role["source_profile_ids"]) == {"ULEADER-f3kirkland", "ULEADER-f3pugetsound"}
    assert role["needs_confirmation"] is True


def test_build_digest_missing_archive_is_soft_skip(tmp_path):
    archive_root = tmp_path / "archive"  # no channel dirs created at all

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["channels"] == [
        {
            "workspace": "f3pugetsound", "channel": "helpdesk", "channel_id": "C1", "status": "missing_archive",
            "files": [], "description": None, "creator": None, "created_at": None,
        }
    ]
    assert result["messages"] == []


# --- modifier / tenure tests ---


def test_derive_leadership_modifier_emeritus_after_role():
    # Real sanitized example: "Seattle Region Nantan Emeritus - 206.555.1234"
    # The modifier appears after the role keyword; trailing content is noise.
    signal = export_logic.derive_leadership("Padre - Seattle Region Nantan Emeritus - 206.555.1234")
    assert signal is not None
    role = next(r for r in signal["possible_roles"] if r["position"] == "Nantan")
    assert role["status"] == "emeritus"
    assert role["is_current"] is False
    assert role["modifier_detected"].lower() == "emeritus"


def test_derive_leadership_modifier_former_before_role():
    signal = export_logic.derive_leadership("Former Nantan")
    assert signal is not None
    role = signal["possible_roles"][0]
    assert role["status"] == "former"
    assert role["is_current"] is False
    assert "former" in role["modifier_detected"].lower()


def test_derive_leadership_modifier_retired():
    signal = export_logic.derive_leadership("Retired Weasel Shaker")
    assert signal is not None
    role = signal["possible_roles"][0]
    assert role["status"] == "retired"
    assert role["is_current"] is False


def test_derive_leadership_modifier_ex_prefix():
    signal = export_logic.derive_leadership("Ex-Nantan")
    assert signal is not None
    role = signal["possible_roles"][0]
    assert role["status"] == "former"
    assert role["is_current"] is False


def test_derive_leadership_no_modifier_display_name_is_unclear():
    # No separator → confidence=medium → status="unclear", is_current=None
    signal = export_logic.derive_leadership("Nantan")
    assert signal is not None
    role = signal["possible_roles"][0]
    assert role["status"] == "unclear"
    assert role["is_current"] is None
    assert role["modifier_detected"] is None


def test_derive_leadership_title_no_modifier_is_current():
    # Title field with no modifier and confidence="high" → status="current"
    signal = export_logic.derive_leadership("Dude", title="Kirkland Nantan")
    title_roles = [r for r in signal["possible_roles"] if r["basis"] == "title"]
    assert title_roles
    assert all(r["status"] == "current" for r in title_roles)
    assert all(r["is_current"] is True for r in title_roles)
    assert all(r["modifier_detected"] is None for r in title_roles)


def test_derive_leadership_title_modifier_scoped_to_segment():
    # "Former Nantan, Kirkland Comz Q" — modifier only in the first segment;
    # second segment has no modifier and should be "current".
    signal = export_logic.derive_leadership("Dude", title="Former Cascades Nantan, Kirkland Comz Q")
    nantan = next(r for r in signal["possible_roles"] if r["position"] == "Nantan")
    comz = next(r for r in signal["possible_roles"] if r["position"] == "Comz")
    assert nantan["status"] == "former"
    assert nantan["is_current"] is False
    assert comz["status"] == "current"
    assert comz["is_current"] is True


def test_derive_leadership_source_text_captured():
    signal = export_logic.derive_leadership("Columbia - Cascades Region Nantan")
    role = signal["possible_roles"][0]
    assert role["source_text"] == "Columbia - Cascades Region Nantan"


def test_derive_leadership_title_source_text_is_segment():
    signal = export_logic.derive_leadership("Dude", title="Redmond Ridge Site Q, Redmond Comz Q")
    site_q = next(r for r in signal["possible_roles"] if r["position"] == "Site Q")
    comz = next(r for r in signal["possible_roles"] if r["position"] == "Comz")
    assert site_q["source_text"] == "Redmond Ridge Site Q"
    assert comz["source_text"] == "Redmond Comz Q"


def test_build_digest_former_leaders_go_to_former_by_region(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    def convert_with_former(channel_dir: Path, out_dir: Path) -> None:
        _fake_convert(channel_dir, out_dir)
        users = json.loads((out_dir / "users.json").read_text())
        users.append({
            "id": "UFORMER", "name": "ex_nantan", "real_name": "Old Leader",
            "profile": {"display_name": "OldLeader", "title": "Former Cascades Nantan"},
        })
        (out_dir / "users.json").write_text(json.dumps(users))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", convert_with_former,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["leadership"]["by_region"] == []
    former = result["leadership"]["former_by_region"]
    assert len(former) == 1
    role = former[0]["roles"][0]
    assert role["position"] == "Nantan"
    assert role["status"] == "former"
    assert role["is_current"] is False


def test_build_digest_emeritus_in_display_name_goes_to_former_by_region(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    def convert_with_emeritus(channel_dir: Path, out_dir: Path) -> None:
        _fake_convert(channel_dir, out_dir)
        users = json.loads((out_dir / "users.json").read_text())
        users.append({
            "id": "UEMERITUS", "name": "padre", "real_name": "Padre",
            # Sanitized real-world format: modifier after role, trailing noise after " - "
            "profile": {"display_name": "Padre - Seattle Region Nantan Emeritus - 206.555.1234"},
        })
        (out_dir / "users.json").write_text(json.dumps(users))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", 3, "2026-06-23", convert_with_emeritus,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["leadership"]["by_region"] == []
    former = result["leadership"]["former_by_region"]
    assert len(former) == 1
    role = former[0]["roles"][0]
    assert role["status"] == "emeritus"
    assert role["is_current"] is False
