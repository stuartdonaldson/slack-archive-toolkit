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
        lambda ws, q, cache_dir=None: [("C1", {"name": "general", "member": True, "description": ""})],
    )

    channel_id, name, already_present = channel_logic.register("f3test", "general", channels_file, cache_dir=tmp_path / "cache")
    assert (channel_id, name, already_present) == ("C1", "general", False)
    assert json.loads(channels_file.read_text()) == [
        {"id": "C1", "name": "general", "workspace": "f3test"}
    ]


def test_register_is_idempotent_on_existing_entry(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    write_json(channels_file, [{"id": "C1", "name": "general", "workspace": "f3test"}])
    monkeypatch.setattr(
        channel_logic.catalog_logic, "lookup",
        lambda ws, q, cache_dir=None: [("C1", {"name": "general", "member": True, "description": ""})],
    )

    channel_id, name, already_present = channel_logic.register("f3test", "general", channels_file, cache_dir=tmp_path / "cache")
    assert already_present is True
    assert json.loads(channels_file.read_text()) == [
        {"id": "C1", "name": "general", "workspace": "f3test"}
    ]


def test_register_strips_leading_hash(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    captured = {}

    def fake_lookup(ws, query, cache_dir=None):
        captured["query"] = query
        return [("C1", {"name": "general", "member": True, "description": ""})]

    monkeypatch.setattr(channel_logic.catalog_logic, "lookup", fake_lookup)
    channel_logic.register("f3test", "#general", channels_file, cache_dir=tmp_path / "cache")
    assert captured["query"] == "general"


def test_register_raises_on_no_match(tmp_path, monkeypatch):
    monkeypatch.setattr(channel_logic.catalog_logic, "lookup", lambda ws, q, cache_dir=None: [])
    with pytest.raises(channel_logic.ChannelError, match="no channel matching"):
        channel_logic.register("f3test", "nonexistent", tmp_path / "channels.json", cache_dir=tmp_path / "cache")


def test_register_raises_on_ambiguous_match(tmp_path, monkeypatch):
    monkeypatch.setattr(
        channel_logic.catalog_logic, "lookup",
        lambda ws, q, cache_dir=None: [("C1", {"name": "x"}), ("C2", {"name": "x"})],
    )
    with pytest.raises(channel_logic.ChannelError, match="more than one channel"):
        channel_logic.register("f3test", "x", tmp_path / "channels.json", cache_dir=tmp_path / "cache")


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


@pytest.mark.parametrize("query,expected", [
    ("general", False), ("f3pugetsound", False), ("C0123", False),
    ("f3*", True), ("*", True), ("event-?", True), ("[ab]ot", True),
    ("f3pugetsound,f3kirkland", True),
])
def test_is_glob(query, expected):
    assert channel_logic.is_glob(query) is expected


def _fake_status(known):
    return lambda: {"known": known, "others": []}


def test_register_matching_registers_new_channels_matching_both_globs(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([
            {"name": "f3pugetsound", "registered": True},
            {"name": "f3kirkland", "registered": True},
            {"name": "dungeons-of-finn-hill", "registered": True},
        ]),
    )

    def fake_refresh_full(workspace, cache_dir=None):
        catalogs = {
            "f3pugetsound": {"channels": {
                "C1": {"member": True, "name": "helpdesk", "description": ""},
                "C2": {"member": False, "name": "disc-it", "description": ""},
            }},
            "f3kirkland": {"channels": {
                "C3": {"member": True, "name": "general", "description": ""},
            }},
        }
        return catalogs[workspace]

    monkeypatch.setattr(channel_logic.catalog_logic, "refresh_full", fake_refresh_full)

    result = channel_logic.register_matching("f3*", "*", channels_file, cache_dir=tmp_path / "cache")

    assert sorted(result["workspaces_checked"]) == ["f3kirkland", "f3pugetsound"]
    added = {(e["id"], e["workspace"]) for e in result["added"]}
    assert added == {("C1", "f3pugetsound"), ("C2", "f3pugetsound"), ("C3", "f3kirkland")}
    saved = json.loads(channels_file.read_text())
    assert {(e["id"], e["workspace"]) for e in saved} == added


def test_register_matching_skips_already_registered_channels(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    write_json(channels_file, [{"id": "C1", "name": "helpdesk", "workspace": "f3pugetsound"}])
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(
        channel_logic.catalog_logic, "refresh_full",
        lambda ws, cache_dir=None: {"channels": {
            "C1": {"member": True, "name": "helpdesk", "description": ""},
            "C2": {"member": False, "name": "disc-it", "description": ""},
        }},
    )

    result = channel_logic.register_matching("f3pugetsound", "*", channels_file, cache_dir=tmp_path / "cache")

    assert [e["id"] for e in result["added"]] == ["C2"]


def test_register_matching_filters_by_channel_glob(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(
        channel_logic.catalog_logic, "refresh_full",
        lambda ws, cache_dir=None: {"channels": {
            "C1": {"member": True, "name": "event-spring-fling", "description": ""},
            "C2": {"member": True, "name": "helpdesk", "description": ""},
        }},
    )

    result = channel_logic.register_matching("f3pugetsound", "event-*", channels_file, cache_dir=tmp_path / "cache")

    assert [e["id"] for e in result["added"]] == ["C1"]


def test_register_matching_accepts_comma_separated_workspace_and_channel_lists(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([
            {"name": "f3pugetsound", "registered": True},
            {"name": "f3kirkland", "registered": True},
            {"name": "dungeons-of-finn-hill", "registered": True},
        ]),
    )
    monkeypatch.setattr(
        channel_logic.catalog_logic, "refresh_full",
        lambda ws, cache_dir=None: {
            "f3pugetsound": {"channels": {
                "C1": {"member": True, "name": "helpdesk", "description": ""},
                "C2": {"member": True, "name": "event-spring-fling", "description": ""},
            }},
            "f3kirkland": {"channels": {
                "C3": {"member": True, "name": "helpdesk", "description": ""},
            }},
        }[ws],
    )

    result = channel_logic.register_matching(
        "f3pugetsound,f3kirkland", "helpdesk,event-*", channels_file, cache_dir=tmp_path / "cache"
    )

    assert sorted(result["workspaces_checked"]) == ["f3kirkland", "f3pugetsound"]
    assert {(e["workspace"], e["name"]) for e in result["added"]} == {
        ("f3pugetsound", "helpdesk"),
        ("f3pugetsound", "event-spring-fling"),
        ("f3kirkland", "helpdesk"),
    }


def test_register_matching_reports_unregistered_workspaces_without_erroring(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([
            {"name": "f3pugetsound", "registered": True},
            {"name": "f3northsea", "registered": False},
        ]),
    )
    monkeypatch.setattr(
        channel_logic.catalog_logic, "refresh_full",
        lambda ws, cache_dir=None: {"channels": {}},
    )

    result = channel_logic.register_matching("f3*", "*", channels_file, cache_dir=tmp_path / "cache")

    assert result["workspaces_skipped_unregistered"] == ["f3northsea"]
    assert result["workspaces_checked"] == ["f3pugetsound"]


def test_register_matching_writes_nothing_when_no_new_channels_found(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(channel_logic.catalog_logic, "refresh_full", lambda ws, cache_dir=None: {"channels": {}})

    result = channel_logic.register_matching("f3pugetsound", "*", channels_file, cache_dir=tmp_path / "cache")

    assert result["added"] == []
    assert not channels_file.exists()


def test_register_matching_skips_private_and_archived_channels(tmp_path, monkeypatch):
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(
        channel_logic.catalog_logic, "refresh_full",
        lambda ws, cache_dir=None: {"channels": {
            "C1": {"member": True, "name": "helpdesk", "is_private": False, "is_archived": False},
            "C2": {"member": True, "name": "leadership-private", "is_private": True, "is_archived": False},
            "C3": {"member": False, "name": "shuttered-ao", "is_private": False, "is_archived": True},
        }},
    )

    result = channel_logic.register_matching("f3pugetsound", "*", channels_file, cache_dir=tmp_path / "cache")

    assert [e["id"] for e in result["added"]] == ["C1"]


def test_register_matching_skips_shuttered_named_channels_even_when_not_archived(tmp_path, monkeypatch):
    # Confirmed against real data: Slack's is_archived flag does not
    # reliably reflect this F3 community's own "shuttered-*" naming
    # convention for a closed-out AO - name is the only reliable signal.
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(
        channel_logic.catalog_logic, "refresh_full",
        lambda ws, cache_dir=None: {"channels": {
            "C1": {"member": True, "name": "helpdesk", "is_private": False, "is_archived": False},
            "C2": {"member": False, "name": "Shuttered-AO-Heritage-Park", "is_private": False, "is_archived": False},
        }},
    )

    result = channel_logic.register_matching("f3pugetsound", "*", channels_file, cache_dir=tmp_path / "cache")

    assert [e["id"] for e in result["added"]] == ["C1"]


def test_register_matching_stamps_registered_at_in_catalog(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(
        channel_logic.workspace_logic, "status",
        _fake_status([{"name": "f3pugetsound", "registered": True}]),
    )
    monkeypatch.setattr(channel_logic.catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(
        channel_logic.catalog_logic.slackdump, "list_channels",
        lambda member_only: [{"id": "C1", "name": "helpdesk", "topic": {"value": ""}, "purpose": {"value": ""}}],
    )

    channel_logic.register_matching("f3pugetsound", "*", channels_file, cache_dir=cache_dir)

    catalog = channel_logic.catalog_logic.load(cache_dir, "f3pugetsound")
    assert catalog["channels"]["C1"]["registered_at"] is not None


def test_register_stamps_registered_at_in_catalog(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channel_logic.catalog_logic.save(
        cache_dir, "f3test",
        {"channels": {"C1": {"member": True, "name": "general", "description": ""}},
         "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )
    monkeypatch.setattr(
        channel_logic.catalog_logic, "lookup",
        lambda ws, q, cache_dir=None: [("C1", {"name": "general", "member": True, "description": ""})],
    )

    channel_logic.register("f3test", "general", channels_file, cache_dir=cache_dir)

    catalog = channel_logic.catalog_logic.load(cache_dir, "f3test")
    assert catalog["channels"]["C1"]["registered_at"] is not None


def test_register_does_not_overwrite_existing_registered_at(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    channels_file = tmp_path / "channels.json"
    channel_logic.catalog_logic.save(
        cache_dir, "f3test",
        {"channels": {"C1": {"member": True, "name": "general", "description": "", "registered_at": "2020-01-01T00:00:00Z"}},
         "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0},
    )
    monkeypatch.setattr(
        channel_logic.catalog_logic, "lookup",
        lambda ws, q, cache_dir=None: [("C1", {"name": "general", "member": True, "description": ""})],
    )

    channel_logic.register("f3test", "general", channels_file, cache_dir=cache_dir)

    catalog = channel_logic.catalog_logic.load(cache_dir, "f3test")
    assert catalog["channels"]["C1"]["registered_at"] == "2020-01-01T00:00:00Z"
