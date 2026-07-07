from slackbackup import catalog_logic


def _fresh():
    return {"channels": {}, "fast_refreshed_at": 0.0, "full_refreshed_at": 0.0}


CH1 = {"id": "C1", "name": "general", "topic": {"value": "T1"}, "purpose": {"value": ""}}
CH2 = {"id": "C2", "name": "helpdesk", "topic": {"value": ""}, "purpose": {"value": "P2"}}
CH3 = {"id": "C3", "name": "new-public", "topic": {"value": ""}, "purpose": {"value": "P3"}}


def test_description_prefers_topic_over_purpose():
    assert catalog_logic.description_of(CH1) == "T1"


def test_description_falls_back_to_purpose_when_topic_empty():
    assert catalog_logic.description_of(CH2) == "P2"


def test_description_empty_when_both_empty():
    ch = {"id": "C9", "name": "x", "topic": {"value": ""}, "purpose": {"value": ""}}
    assert catalog_logic.description_of(ch) == ""


def test_fast_merge_into_empty_catalog_produces_member_rows():
    data = catalog_logic.merge_fast(_fresh(), [CH1, CH2])
    assert data["channels"]["C1"] == {
        "member": True, "name": "general", "description": "T1", "topic": "T1", "is_private": False, "is_archived": False,
        "creator": None, "created": None,
    }
    assert data["channels"]["C2"] == {
        "member": True, "name": "helpdesk", "description": "P2", "topic": None, "is_private": False, "is_archived": False,
        "creator": None, "created": None,
    }


def test_merge_carries_private_and_archived_flags():
    private_ch = {"id": "C4", "name": "leadership", "topic": {"value": ""}, "purpose": {"value": ""}, "is_private": True}
    archived_ch = {"id": "C5", "name": "shuttered-ao", "topic": {"value": ""}, "purpose": {"value": ""}, "is_archived": True}
    data = catalog_logic.merge_full(_fresh(), [private_ch, archived_ch])
    assert data["channels"]["C4"]["is_private"] is True
    assert data["channels"]["C5"]["is_archived"] is True


def test_merge_carries_creator_and_created():
    ch = {
        "id": "C6", "name": "ao-foo", "topic": {"value": ""}, "purpose": {"value": ""},
        "creator": "U123", "created": 1700000000,
    }
    data = catalog_logic.merge_full(_fresh(), [ch])
    assert data["channels"]["C6"]["creator"] == "U123"
    assert data["channels"]["C6"]["created"] == 1700000000


def test_full_merge_adds_new_channel_as_not_member():
    data = catalog_logic.merge_fast(_fresh(), [CH1])
    data = catalog_logic.merge_full(data, [CH3])
    assert data["channels"]["C3"]["member"] is False


def test_full_merge_refreshes_description_without_clobbering_member_flag():
    data = catalog_logic.merge_fast(_fresh(), [CH1])
    updated_ch1 = {"id": "C1", "name": "general", "topic": {"value": "T1-updated"}, "purpose": {"value": ""}}
    data = catalog_logic.merge_full(data, [updated_ch1])
    assert data["channels"]["C1"] == {
        "member": True, "name": "general", "description": "T1-updated", "topic": "T1-updated",
        "is_private": False, "is_archived": False, "creator": None, "created": None,
    }


def test_rerunning_fast_tier_never_demotes_a_full_tier_only_channel():
    data = catalog_logic.merge_fast(_fresh(), [CH1])
    data = catalog_logic.merge_full(data, [CH3])
    data = catalog_logic.merge_fast(data, [CH1])
    assert data["channels"]["C3"]["member"] is False


def test_match_channels_by_exact_id():
    channels = {"C1": {"name": "general"}, "C2": {"name": "HelpDesk"}}
    assert catalog_logic.match_channels(channels, "C1") == [("C1", {"name": "general"})]


def test_match_channels_by_case_insensitive_name():
    channels = {"C1": {"name": "general"}, "C2": {"name": "HelpDesk"}}
    assert catalog_logic.match_channels(channels, "helpdesk") == [("C2", {"name": "HelpDesk"})]


def test_match_channels_no_match_returns_empty():
    channels = {"C1": {"name": "general"}}
    assert catalog_logic.match_channels(channels, "nonexistent") == []


def test_refresh_fast_skips_api_call_when_cache_is_fresh(tmp_path, monkeypatch):
    catalog_logic.save(tmp_path, "f3test", {"channels": {}, "fast_refreshed_at": 1000.0, "full_refreshed_at": 0.0})

    def boom(*a, **kw):
        raise AssertionError("should not call slackdump when cache is fresh")

    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", boom)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", boom)

    data = catalog_logic.refresh_fast("f3test", cache_dir=tmp_path, ttl=900, now=1500.0)
    assert data["fast_refreshed_at"] == 1000.0


def test_refresh_fast_calls_slackdump_when_cache_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", lambda member_only: [CH1])

    data = catalog_logic.refresh_fast("f3test", cache_dir=tmp_path, ttl=900, now=1000.0)
    assert data["channels"]["C1"]["member"] is True
    assert data["fast_refreshed_at"] == 1000.0


