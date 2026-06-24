import json

import pytest

from slackbackup import channel_logic


def write_json(path, data):
    path.write_text(json.dumps(data))


def test_validate_accepts_valid_single_and_multi_channel(tmp_path):
    f = tmp_path / "c.json"
    write_json(f, [{"id": "C1", "name": "general", "workspace": "acme"}])
    assert channel_logic.validate(f)

    write_json(f, [
        {"id": "C1", "name": "general", "workspace": "acme"},
        {"id": "C2", "name": "helpdesk", "workspace": "acme"},
    ])
    assert channel_logic.validate(f)


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"id": "C1", "name": "general", "workspace": "acme"},
        [{"name": "general", "workspace": "acme"}],
        [{"id": "", "name": "general", "workspace": "acme"}],
        [{"id": "C1", "name": "", "workspace": "acme"}],
        [{"id": "C1", "name": "general"}],
    ],
)
def test_validate_rejects_invalid_shapes(tmp_path, data):
    f = tmp_path / "c.json"
    write_json(f, data)
    with pytest.raises(channel_logic.ChannelError):
        channel_logic.validate(f)


def test_validate_rejects_malformed_json(tmp_path):
    f = tmp_path / "c.json"
    f.write_text("not valid json")
    with pytest.raises(channel_logic.ChannelError):
        channel_logic.validate(f)


def test_validate_rejects_missing_file(tmp_path):
    with pytest.raises(channel_logic.ChannelError, match="file not found"):
        channel_logic.validate(tmp_path / "does-not-exist.json")


def test_register_appends_new_channel(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.catalog_logic, "lookup",
        lambda ws, q: [("C1", {"name": "general", "member": True, "description": ""})],
    )

    channel_id, name, already_present = channel_logic.register("f3test", "general", channels_file)
    assert (channel_id, name, already_present) == ("C1", "general", False)
    assert json.loads(channels_file.read_text()) == [
        {"id": "C1", "name": "general", "workspace": "f3test"}
    ]


def test_register_is_idempotent_on_existing_entry(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    write_json(channels_file, [{"id": "C1", "name": "general", "workspace": "f3test"}])
    monkeypatch.setattr(
        channel_logic.catalog_logic, "lookup",
        lambda ws, q: [("C1", {"name": "general", "member": True, "description": ""})],
    )

    channel_id, name, already_present = channel_logic.register("f3test", "general", channels_file)
    assert already_present is True
    assert json.loads(channels_file.read_text()) == [
        {"id": "C1", "name": "general", "workspace": "f3test"}
    ]


def test_register_strips_leading_hash(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    captured = {}

    def fake_lookup(ws, query):
        captured["query"] = query
        return [("C1", {"name": "general", "member": True, "description": ""})]

    monkeypatch.setattr(channel_logic.catalog_logic, "lookup", fake_lookup)
    channel_logic.register("f3test", "#general", channels_file)
    assert captured["query"] == "general"


def test_register_raises_on_no_match(tmp_path, monkeypatch):
    monkeypatch.setattr(channel_logic.catalog_logic, "lookup", lambda ws, q: [])
    with pytest.raises(channel_logic.ChannelError, match="no channel matching"):
        channel_logic.register("f3test", "nonexistent", tmp_path / "channels.json")


def test_register_raises_on_ambiguous_match(tmp_path, monkeypatch):
    monkeypatch.setattr(
        channel_logic.catalog_logic, "lookup",
        lambda ws, q: [("C1", {"name": "x"}), ("C2", {"name": "x"})],
    )
    with pytest.raises(channel_logic.ChannelError, match="more than one channel"):
        channel_logic.register("f3test", "x", tmp_path / "channels.json")


def test_list_for_workspace_marks_registered_status(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    write_json(channels_file, [{"id": "C1", "name": "general", "workspace": "f3test"}])

    monkeypatch.setattr(
        channel_logic.catalog_logic, "refresh_fast",
        lambda ws: {
            "channels": {
                "C1": {"member": True, "name": "general", "description": ""},
                "C2": {"member": True, "name": "random", "description": ""},
                "C3": {"member": False, "name": "not-a-member", "description": ""},
            }
        },
    )

    rows = channel_logic.list_for_workspace("f3test", channels_file)
    by_id = {row["id"]: row for row in rows}

    assert by_id["C1"]["registered"] is True
    assert by_id["C2"]["registered"] is False
    assert "C3" not in by_id  # non-member channels excluded from the fast-tier view
