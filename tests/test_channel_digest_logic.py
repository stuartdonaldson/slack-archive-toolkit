from slackbackup import channel_digest_logic


def _catalog(channels: dict) -> dict:
    return {"channels": channels}


def test_filter_channels_matches_glob_pattern_and_sorts_by_name():
    catalog = _catalog({
        "C2": {"name": "shuttered-zzz", "is_archived": False, "member": True},
        "C1": {"name": "shuttered-aaa", "description": "old ao", "is_archived": True, "member": True},
        "C3": {"name": "helpdesk", "is_archived": False, "member": True},
    })

    result = channel_digest_logic.filter_channels(catalog, "shuttered-*")

    assert [c["name"] for c in result] == ["shuttered-aaa", "shuttered-zzz"]
    assert result[0] == {
        "id": "C1", "name": "shuttered-aaa", "description": "old ao",
        "is_archived": True, "member": True,
    }


def test_filter_channels_supports_arbitrary_glob_not_just_prefix():
    catalog = _catalog({
        "C1": {"name": "ao-redmond-ridge", "is_archived": False, "member": True},
        "C2": {"name": "ao-golden-mile", "is_archived": False, "member": True},
        "C3": {"name": "disc-golf", "is_archived": False, "member": True},
    })

    result = channel_digest_logic.filter_channels(catalog, "ao-*")
    assert [c["name"] for c in result] == ["ao-golden-mile", "ao-redmond-ridge"]


def test_filter_channels_no_match_returns_empty():
    catalog = _catalog({"C1": {"name": "helpdesk", "is_archived": False, "member": True}})
    assert channel_digest_logic.filter_channels(catalog, "shuttered-*") == []


def test_filter_channels_supports_comma_separated_selector_list():
    catalog = _catalog({
        "C1": {"name": "shuttered-foo", "is_archived": False, "member": True},
        "C2": {"name": "archived-bar", "is_archived": True, "member": True},
        "C3": {"name": "general", "is_archived": False, "member": True},
    })

    result = channel_digest_logic.filter_channels(catalog, "shuttered-*,archived-*")

    assert [c["name"] for c in result] == ["archived-bar", "shuttered-foo"]


def _channel(name, is_archived=False):
    return {"id": "C1", "name": name, "description": "", "is_archived": is_archived, "member": True}


def test_build_digest_manifest_counts_and_schema():
    results = [
        {"channel": _channel("shuttered-empty"), "messages": [], "files": []},
        {"channel": _channel("shuttered-has-canvas", is_archived=True), "messages": [], "files": [
            {"id": "F1", "name": "REGION_INFO", "title": "REGION INFO", "pretty_type": "Canvas",
             "creator": "U1", "creator_name": "Combine", "created_at": "2024-11-22T07:25:51Z",
             "permalink": "https://example.slack.com/docs/T1/F1", "content": "Established: July 4th, 2024"},
        ]},
    ]

    digest = channel_digest_logic.build_digest("f3pugetsound", "shuttered-*", results)

    assert digest["schema_version"] == "slack-channel-digest-v2"
    assert digest["workspace"] == "f3pugetsound"
    assert digest["pattern"] == "shuttered-*"
    assert digest["first_generated_at"] == digest["last_generated_at"]
    assert digest["manifest"]["channels_total"] == 2
    assert digest["manifest"]["channels_with_content"] == 1
    assert digest["manifest"]["errors_this_run"] == 0

    by_name = {c["name"]: c for c in digest["channels"]}
    assert by_name["shuttered-empty"]["messages"] == []
    assert by_name["shuttered-empty"]["files"] == []
    assert by_name["shuttered-has-canvas"]["slack_archived"] is True
    assert by_name["shuttered-has-canvas"]["error"] is None
    assert by_name["shuttered-has-canvas"]["first_seen_at"] == digest["last_generated_at"]
    canvas = by_name["shuttered-has-canvas"]["files"][0]
    assert canvas["title"] == "REGION INFO"
    assert canvas["creator_name"] == "Combine"
    assert canvas["first_seen_at"] == digest["last_generated_at"]
    assert canvas["content_last_changed_at"] == digest["last_generated_at"]


def test_build_digest_reports_and_sanitizes_errors():
    raw_error = (
        "slackdump archive failed: \x1b[90m2026-07-02 16:12:00\x1b[0m \x1b[1;32mINFO\x1b[0m got rate limited\n"
        "                      ├─ retry_after: 30s\n"
        "                      └─ \x1b[31;1merror:\x1b[0m slack rate limit exceeded, retry after 30s"
    )
    results = [
        {"channel": _channel("shuttered-broken"), "messages": [], "files": [], "error": raw_error},
    ]

    digest = channel_digest_logic.build_digest("f3pugetsound", "shuttered-*", results)

    assert digest["manifest"]["errors_this_run"] == 1
    error = digest["channels"][0]["error"]
    assert "\x1b" not in error
    assert "\n" not in error
    assert "slack rate limit exceeded" in error


