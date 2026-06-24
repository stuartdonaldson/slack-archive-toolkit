from slackbackup import export_logic


def _touch(out_dir, name):
    (out_dir / name).write_text("{}")


def test_list_exports_unfiltered_best_effort_split(tmp_path):
    _touch(tmp_path, "f3pugetsound-helpdesk-2026-04.json")
    rows = export_logic.list_exports(tmp_path)
    assert rows == [{"workspace": "f3pugetsound", "channel": "helpdesk", "month": "2026-04", "path": tmp_path / "f3pugetsound-helpdesk-2026-04.json"}]


def test_list_exports_filtered_by_workspace_and_channel_resolves_hyphenated_names_exactly(tmp_path):
    # Both workspace and channel contain hyphens - ambiguous to split blindly,
    # but exact when both filters are given.
    _touch(tmp_path, "dungeons-of-finn-hill-all-f3-cascades-2026-04.json")

    rows = export_logic.list_exports(tmp_path, workspace="dungeons-of-finn-hill", channel="all-f3-cascades")
    assert len(rows) == 1
    assert rows[0]["workspace"] == "dungeons-of-finn-hill"
    assert rows[0]["channel"] == "all-f3-cascades"
    assert rows[0]["month"] == "2026-04"


def test_list_exports_filtered_by_workspace_only_resolves_hyphenated_channel(tmp_path):
    _touch(tmp_path, "f3cascades-all-f3-cascades-2026-05.json")

    rows = export_logic.list_exports(tmp_path, workspace="f3cascades")
    assert len(rows) == 1
    assert rows[0]["channel"] == "all-f3-cascades"
    assert rows[0]["month"] == "2026-05"


def test_list_exports_filtered_by_channel_only_resolves_hyphenated_workspace(tmp_path):
    _touch(tmp_path, "dungeons-of-finn-hill-ai-coding-2026-05.json")

    rows = export_logic.list_exports(tmp_path, channel="ai-coding")
    assert len(rows) == 1
    assert rows[0]["workspace"] == "dungeons-of-finn-hill"
    assert rows[0]["month"] == "2026-05"


def test_list_exports_unrelated_files_are_ignored(tmp_path):
    _touch(tmp_path, "not-an-export-file.json")
    _touch(tmp_path, "f3test-general-2026-01.json")

    rows = export_logic.list_exports(tmp_path)
    assert len(rows) == 1
    assert rows[0]["month"] == "2026-01"


def test_list_exports_no_matches_for_wrong_filter(tmp_path):
    _touch(tmp_path, "f3test-general-2026-01.json")
    rows = export_logic.list_exports(tmp_path, workspace="other-workspace")
    assert rows == []