def test_lookup_falls_back_to_full_tier_on_fast_miss(tmp_path, monkeypatch):
    calls = []

    def fake_list_channels(member_only):
        calls.append(member_only)
        return [CH1] if member_only else [CH1, CH3]

    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", fake_list_channels)

    matches = catalog_logic.lookup("f3test", "new-public", cache_dir=tmp_path)
    assert matches == [
        ("C3", {
            "member": False, "name": "new-public", "description": "P3", "topic": None,
            "is_private": False, "is_archived": False, "creator": None, "created": None,
        })
    ]
    assert calls == [True, False]


def test_name_by_id_is_read_only_and_never_calls_slackdump(tmp_path, monkeypatch):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))

    def boom(*a, **kw):
        raise AssertionError("name_by_id must not call slackdump")

    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", boom)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", boom)

    assert catalog_logic.name_by_id("f3test", "C1", cache_dir=tmp_path) == "general"
    assert catalog_logic.name_by_id("f3test", "C404", cache_dir=tmp_path) == ""


def test_set_registered_at_stamps_when_unset(tmp_path):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))
    catalog_logic.set_registered_at(tmp_path, "f3test", "C1", "2026-06-24T00:00:00Z")
    data = catalog_logic.load(tmp_path, "f3test")
    assert data["channels"]["C1"]["registered_at"] == "2026-06-24T00:00:00Z"


def test_set_registered_at_does_not_overwrite_existing_value(tmp_path):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))
    catalog_logic.set_registered_at(tmp_path, "f3test", "C1", "2020-01-01T00:00:00Z")
    catalog_logic.set_registered_at(tmp_path, "f3test", "C1", "2026-06-24T00:00:00Z")
    data = catalog_logic.load(tmp_path, "f3test")
    assert data["channels"]["C1"]["registered_at"] == "2020-01-01T00:00:00Z"


def test_set_registered_at_is_noop_for_unknown_channel(tmp_path):
    catalog_logic.save(tmp_path, "f3test", _fresh())
    catalog_logic.set_registered_at(tmp_path, "f3test", "C404", "2026-06-24T00:00:00Z")
    data = catalog_logic.load(tmp_path, "f3test")
    assert "C404" not in data["channels"]


def test_update_last_posted_sets_value(tmp_path):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))
    catalog_logic.update_last_posted(tmp_path, "f3test", "C1", "2026-06-20T12:00:00Z")
    data = catalog_logic.load(tmp_path, "f3test")
    assert data["channels"]["C1"]["last_posted"] == "2026-06-20T12:00:00Z"


def test_update_last_posted_overwrites_previous_value(tmp_path):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))
    catalog_logic.update_last_posted(tmp_path, "f3test", "C1", "2026-01-01T00:00:00Z")
    catalog_logic.update_last_posted(tmp_path, "f3test", "C1", "2026-06-20T12:00:00Z")
    data = catalog_logic.load(tmp_path, "f3test")
    assert data["channels"]["C1"]["last_posted"] == "2026-06-20T12:00:00Z"


def test_update_last_posted_is_noop_for_none(tmp_path):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))
    catalog_logic.update_last_posted(tmp_path, "f3test", "C1", None)
    data = catalog_logic.load(tmp_path, "f3test")
    assert "last_posted" not in data["channels"]["C1"]


def test_effective_recency_prefers_last_posted_over_registered_at():
    catalog = {"channels": {"C1": {"last_posted": "2026-06-20T00:00:00Z", "registered_at": "2020-01-01T00:00:00Z"}}}
    assert catalog_logic.effective_recency(catalog, "C1") == "2026-06-20T00:00:00Z"


def test_effective_recency_falls_back_to_registered_at():
    catalog = {"channels": {"C1": {"registered_at": "2020-01-01T00:00:00Z"}}}
    assert catalog_logic.effective_recency(catalog, "C1") == "2020-01-01T00:00:00Z"


def test_effective_recency_empty_string_when_totally_unknown():
    catalog = {"channels": {}}
    assert catalog_logic.effective_recency(catalog, "C1") == ""


def test_record_check_stamps_last_checked_and_last_action(tmp_path):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))
    catalog_logic.record_check(tmp_path, "f3test", "C1", "2026-07-07", "skip")
    data = catalog_logic.load(tmp_path, "f3test")
    assert data["channels"]["C1"]["last_checked"] == "2026-07-07"
    assert data["channels"]["C1"]["last_action"] == "skip"


def test_record_check_does_not_touch_last_posted(tmp_path):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))
    catalog_logic.update_last_posted(tmp_path, "f3test", "C1", "2026-06-20T00:00:00Z")
    catalog_logic.record_check(tmp_path, "f3test", "C1", "2026-07-07", "skip")
    data = catalog_logic.load(tmp_path, "f3test")
    assert data["channels"]["C1"]["last_posted"] == "2026-06-20T00:00:00Z"


def test_record_check_is_noop_for_unknown_channel(tmp_path):
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), [CH1]))
    catalog_logic.record_check(tmp_path, "f3test", "C-unknown", "2026-07-07", "skip")
    data = catalog_logic.load(tmp_path, "f3test")
    assert "C-unknown" not in data["channels"]
