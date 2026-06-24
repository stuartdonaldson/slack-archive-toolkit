"""Tests for the LLM digest export: one merged document spanning the
trailing N months across every f3* workspace. Separate from
test_export_logic.py (the per-channel-month exporter) - different schema,
same underlying fixtures.
"""
import json
import shutil
from pathlib import Path

from slackbackup import export_logic

FIXTURE = Path(__file__).parent.parent / "scripts" / "test_fixtures" / "export-archive"

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
    assert result["leadership"] == {"raw_profile_matches": [], "by_region": []}


def test_derive_leadership_none_for_plain_display_name():
    assert export_logic.derive_leadership("Al") is None
    assert export_logic.derive_leadership(None) is None
    assert export_logic.derive_leadership("") is None


def test_derive_leadership_matches_title_and_region():
    signal = export_logic.derive_leadership("Columbia - Cascades Region Nantan")
    assert signal["possible_f3_name"] == "Columbia"
    assert signal["possible_region"] == "F3 Cascades"
    assert signal["possible_roles"] == [
        {"position": "Nantan", "basis": "display_name", "confidence": "medium_high", "needs_confirmation": True}
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
    )

    # The leader never posted in-range, so doesn't appear in messages...
    assert not any(m.get("user") == "ULEADER" for m in result["messages"])
    # ...but still surfaces in leadership, since that's scanned from the
    # full roster, not just posters.
    assert result["leadership"]["raw_profile_matches"] == [
        {
            "id": "ULEADER",
            "workspace": "f3pugetsound",
            "display_name": "Columbia - Cascades Region Nantan",
            "real_name": "Real Columbia",
            "is_bot": False,
            "derived": {
                "possible_f3_name": "Columbia",
                "possible_region": "F3 Cascades",
                "possible_roles": [
                    {"position": "Nantan", "basis": "display_name", "confidence": "medium_high", "needs_confirmation": True}
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
    )

    assert len(result["leadership"]["raw_profile_matches"]) == 2  # one per workspace account
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
    )

    assert result["channels"] == [
        {"workspace": "f3pugetsound", "channel": "helpdesk", "channel_id": "C1", "status": "missing_archive"}
    ]
    assert result["messages"] == []