def _file(id_, content="text", **overrides):
    base = {
        "id": id_, "name": id_, "title": id_, "pretty_type": "Canvas",
        "creator": "U1", "creator_name": "Combine", "created_at": "2024-11-22T07:25:51Z",
        "permalink": None, "content": content,
    }
    base.update(overrides)
    return base


def _build_at(monkeypatch, timestamp, workspace, pattern, results):
    monkeypatch.setattr(channel_digest_logic, "_now", lambda: timestamp)
    return channel_digest_logic.build_digest(workspace, pattern, results)


def test_merge_digests_preserves_first_seen_and_updates_last_seen(monkeypatch):
    old = _build_at(
        monkeypatch, "2026-01-01T00:00:00Z", "f3pugetsound", "shuttered-*",
        [{"channel": _channel("shuttered-a"), "messages": [], "files": [_file("F1")]}],
    )
    new = _build_at(
        monkeypatch, "2026-02-01T00:00:00Z", "f3pugetsound", "shuttered-*",
        [{"channel": _channel("shuttered-a"), "messages": [], "files": [_file("F1")]}],
    )

    merged = channel_digest_logic.merge_digests(old, new)

    assert merged["schema_version"] == "slack-channel-digest-v2"
    assert merged["first_generated_at"] == "2026-01-01T00:00:00Z"
    assert merged["last_generated_at"] == "2026-02-01T00:00:00Z"
    chan = merged["channels"][0]
    assert chan["first_seen_at"] == "2026-01-01T00:00:00Z"
    assert chan["last_seen_at"] == "2026-02-01T00:00:00Z"
    file_ = chan["files"][0]
    assert file_["first_seen_at"] == "2026-01-01T00:00:00Z"
    assert file_["last_seen_at"] == "2026-02-01T00:00:00Z"
    # content unchanged between runs - content_last_changed_at stays at first sighting
    assert file_["content_last_changed_at"] == "2026-01-01T00:00:00Z"


def test_merge_digests_detects_content_change(monkeypatch):
    old = _build_at(
        monkeypatch, "2026-01-01T00:00:00Z", "f3pugetsound", "shuttered-*",
        [{"channel": _channel("shuttered-a"), "messages": [], "files": [_file("F1", content="v1")]}],
    )
    new = _build_at(
        monkeypatch, "2026-02-01T00:00:00Z", "f3pugetsound", "shuttered-*",
        [{"channel": _channel("shuttered-a"), "messages": [], "files": [_file("F1", content="v2")]}],
    )

    merged = channel_digest_logic.merge_digests(old, new)

    file_ = merged["channels"][0]["files"][0]
    assert file_["content"] == "v2"
    assert file_["content_last_changed_at"] == "2026-02-01T00:00:00Z"


def test_merge_digests_keeps_channel_not_rescanned_this_run(monkeypatch):
    old = _build_at(
        monkeypatch, "2026-01-01T00:00:00Z", "f3pugetsound", "shuttered-*",
        [{"channel": _channel("shuttered-a"), "messages": [], "files": [_file("F1")]}],
    )
    new = _build_at(monkeypatch, "2026-02-01T00:00:00Z", "f3pugetsound", "other-*", [])

    merged = channel_digest_logic.merge_digests(old, new)

    assert merged["manifest"]["channels_total"] == 1
    assert merged["manifest"]["channels_scanned_this_run"] == 0
    assert merged["channels"][0]["name"] == "shuttered-a"
    assert merged["channels"][0]["last_seen_at"] == "2026-01-01T00:00:00Z"


def test_merge_digests_adds_newly_appeared_channel(monkeypatch):
    old = _build_at(monkeypatch, "2026-01-01T00:00:00Z", "f3pugetsound", "shuttered-*", [])
    new = _build_at(
        monkeypatch, "2026-02-01T00:00:00Z", "f3pugetsound", "shuttered-*",
        [{"channel": _channel("shuttered-new"), "messages": [], "files": [_file("F2")]}],
    )

    merged = channel_digest_logic.merge_digests(old, new)

    assert merged["manifest"]["channels_total"] == 1
    names = [c["name"] for c in merged["channels"]]
    assert "shuttered-new" in names


def test_merge_digests_rejects_mismatched_schema_version():
    old = {"schema_version": "slack-channel-digest-v1", "channels": []}
    new = channel_digest_logic.build_digest("f3pugetsound", "shuttered-*", [])

    try:
        channel_digest_logic.merge_digests(old, new)
        assert False, "expected ValueError"
    except ValueError:
        pass
