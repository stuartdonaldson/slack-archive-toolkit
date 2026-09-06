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
        "member": True, "name": "general", "description": "T1", "topic": "T1", "purpose": None,
        "is_private": False, "is_archived": False, "creator": None, "created": None,
    }
    assert data["channels"]["C2"] == {
        "member": True, "name": "helpdesk", "description": "P2", "topic": None, "purpose": "P2",
        "is_private": False, "is_archived": False, "creator": None, "created": None,
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
        "member": True, "name": "general", "description": "T1-updated", "topic": "T1-updated", "purpose": None,
        "is_private": False, "is_archived": False, "creator": None, "created": None,
    }


CADENCE_STATE = {
    "last_posted": "2026-07-01T00:00:00Z",
    "last_checked": "2026-09-05",
    "last_action": "resume",
    "registered_at": "2026-06-01T00:00:00Z",
}


def _catalog_with_cadence_state(merge, channel):
    """A catalog holding `channel` with cadence state already recorded, as a
    real one does after a backup run has stamped it."""
    data = merge(_fresh(), [channel])
    data["channels"][channel["id"]].update(CADENCE_STATE)
    return data


def test_fast_merge_preserves_cadence_state_on_an_existing_channel():
    data = _catalog_with_cadence_state(catalog_logic.merge_fast, CH1)
    data = catalog_logic.merge_fast(data, [CH1])
    assert {k: data["channels"]["C1"].get(k) for k in CADENCE_STATE} == CADENCE_STATE


def test_full_merge_preserves_cadence_state_on_an_existing_channel():
    data = _catalog_with_cadence_state(catalog_logic.merge_full, CH3)
    data = catalog_logic.merge_full(data, [CH3])
    assert {k: data["channels"]["C3"].get(k) for k in CADENCE_STATE} == CADENCE_STATE


def test_fast_merge_refreshes_description_while_preserving_cadence_state():
    data = _catalog_with_cadence_state(catalog_logic.merge_fast, CH1)
    renamed = {"id": "C1", "name": "general-v2", "topic": {"value": "T1-updated"}, "purpose": {"value": ""}}
    data = catalog_logic.merge_fast(data, [renamed])
    assert data["channels"]["C1"] == {
        "member": True, "name": "general-v2", "description": "T1-updated",
        "topic": "T1-updated", "purpose": None, "is_private": False,
        "is_archived": False, "creator": None, "created": None, **CADENCE_STATE,
    }


def test_fast_merge_promotes_a_full_tier_only_channel_to_member():
    data = _catalog_with_cadence_state(catalog_logic.merge_full, CH3)
    data = catalog_logic.merge_fast(data, [CH3])
    assert data["channels"]["C3"]["member"] is True
    assert {k: data["channels"]["C3"].get(k) for k in CADENCE_STATE} == CADENCE_STATE


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


def _seed_full_catalog(tmp_path, workspace, count):
    """Pre-populate a catalog with `count` not-member channels, standing in
    for an already-known-good full-tier cache."""
    channels = [
        {"id": f"C{i}", "name": f"chan{i}", "topic": {"value": ""}, "purpose": {"value": ""}}
        for i in range(count)
    ]
    data = catalog_logic.merge_full(_fresh(), channels)
    catalog_logic.save(tmp_path, workspace, data)


def test_refresh_full_retries_on_truncated_response_then_accepts_recovery(tmp_path, monkeypatch):
    _seed_full_catalog(tmp_path, "f3test", 6)
    responses = iter([[CH1], [CH1], [CH1, CH2, CH3]])  # 1, 1, then a plausible 3-of-6

    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", lambda member_only: next(responses))

    data = catalog_logic.refresh_full("f3test", cache_dir=tmp_path, ttl=0, now=2000.0)
    assert data["full_refreshed_at"] == 2000.0
    assert "C1" in data["channels"]


def test_refresh_full_does_not_stamp_when_still_truncated_after_retries(tmp_path, monkeypatch):
    _seed_full_catalog(tmp_path, "f3test", 60)

    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", lambda member_only: [CH1])

    data = catalog_logic.refresh_full("f3test", cache_dir=tmp_path, ttl=0, now=2000.0)
    # A silently-truncated response must not reset the TTL clock.
    assert data["full_refreshed_at"] == 0.0
    # But the (harmless, upsert-only) merge still happens.
    assert "C1" in data["channels"]
    assert len(data["channels"]) == 60


def test_refresh_full_accepts_first_try_when_not_truncated(tmp_path, monkeypatch):
    _seed_full_catalog(tmp_path, "f3test", 2)
    calls = []

    def fake_list_channels(member_only):
        calls.append(member_only)
        return [CH1, CH2, CH3]

    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", fake_list_channels)

    data = catalog_logic.refresh_full("f3test", cache_dir=tmp_path, ttl=0, now=2000.0)
    assert data["full_refreshed_at"] == 2000.0
    assert len(calls) == 1


def test_refresh_full_no_baseline_never_flags_truncation(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", lambda member_only: [CH1])

    data = catalog_logic.refresh_full("f3test", cache_dir=tmp_path, ttl=0, now=2000.0)
    assert data["full_refreshed_at"] == 2000.0


def test_refresh_fast_does_not_stamp_when_still_truncated_after_retries(tmp_path, monkeypatch):
    channels = [
        {"id": f"C{i}", "name": f"chan{i}", "topic": {"value": ""}, "purpose": {"value": ""}}
        for i in range(60)
    ]
    catalog_logic.save(tmp_path, "f3test", catalog_logic.merge_fast(_fresh(), channels))

    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", lambda member_only: [CH1])

    data = catalog_logic.refresh_fast("f3test", cache_dir=tmp_path, ttl=0, now=2000.0)
    assert data["fast_refreshed_at"] == 0.0


def test_is_truncated_helper():
    assert catalog_logic._is_truncated(5, 60) is True
    assert catalog_logic._is_truncated(59, 60) is False
    assert catalog_logic._is_truncated(0, 0) is False


def test_refresh_full_persists_full_scan_complete_true_when_not_truncated(tmp_path, monkeypatch):
    _seed_full_catalog(tmp_path, "f3test", 2)
    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", lambda member_only: [CH1, CH2, CH3])

    data = catalog_logic.refresh_full("f3test", cache_dir=tmp_path, ttl=0, now=2000.0)
    assert data["full_scan_complete"] is True


def test_refresh_full_persists_full_scan_complete_false_when_truncated(tmp_path, monkeypatch):
    _seed_full_catalog(tmp_path, "f3test", 60)
    monkeypatch.setattr(catalog_logic.slackdump, "select_workspace_or_die", lambda ws: None)
    monkeypatch.setattr(catalog_logic.slackdump, "list_channels", lambda member_only: [CH1])

    data = catalog_logic.refresh_full("f3test", cache_dir=tmp_path, ttl=0, now=2000.0)
    assert data["full_scan_complete"] is False


def test_load_absent_full_scan_complete_defaults_to_untrustworthy(tmp_path):
    data = catalog_logic.load(tmp_path, "f3test")
    assert data.get("full_scan_complete", False) is False


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
            "member": False, "name": "new-public", "description": "P3", "topic": None, "purpose": "P3",
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
