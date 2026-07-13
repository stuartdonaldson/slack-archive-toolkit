"""Ports every scenario from scripts/test_export_monthly.sh against the
exact same fixtures (scripts/test_fixtures/export-archive/) - this is the
parity guarantee for the most complex piece of the rewrite.
"""
import json
import shutil
from pathlib import Path

import pytest

from slackbackup import export_logic

FIXTURE = Path(__file__).parent.parent / "scripts" / "test_fixtures" / "export-archive"
WS = "f3pugetsound"
CH = "helpdesk"

A_TS = "1775811600.000100"
A1_TS = "1775811900.000100"
A2_TS = "1775901600.000100"
B_TS = "1776686400.000100"
B1_TS = "1777708800.000100"
C_TS = "1778853600.000100"
D_TS = "1778853600.000100"
BOT_TS = "1780660800.000100"


def _by_ts(messages, ts):
    matches = [m for m in messages if m["ts"] == ts]
    return matches[0] if matches else None


def test_monthly_split_and_naming(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)

    apr = out / f"{WS}-{CH}-2026-04.json"
    may = out / f"{WS}-{CH}-2026-05.json"
    jun = out / f"{WS}-{CH}-2026-06.json"
    assert apr.exists() and may.exists() and jun.exists()
    assert len(list(out.glob("*.json"))) == 3


def test_metadata_fields(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    april = json.loads((out / f"{WS}-{CH}-2026-04.json").read_text())

    assert april["workspace"] == WS
    assert april["channel"] == CH
    assert april["month"] == "2026-04"
    assert april["range"] == {"from": "2026-04-01", "to": "2026-04-30"}


def test_nesting_parent_a_has_two_ordered_replies(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    april = json.loads((out / f"{WS}-{CH}-2026-04.json").read_text())

    matches = [m for m in april["messages"] if m["ts"] == A_TS]
    assert len(matches) == 1
    parent_a = matches[0]
    assert [r["ts"] for r in parent_a["replies"]] == [A1_TS, A2_TS]

    assert _by_ts(april["messages"], A1_TS) is None
    assert _by_ts(april["messages"], A2_TS) is None


def test_display_name_resolution(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    april = json.loads((out / f"{WS}-{CH}-2026-04.json").read_text())

    parent_a = _by_ts(april["messages"], A_TS)
    assert parent_a["user"] == "U0A"
    assert parent_a["display_name"] == "Al"
    assert parent_a["replies"][0]["display_name"] == "Bob Baker"


def test_display_name_falls_back_to_raw_id_when_unmapped(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    may = json.loads((out / f"{WS}-{CH}-2026-05.json").read_text())

    assert may["messages"][0]["display_name"] == "U0E"


def test_bot_message_uses_bot_id_and_username(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    june = json.loads((out / f"{WS}-{CH}-2026-06.json").read_text())

    bot_msg = _by_ts(june["messages"], BOT_TS)
    assert bot_msg["user"] == "B0BOT"
    assert bot_msg["display_name"] == "Backblast Bot"


def test_files_reduced_to_name_filetype_permalink(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    april = json.loads((out / f"{WS}-{CH}-2026-04.json").read_text())

    parent_a = _by_ts(april["messages"], A_TS)
    assert len(parent_a["files"]) == 1
    assert set(parent_a["files"][0].keys()) == {"id", "name", "filetype", "permalink"}
    assert parent_a["files"][0]["name"] == "printer-error.jpg"


def test_noise_stripping_only_expected_keys_survive(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    april = json.loads((out / f"{WS}-{CH}-2026-04.json").read_text())

    parent_a = _by_ts(april["messages"], A_TS)
    assert set(parent_a.keys()) == {"display_name", "files", "replies", "text", "ts", "user"}


def test_cross_month_thread_stays_whole_in_parents_month(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    april = json.loads((out / f"{WS}-{CH}-2026-04.json").read_text())
    may = json.loads((out / f"{WS}-{CH}-2026-05.json").read_text())

    parent_b = _by_ts(april["messages"], B_TS)
    assert len(parent_b["replies"]) == 1
    assert parent_b["replies"][0]["ts"] == B1_TS
    assert _by_ts(may["messages"], B1_TS) is None


def test_may_has_only_standalone_message_with_no_replies_key(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)
    may = json.loads((out / f"{WS}-{CH}-2026-05.json").read_text())

    assert len(may["messages"]) == 1
    assert may["messages"][0]["ts"] == C_TS
    assert "replies" not in may["messages"][0]


def test_range_bounding_narrow_window_emits_one_file(tmp_path):
    out = tmp_path / "out3"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-05-01", "2026-05-31", out)

    assert (out / f"{WS}-{CH}-2026-05.json").exists()
    assert len(list(out.glob("*.json"))) == 1


def test_idempotency_seals_past_months_rewrites_trailing(tmp_path):
    out = tmp_path / "out1"
    out.mkdir()
    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out)

    apr = out / f"{WS}-{CH}-2026-04.json"
    may = out / f"{WS}-{CH}-2026-05.json"
    apr_before = apr.read_bytes()
    may_before = may.read_bytes()

    results = dict(export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out))

    assert results["2026-04"] == "skipped"
    assert results["2026-05"] == "skipped"
    assert results["2026-06"] == "rewrote_trailing"
    assert apr.read_bytes() == apr_before
    assert may.read_bytes() == may_before


def test_late_reply_reopens_a_sealed_month(tmp_path):
    late_fixture = tmp_path / "late-reply-fixture"
    shutil.copytree(FIXTURE, late_fixture)
    out = tmp_path / "out7"
    out.mkdir()

    export_logic.export_transform(late_fixture, WS, CH, "2026-04-01", "2026-06-30", out)
    april = json.loads((out / f"{WS}-{CH}-2026-04.json").read_text())
    assert len(_by_ts(april["messages"], A_TS)["replies"]) == 2

    late_reply_ts = "1782900000.000100"
    (late_fixture / CH / "2026-07-01.json").write_text(json.dumps([
        {"type": "message", "user": "U0B", "ts": late_reply_ts, "thread_ts": A_TS,
         "text": "reply A3 — very late reply, arrives in July"}
    ]))

    results = dict(export_logic.export_transform(late_fixture, WS, CH, "2026-04-01", "2026-06-30", out))
    assert results["2026-04"] == "rewrote_late"

    april = json.loads((out / f"{WS}-{CH}-2026-04.json").read_text())
    replies = _by_ts(april["messages"], A_TS)["replies"]
    assert len(replies) == 3
    assert replies[2]["ts"] == late_reply_ts


def test_seal_stamp_past_month_end_seals_trailing_month(tmp_path):
    out = tmp_path / "out5"
    out.mkdir()
    stamp = tmp_path / ".last_backup"
    stamp.write_text("2026-07-01T00:00:00Z\n")

    results_a = dict(export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out, stamp))
    assert results_a["2026-06"] == "wrote"

    results_b = dict(export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out, stamp))
    assert results_b["2026-06"] == "skipped"


def test_seal_stamp_within_month_does_not_seal_it(tmp_path):
    out = tmp_path / "out6"
    out.mkdir()
    stamp = tmp_path / ".last_backup"
    stamp.write_text("2026-06-10T00:00:00Z\n")

    export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out, stamp)
    results = dict(export_logic.export_transform(FIXTURE, WS, CH, "2026-04-01", "2026-06-30", out, stamp))

    assert results["2026-06"] == "rewrote_trailing"
