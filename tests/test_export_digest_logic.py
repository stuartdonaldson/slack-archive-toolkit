"""Tests for the LLM digest export: one merged document spanning every
message ever archived (or the trailing N days, via --days) across every
f3* workspace. Separate from test_export_logic.py (the per-channel-month
exporter) - different schema, same underlying fixtures.
"""
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from slackbackup import catalog_logic, export_logic

FIXTURE = Path(__file__).parent.parent / "scripts" / "test_fixtures" / "export-archive"


def _make_file_db(path: Path, files: list[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE FILE (ID TEXT, DATA TEXT, MESSAGE_ID TEXT)")
    for f in files:
        message_id = f.get("message_id")
        conn.execute("INSERT INTO FILE (ID, DATA, MESSAGE_ID) VALUES (?, ?, ?)", (f["id"], json.dumps(f), message_id))
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


def test_select_channels_accepts_comma_separated_workspace_list(tmp_path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
        {"id": "C2", "name": "1st-f", "workspace": "f3kirkland"},
        {"id": "C3", "name": "ai-coding", "workspace": "dungeons-of-finn-hill"},
    ]))

    selected = export_logic.select_channels(channels_file, "f3pugetsound,f3kirkland")
    assert {e["workspace"] for e in selected} == {"f3pugetsound", "f3kirkland"}


def test_trailing_days_range_within_month():
    assert export_logic.trailing_days_range(10, "2026-06-23") == ("2026-06-14", "2026-06-23")


def test_trailing_days_range_crosses_year_boundary():
    assert export_logic.trailing_days_range(30, "2026-01-15") == ("2025-12-17", "2026-01-15")


def test_trailing_days_range_none_means_unbounded():
    assert export_logic.trailing_days_range(None, "2026-06-23") == (None, "2026-06-23")


def test_load_job_rejects_workspaces_given_as_a_bare_string(tmp_path):
    job_file = tmp_path / "job.json"
    job_file.write_text(json.dumps({
        "type": "digest", "archive_root": "/archive", "workspaces": "f3pugetsound", "out": "out-{as_of}.json",
    }))

    with pytest.raises(ValueError):
        export_logic.load_job(job_file)


def test_load_job_rejects_missing_workspaces(tmp_path):
    job_file = tmp_path / "job.json"
    job_file.write_text(json.dumps({"type": "digest", "archive_root": "/archive", "out": "out-{as_of}.json"}))

    with pytest.raises(ValueError):
        export_logic.load_job(job_file)


def test_load_job_accepts_workspaces_as_a_list(tmp_path):
    job_file = tmp_path / "job.json"
    job_file.write_text(json.dumps({
        "type": "digest", "archive_root": "/archive", "workspaces": ["f3pugetsound"], "out": "out-{as_of}.json",
    }))

    job = export_logic.load_job(job_file)
    assert job["workspaces"] == ["f3pugetsound"]


def test_digest_message_url():
    url = export_logic.digest_message_url("f3pugetsound", "C123", "1718990400.123456")
    assert url == "https://f3pugetsound.slack.com/archives/C123/p1718990400123456"


def test_digest_channel_url():
    url = export_logic.digest_channel_url("f3pugetsound", "C123")
    assert url == "https://f3pugetsound.slack.com/archives/C123"


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


def test_select_messages_in_range_includes_thread_with_parent_before_window_and_reply_inside():
    users_map = {"U0A": "Al", "U0B": "Caz"}
    all_messages = [
        {"ts": "1000.000100", "thread_ts": "1000.000100", "user": "U0A", "text": "old parent"},
        {"ts": "2000.000100", "thread_ts": "1000.000100", "user": "U0B", "text": "revived reply"},
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 1900.0, 2100.0)

    assert len(messages) == 1
    parent = messages[0]
    assert parent["ts"] == "1000.000100"
    assert parent["in_scope"] is False
    assert [r["ts"] for r in parent["replies"]] == ["2000.000100"]

    activity = export_logic._channel_activity(messages)
    assert activity["root_message_count"] == 0
    assert activity["reply_count"] == 1
    assert activity["total_message_count"] == 1
    assert activity["participant_count"] == 1  # only the replying author, U0B
    assert activity["first_message_utc"] == activity["last_message_utc"]


