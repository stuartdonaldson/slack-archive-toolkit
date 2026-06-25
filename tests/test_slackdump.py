import json
import subprocess

from slackbackup import slackdump


def _fake_completed(stdout):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_list_channels_filters_out_dm_conversations(monkeypatch):
    # Confirmed empirically: `slackdump list channels`, even with
    # -member-only, also returns plain DM conversations - is_channel
    # false, blank name, id prefixed D instead of C.
    raw = [
        {"id": "C1", "name": "general", "is_channel": True},
        {"id": "D1", "name": "", "is_channel": False, "is_im": True},
    ]
    monkeypatch.setattr(slackdump, "_run", lambda args: _fake_completed(json.dumps(raw)))

    result = slackdump.list_channels(member_only=False)

    assert [c["id"] for c in result] == ["C1"]


def test_list_channels_filters_out_multi_person_dms_by_name(monkeypatch):
    # Sneakier than plain DMs: Slack reports is_channel:true for these too,
    # with a C-prefixed id - the name is the only reliable signal, and it
    # embeds every participant's real username (privacy leak, not just
    # noise, if one slips into channels.json).
    raw = [
        {"id": "C1", "name": "general", "is_channel": True},
        {"id": "C2", "name": "mpdm-alice--bob--carol-1", "is_channel": True, "is_mpim": True},
    ]
    monkeypatch.setattr(slackdump, "_run", lambda args: _fake_completed(json.dumps(raw)))

    result = slackdump.list_channels(member_only=False)

    assert [c["id"] for c in result] == ["C1"]


def test_list_channels_empty_output_returns_empty_list(monkeypatch):
    monkeypatch.setattr(slackdump, "_run", lambda args: _fake_completed(""))
    assert slackdump.list_channels(member_only=True) == []


def test_list_channels_failure_raises(monkeypatch):
    monkeypatch.setattr(
        slackdump, "_run",
        lambda args: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom"),
    )
    try:
        slackdump.list_channels(member_only=False)
        assert False, "expected SlackdumpError"
    except slackdump.SlackdumpError as exc:
        assert "boom" in str(exc)
