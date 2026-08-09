import json
import sqlite3

import pytest

from slackbackup import bot_images_logic


def _make_db(path, messages):
    """messages: list of (ts, data_dict)."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE MESSAGE (ID INTEGER, CHUNK_ID INTEGER, TS TEXT, DATA TEXT)"
    )
    for i, (ts, data) in enumerate(messages):
        conn.execute(
            "INSERT INTO MESSAGE (ID, CHUNK_ID, TS, DATA) VALUES (?, ?, ?, ?)",
            (i, i, ts, json.dumps(data)),
        )
    conn.commit()
    conn.close()


def _msg_with_image(url):
    return {"blocks": [{"type": "image", "image_url": url}]}


def test_iter_image_blocks_finds_image_blocks(tmp_path):
    db_path = tmp_path / "slackdump.sqlite"
    _make_db(
        db_path,
        [
            ("1700000000.000001", _msg_with_image("https://storage.googleapis.com/f3-public-images/x.png")),
            ("1700000001.000002", {"text": "no image here"}),
        ],
    )
    found = list(bot_images_logic.iter_image_blocks(db_path))
    assert found == [("1700000000.000001", "https://storage.googleapis.com/f3-public-images/x.png")]


def test_iter_image_blocks_dedupes_duplicate_ts_rows(tmp_path):
    db_path = tmp_path / "slackdump.sqlite"
    url = "https://storage.googleapis.com/f3-public-images/x.png"
    _make_db(db_path, [("1700000000.000001", _msg_with_image(url))] * 3)
    found = list(bot_images_logic.iter_image_blocks(db_path))
    assert found == [("1700000000.000001", url)]


def test_target_filename_prefixes_date_from_ts():
    fname = bot_images_logic.target_filename(
        "1784304534.058099", "https://storage.googleapis.com/f3-public-images/event_instance_images/663445_low_res.png"
    )
    assert fname == "2026-07-17_663445_low_res.png"


def test_backfill_channel_no_db_returns_zero_stats(tmp_path):
    stats = bot_images_logic.backfill_channel(tmp_path)
    assert stats.found == 0
    assert stats.downloaded == 0


def test_backfill_channel_skips_auth_required_host(tmp_path, monkeypatch):
    db_path = tmp_path / "slackdump.sqlite"
    _make_db(
        db_path,
        [("1700000000.000001", _msg_with_image("https://files.slack.com/files-pri/T0-F0/img.png"))],
    )

    def _boom(*a, **kw):
        raise AssertionError("should never attempt to download an auth-required URL")

    monkeypatch.setattr(bot_images_logic.urllib.request, "urlretrieve", _boom)

    stats = bot_images_logic.backfill_channel(tmp_path)
    assert stats.found == 1
    assert stats.skipped_auth == 1
    assert stats.downloaded == 0
    assert not (tmp_path / bot_images_logic.DEFAULT_OUT_SUBDIR / "2023-11-14_img.png").exists()


def test_backfill_channel_downloads_and_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "slackdump.sqlite"
    url = "https://storage.googleapis.com/f3-public-images/x.png"
    _make_db(db_path, [("1700000000.000001", _msg_with_image(url))])

    calls = []

    def _fake_urlretrieve(fetch_url, dest):
        calls.append(fetch_url)
        dest.write_bytes(b"fake-image-bytes")

    monkeypatch.setattr(bot_images_logic.urllib.request, "urlretrieve", _fake_urlretrieve)

    stats = bot_images_logic.backfill_channel(tmp_path)
    assert stats.found == 1
    assert stats.downloaded == 1
    assert len(calls) == 1

    out_file = tmp_path / bot_images_logic.DEFAULT_OUT_SUBDIR / "2023-11-14_x.png"
    assert out_file.exists()

    # Second run: already on disk, must not re-download.
    stats2 = bot_images_logic.backfill_channel(tmp_path)
    assert stats2.downloaded == 0
    assert stats2.skipped_existing == 1
    assert len(calls) == 1


def test_backfill_channel_404_writes_gone_marker_and_does_not_retry(tmp_path, monkeypatch):
    """A confirmed-gone URL (e.g. F3 Nation's ephemeral calendar-preview
    thumbnails, which the bot's own service garbage-collects) must not be
    retried on every future backup cycle forever (SlackBackup sat-lqp)."""
    db_path = tmp_path / "slackdump.sqlite"
    url = "https://storage.googleapis.com/f3nation-calendar-images/x.png"
    _make_db(db_path, [("1700000000.000001", _msg_with_image(url))])

    calls = []

    def _404(*a, **kw):
        calls.append(1)
        raise bot_images_logic.urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(bot_images_logic.urllib.request, "urlretrieve", _404)

    stats = bot_images_logic.backfill_channel(tmp_path)
    assert stats.found == 1
    assert stats.skipped_gone == 1
    assert stats.failed == 0
    assert len(calls) == 1

    marker = tmp_path / bot_images_logic.DEFAULT_OUT_SUBDIR / ("2023-11-14_x.png" + bot_images_logic.GONE_MARKER_SUFFIX)
    assert marker.exists()

    # Second run must not retry the dead URL at all.
    stats2 = bot_images_logic.backfill_channel(tmp_path)
    assert stats2.skipped_gone == 1
    assert len(calls) == 1


def test_backfill_channel_non_404_error_still_retries(tmp_path, monkeypatch):
    """A transient failure (network blip, 500, etc.) must keep retrying on
    future runs, unlike a confirmed 404."""
    db_path = tmp_path / "slackdump.sqlite"
    url = "https://storage.googleapis.com/f3-public-images/x.png"
    _make_db(db_path, [("1700000000.000001", _msg_with_image(url))])

    def _500(*a, **kw):
        raise bot_images_logic.urllib.error.HTTPError(url, 500, "Server Error", None, None)

    monkeypatch.setattr(bot_images_logic.urllib.request, "urlretrieve", _500)

    stats = bot_images_logic.backfill_channel(tmp_path)
    assert stats.failed == 1
    assert stats.skipped_gone == 0
    marker = tmp_path / bot_images_logic.DEFAULT_OUT_SUBDIR / ("2023-11-14_x.png" + bot_images_logic.GONE_MARKER_SUFFIX)
    assert not marker.exists()


def test_backfill_channel_failed_download_is_non_fatal(tmp_path, monkeypatch):
    db_path = tmp_path / "slackdump.sqlite"
    url = "https://storage.googleapis.com/f3-public-images/x.png"
    _make_db(db_path, [("1700000000.000001", _msg_with_image(url))])

    def _boom(*a, **kw):
        raise OSError("network down")

    monkeypatch.setattr(bot_images_logic.urllib.request, "urlretrieve", _boom)

    stats = bot_images_logic.backfill_channel(tmp_path)
    assert stats.found == 1
    assert stats.failed == 1
    assert stats.downloaded == 0