def test_select_messages_in_range_no_in_scope_key_when_parent_and_replies_inside_window():
    users_map = {"U0A": "Al", "U0B": "Caz"}
    all_messages = [
        {"ts": "1000.000100", "thread_ts": "1000.000100", "user": "U0A", "text": "parent"},
        {"ts": "1100.000100", "thread_ts": "1000.000100", "user": "U0B", "text": "reply"},
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert len(messages) == 1
    assert "in_scope" not in messages[0]
    assert "in_scope" not in messages[0]["replies"][0]

    activity = export_logic._channel_activity(messages)
    assert activity["root_message_count"] == 1
    assert activity["reply_count"] == 1
    assert activity["participant_count"] == 2


def test_select_messages_in_range_excludes_thread_when_parent_and_replies_all_before_window():
    users_map = {"U0A": "Al", "U0B": "Caz"}
    all_messages = [
        {"ts": "1000.000100", "thread_ts": "1000.000100", "user": "U0A", "text": "parent"},
        {"ts": "1100.000100", "thread_ts": "1000.000100", "user": "U0B", "text": "reply"},
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 5000.0, 6000.0)

    assert messages == []


def test_select_messages_in_range_carries_reactions_when_present():
    users_map = {"U0A": "Al"}
    all_messages = [
        {
            "ts": "1000.000100", "user": "U0A", "text": "parent",
            "reactions": [{"name": "+1", "count": 2, "users": ["U0A", "U0B"]}],
        },
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert messages[0]["reactions"] == [{"name": "+1", "count": 2, "users": ["U0A", "U0B"]}]


def test_select_messages_in_range_omits_reactions_key_when_absent():
    users_map = {"U0A": "Al"}
    all_messages = [{"ts": "1000.000100", "user": "U0A", "text": "parent"}]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert "reactions" not in messages[0]


def test_select_messages_in_range_carries_edited_as_utc():
    users_map = {"U0A": "Al"}
    all_messages = [
        {
            "ts": "1000.000100", "user": "U0A", "text": "parent",
            "edited": {"user": "U0A", "ts": "1000.000200"},
        },
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert messages[0]["edited"] == {"user": "U0A", "at_utc": export_logic._format_utc(1000.0002)}


def test_select_messages_in_range_carries_subtype_verbatim():
    users_map = {"U0A": "Al"}
    all_messages = [
        {"ts": "1000.000100", "user": "U0A", "text": "joined", "subtype": "channel_join"},
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert messages[0]["subtype"] == "channel_join"


def test_select_messages_in_range_unfurl_from_permalink_parses_target_channel_and_ts():
    users_map = {"U0A": "Al"}
    all_messages = [
        {
            "ts": "1000.000100", "user": "U0A", "text": "look at this",
            "attachments": [
                {
                    "is_msg_unfurl": True,
                    "from_url": "https://f3pugetsound.slack.com/archives/C123/p1778086219226429",
                    "author_name": "Caz",
                    "text": "the earlier quoted message",
                },
            ],
        },
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    unfurl = messages[0]["unfurls"][0]
    assert unfurl["url"] == "https://f3pugetsound.slack.com/archives/C123/p1778086219226429"
    assert unfurl["author_name"] == "Caz"
    assert unfurl["quoted_text"] == "the earlier quoted message"
    assert unfurl["target_channel_id"] == "C123"
    assert unfurl["target_ts"] == "1778086219.226429"


def test_select_messages_in_range_other_attachment_emits_url_and_title():
    users_map = {"U0A": "Al"}
    all_messages = [
        {
            "ts": "1000.000100", "user": "U0A", "text": "check this out",
            "attachments": [
                {"from_url": "https://example.com/page", "title": "Example Page"},
            ],
        },
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert messages[0]["unfurls"] == [{"url": "https://example.com/page", "title": "Example Page"}]


def test_select_messages_in_range_attachment_without_url_or_title_link_is_skipped():
    users_map = {"U0A": "Al"}
    all_messages = [
        {
            "ts": "1000.000100", "user": "U0A", "text": "no link here",
            "attachments": [{"fallback": "some fallback text with no url"}],
        },
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert "unfurls" not in messages[0]


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
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["schema_version"] == "slack-llm-digest-v2"
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
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
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
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
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
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_fn,
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
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_fn,
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
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_fn,
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
    conn.execute("CREATE TABLE FILE (ID TEXT, DATA TEXT, MESSAGE_ID TEXT)")
    conn.execute("INSERT INTO FILE (ID, DATA, MESSAGE_ID) VALUES (?, ?, ?)", (CANVAS_FILE["id"], json.dumps(CANVAS_FILE), None))
    conn.execute("INSERT INTO FILE (ID, DATA, MESSAGE_ID) VALUES (?, ?, ?)", (IMAGE_FILE["id"], json.dumps(IMAGE_FILE), None))
    conn.commit()
    conn.close()

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "ao-active-book-club", "workspace": "f3pugetsound"},
    ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
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
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
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
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "never-warmed-cache",
    )

    meta = next(c for c in result["channels"] if c["channel_id"] == "C1")
    assert meta == {
        "workspace": "f3pugetsound", "channel": "helpdesk", "channel_id": "C1", "status": "ok",
        "channel_url": "https://f3pugetsound.slack.com/archives/C1", "files": [],
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
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_with_admin,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    matches = result["leadership"]["profile_role_matches"]
    admin_entry = next(m for m in matches if m["id"] == "UADMIN")
    assert admin_entry["slack_roles"] == ["admin"]
    assert admin_entry["derived"] is None
    # No derived role/region to group by - doesn't appear in by_region.
    assert result["leadership"]["by_region"] == []


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
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_with_leader,
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
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_with_leader,
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
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["channels"] == [
        {
            "workspace": "f3pugetsound", "channel": "helpdesk", "channel_id": "C1", "status": "missing_archive",
            "channel_url": "https://f3pugetsound.slack.com/archives/C1",
            "files": [], "description": None, "creator": None, "created_at": None,
        }
    ]
    assert result["messages"] == []


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
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_with_former,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["leadership"]["by_region"] == []
    former = result["leadership"]["former_by_region"]
    assert len(former) == 1
    role = former[0]["roles"][0]
    assert role["position"] == "Nantan"
    assert role["status"] == "former"
    assert role["is_current"] is False


def test_load_channel_files_message_attached_file_carries_message_ts(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)

    file_with_message = CANVAS_FILE.copy()
    file_with_message["id"] = "F_WITH_MESSAGE"
    _make_file_db(channel_dir / "slackdump.sqlite", [file_with_message])

    # Manually add MESSAGE_ID to the database since _make_file_db uses the message_id key
    # We need to update the database directly
    db_path = channel_dir / "slackdump.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE FILE SET MESSAGE_ID = ? WHERE ID = ?", ("1234567890.000001", "F_WITH_MESSAGE"))
    conn.commit()
    conn.close()

    files = export_logic._load_channel_files(channel_dir)

    assert len(files) == 1
    assert files[0]["message_ts"] == "1234567890.000001"


def test_load_channel_files_channel_canvas_omits_message_ts(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)
    _make_file_db(channel_dir / "slackdump.sqlite", [CANVAS_FILE])

    files = export_logic._load_channel_files(channel_dir)

    assert len(files) == 1
    assert "message_ts" not in files[0]


def test_load_channel_files_dedupes_prefers_message_attached_over_channel_canvas(tmp_path):
    channel_dir = tmp_path / "f3pugetsound" / "ao-active-book-club"
    channel_dir.mkdir(parents=True)

    # Create two rows for the same file: one with MESSAGE_ID, one without
    db_path = channel_dir / "slackdump.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE FILE (ID TEXT, DATA TEXT, MESSAGE_ID TEXT)")
    # First row: channel canvas (MESSAGE_ID is null)
    conn.execute("INSERT INTO FILE (ID, DATA, MESSAGE_ID) VALUES (?, ?, ?)",
                 (CANVAS_FILE["id"], json.dumps(CANVAS_FILE), None))
    # Second row: same file attached to a message
    conn.execute("INSERT INTO FILE (ID, DATA, MESSAGE_ID) VALUES (?, ?, ?)",
                 (CANVAS_FILE["id"], json.dumps(CANVAS_FILE), "1234567890.000001"))
    conn.commit()
    conn.close()

    files = export_logic._load_channel_files(channel_dir)

    assert len(files) == 1
    assert files[0]["message_ts"] == "1234567890.000001"


def test_build_digest_channel_url_present_on_ok_channels(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    meta = next(c for c in result["channels"] if c["channel_id"] == "C1")
    assert meta["channel_url"] == "https://f3pugetsound.slack.com/archives/C1"
    assert meta["status"] == "ok"


def test_build_digest_channel_url_present_on_missing_archive_channels(tmp_path):
    archive_root = tmp_path / "archive"

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", None, "2026-06-23", _fake_convert,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    meta = next(c for c in result["channels"] if c["channel_id"] == "C1")
    assert meta["channel_url"] == "https://f3pugetsound.slack.com/archives/C1"
    assert meta["status"] == "missing_archive"


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
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_with_emeritus,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["leadership"]["by_region"] == []
    former = result["leadership"]["former_by_region"]
    assert len(former) == 1
    role = former[0]["roles"][0]
    assert role["status"] == "emeritus"
    assert role["is_current"] is False


def test_build_digest_title_high_role_wins_confidence_and_currency(tmp_path):
    # A profile carrying both a display-name (medium_high) and an explicit
    # title (high) role for the same region/position merges into one rollup
    # group. The group must report the title's "high" confidence (not the
    # display name's "medium_high") and, since its status resolves to
    # "current", is_current must be True - not None.
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    def convert_with_title(channel_dir: Path, out_dir: Path) -> None:
        _fake_convert(channel_dir, out_dir)
        users = json.loads((out_dir / "users.json").read_text())
        users.append({
            "id": "ULEADER", "name": "columbia", "real_name": "Real Columbia",
            "profile": {
                "display_name": "Columbia - Cascades Region Nantan",
                "title": "Cascades Nantan",
            },
        })
        (out_dir / "users.json").write_text(json.dumps(users))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_with_title,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    by_region = result["leadership"]["by_region"]
    assert len(by_region) == 1
    role = by_region[0]["roles"][0]
    assert role["position"] == "Nantan"
    assert role["confidence"] == "high"
    assert role["status"] == "current"
    assert role["is_current"] is True
    assert result["leadership"]["former_by_region"] == []


def test_enrich_for_digest_reply_has_thread_ts_parent_does_not():
    """Replies carry thread_ts equal to parent ts; roots have no thread_ts."""
    parent = {"ts": "1000.000100", "user": "U0A", "text": "parent message"}
    reply = {"ts": "1100.000100", "user": "U0B", "text": "reply"}
    parent["replies"] = [reply]

    export_logic._enrich_for_digest(parent, "f3pugetsound", "helpdesk", "C1")

    assert "thread_ts" not in parent
    assert parent["posted_at_local"] == export_logic._format_local_pacific(1000.0001)
    assert reply["thread_ts"] == "1000.000100"
    assert reply["posted_at_local"] == export_logic._format_local_pacific(1100.0001)


def test_extract_mentions_order_and_dedupe():
    text = "hey <@U0B> and <@U0A>, also <@U0B> again"
    assert export_logic._extract_mentions(text) == ["U0B", "U0A"]


def test_extract_mentions_empty_when_no_tokens():
    assert export_logic._extract_mentions("no mentions here, just <#C123> and <!here>") == []


def test_extract_links_bare_url_has_null_label():
    links = export_logic._extract_links("check <https://example.com/page>")
    assert links == [{"url": "https://example.com/page", "label": None, "type": "external"}]


def test_extract_links_labeled_url():
    links = export_logic._extract_links("see <https://example.com/page|the docs>")
    assert links[0]["label"] == "the docs"
    assert links[0]["type"] == "external"


def test_extract_links_slack_message_link_yields_target_channel_and_ts():
    text = "look at <https://f3pugetsound.slack.com/archives/C123/p1778086219226429|this>"
    links = export_logic._extract_links(text)
    assert links[0]["type"] == "slack_message"
    assert links[0]["target_channel_id"] == "C123"
    assert links[0]["target_ts"] == "1778086219.226429"


def test_extract_links_slack_file_link():
    text = "doc <https://f3pugetsound.slack.com/files/U0A/F123/canvas>"
    links = export_logic._extract_links(text)
    assert links[0]["type"] == "slack_file"


def test_select_messages_in_range_carries_mentions_and_links():
    users_map = {"U0A": "Al"}
    all_messages = [
        {
            "ts": "1000.000100", "user": "U0A",
            "text": "hey <@U0B> check <https://example.com/page>",
        },
    ]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert messages[0]["mentions"] == ["U0B"]
    assert messages[0]["links"] == [{"url": "https://example.com/page", "label": None, "type": "external"}]
    # text is untouched - raw tokens survive verbatim.
    assert messages[0]["text"] == "hey <@U0B> check <https://example.com/page>"


def test_select_messages_in_range_omits_mentions_and_links_keys_when_absent():
    users_map = {"U0A": "Al"}
    all_messages = [{"ts": "1000.000100", "user": "U0A", "text": "plain text"}]

    messages = export_logic.select_messages_in_range(all_messages, users_map, 900.0, 1200.0)

    assert "mentions" not in messages[0]
    assert "links" not in messages[0]


def test_build_digest_user_index_includes_mentioned_never_posting_user_excludes_unreferenced(tmp_path):
    archive_root = tmp_path / "archive"
    channel_dir = archive_root / "f3pugetsound" / "helpdesk"
    channel_dir.mkdir(parents=True)
    (channel_dir / "slackdump.sqlite").write_bytes(b"")

    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"},
    ]))

    def convert_fn(channel_dir: Path, out_dir: Path) -> None:
        out = out_dir / "helpdesk"
        out.mkdir(parents=True)
        (out_dir / "users.json").write_text(json.dumps([
            {"id": "U0A", "name": "alice.a", "real_name": "Alice Anderson", "profile": {"display_name": "Al"}},
            {"id": "U0MENTIONED", "name": "mo", "real_name": "Mo Mentioned",
             "profile": {"display_name": "Mo"}},
            {"id": "U0UNUSED", "name": "un", "real_name": "Un Referenced",
             "profile": {"display_name": "Un"}},
        ]))
        (out / "2026-06-01.json").write_text(json.dumps([
            {"type": "message", "user": "U0A", "ts": "1780300800.000100", "text": "hey <@U0MENTIONED>"},
        ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_fn,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    ws_index = result["user_index"]["f3pugetsound"]
    assert ws_index["U0A"] == {"display_name": "Al", "is_bot": False}
    assert ws_index["U0MENTIONED"] == {"display_name": "Mo", "is_bot": False}
    assert "U0UNUSED" not in ws_index


def test_build_digest_user_index_scoped_per_workspace_for_shared_user_id(tmp_path):
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

    def convert_fn(channel_dir: Path, out_dir: Path) -> None:
        workspace = channel_dir.parent.name
        out = out_dir / "helpdesk"
        out.mkdir(parents=True)
        display_name = "Puget Al" if workspace == "f3pugetsound" else "Kirkland Al"
        (out_dir / "users.json").write_text(json.dumps([
            {"id": "U0SAME", "name": "same", "real_name": "Same Real Name",
             "profile": {"display_name": display_name}},
        ]))
        (out / "2026-06-01.json").write_text(json.dumps([
            {"type": "message", "user": "U0SAME", "ts": "1780300800.000100", "text": "hi"},
        ]))

    result = export_logic.build_digest(
        channels_file, archive_root, "f3*", None, "2026-06-23", convert_fn,
        catalog_cache_dir=tmp_path / "empty-cache",
    )

    assert result["user_index"]["f3pugetsound"]["U0SAME"]["display_name"] == "Puget Al"
    assert result["user_index"]["f3kirkland"]["U0SAME"]["display_name"] == "Kirkland Al"


def test_enrich_for_digest_posted_at_local_has_dst_offset():
    """January timestamp shows -08:00 offset; July shows -07:00."""
    # 2026-01-15 00:00:00 UTC = epoch 1736899200
    jan_ts = 1736899200.000100
    # 2026-07-15 00:00:00 UTC = epoch 1752604800
    jul_ts = 1752604800.000100

    jan_local = export_logic._format_local_pacific(jan_ts)
    jul_local = export_logic._format_local_pacific(jul_ts)

    assert "-08:00" in jan_local
    assert "-07:00" in jul_local
