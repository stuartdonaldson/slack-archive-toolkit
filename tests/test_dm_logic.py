import json

from slackbackup import dm_logic


def write_json(path, data):
    path.write_text(json.dumps(data))


def _fake_status(known):
    return lambda: {"known": known, "others": []}


def test_register_matching_discovers_plain_and_group_dms(tmp_path, monkeypatch):
    dms_file = tmp_path / "dms.json"
    monkeypatch.setattr(
        dm_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(dm_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(
        dm_logic.slackdump, "list_dms",
        lambda include_group=True: [
            {"id": "D1", "name": "", "is_im": True, "user": "U1"},
            {"id": "C2", "name": "mpdm-alice--bob-1", "is_mpim": True},
        ],
    )

    result = dm_logic.register_matching("f3pugetsound", dms_file)

    added = {(e["id"], e["name"], e["workspace"]) for e in result["added"]}
    assert added == {
        ("D1", "dm-U1", "f3pugetsound"),
        ("C2", "mpdm-alice--bob-1", "f3pugetsound"),
    }
    saved = json.loads(dms_file.read_text())
    assert {(e["id"], e["name"], e["workspace"]) for e in saved} == added


def test_register_matching_excludes_group_dms_when_disabled(tmp_path, monkeypatch):
    dms_file = tmp_path / "dms.json"
    monkeypatch.setattr(
        dm_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(dm_logic.slackdump, "select_workspace_or_die", lambda ws: None)

    captured = {}

    def fake_list_dms(include_group=True):
        captured["include_group"] = include_group
        return [{"id": "D1", "name": "", "is_im": True, "user": "U1"}]

    monkeypatch.setattr(dm_logic.slackdump, "list_dms", fake_list_dms)

    result = dm_logic.register_matching("f3pugetsound", dms_file, include_group=False)

    assert captured["include_group"] is False
    assert [e["id"] for e in result["added"]] == ["D1"]


def test_register_matching_skips_already_registered(tmp_path, monkeypatch):
    dms_file = tmp_path / "dms.json"
    write_json(dms_file, [{"id": "D1", "name": "dm-U1", "workspace": "f3pugetsound"}])
    monkeypatch.setattr(
        dm_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(dm_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(
        dm_logic.slackdump, "list_dms",
        lambda include_group=True: [{"id": "D1", "name": "", "is_im": True, "user": "U1"}],
    )

    result = dm_logic.register_matching("f3pugetsound", dms_file)

    assert result["added"] == []
    saved = json.loads(dms_file.read_text())
    assert len(saved) == 1


def test_register_matching_prunes_dms_no_longer_present(tmp_path, monkeypatch):
    dms_file = tmp_path / "dms.json"
    write_json(dms_file, [
        {"id": "D1", "name": "dm-U1", "workspace": "f3pugetsound"},
        {"id": "D2", "name": "dm-U2", "workspace": "f3pugetsound"},
    ])
    monkeypatch.setattr(
        dm_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(dm_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(
        dm_logic.slackdump, "list_dms",
        lambda include_group=True: [{"id": "D1", "name": "", "is_im": True, "user": "U1"}],
    )

    result = dm_logic.register_matching("f3pugetsound", dms_file)

    assert [e["id"] for e in result["removed"]] == ["D2"]
    saved = json.loads(dms_file.read_text())
    assert [e["id"] for e in saved] == ["D1"]


def test_register_matching_skips_unregistered_workspaces(tmp_path, monkeypatch):
    dms_file = tmp_path / "dms.json"
    monkeypatch.setattr(
        dm_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": False}]),
    )

    result = dm_logic.register_matching("f3pugetsound", dms_file)

    assert result["workspaces_checked"] == []
    assert result["workspaces_skipped_unregistered"] == ["f3pugetsound"]
