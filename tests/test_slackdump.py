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
    monkeypatch.setattr(slackdump, "_run", lambda args, timeout=None: _fake_completed(json.dumps(raw)))

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
    monkeypatch.setattr(slackdump, "_run", lambda args, timeout=None: _fake_completed(json.dumps(raw)))

    result = slackdump.list_channels(member_only=False)

    assert [c["id"] for c in result] == ["C1"]


def test_list_channels_empty_output_returns_empty_list(monkeypatch):
    monkeypatch.setattr(slackdump, "_run", lambda args, timeout=None: _fake_completed(""))
    assert slackdump.list_channels(member_only=True) == []


def test_list_channels_failure_raises(monkeypatch):
    monkeypatch.setattr(
        slackdump, "_run",
        lambda args, timeout=None: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom"),
    )
    try:
        slackdump.list_channels(member_only=False)
        assert False, "expected SlackdumpError"
    except slackdump.SlackdumpError as exc:
        assert "boom" in str(exc)


def test_dedupe_passes_message_key_mode_and_execute(monkeypatch, tmp_path):
    captured = {}

    def _run(args, timeout=None):
        captured["args"] = args
        return _fake_completed("Removed messages: 0\n")

    monkeypatch.setattr(slackdump, "_run", _run)

    slackdump.dedupe(tmp_path / "f3test" / "general")

    assert captured["args"] == [
        "tools", "dedupe", "-mode", "message-key", "-execute", str(tmp_path / "f3test" / "general"),
    ]


def test_dedupe_parses_removed_message_count(monkeypatch, tmp_path):
    # Real `tools dedupe -execute` stdout (2026-08-08, sat-9hq): a plain
    # "Duplicate ..." summary, an ANSI-colored INFO log line, then a plain
    # "Removed ..." summary - only the last is parsed.
    stdout = (
        "Duplicate messages: 158\n"
        "Duplicate channels: 12\n"
        "\x1b[90m2026-08-08 07:18:23\x1b[0m \x1b[1;32mINFO\x1b[0m dedupe execute\n"
        "Removed messages: 158\n"
        "Removed channels: 12\n"
    )
    monkeypatch.setattr(slackdump, "_run", lambda args, timeout=None: _fake_completed(stdout))

    assert slackdump.dedupe(tmp_path) == 158


def test_dedupe_no_removed_line_returns_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(slackdump, "_run", lambda args, timeout=None: _fake_completed("Duplicate messages: 0\n"))
    assert slackdump.dedupe(tmp_path) == 0


def test_dedupe_failure_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(
        slackdump, "_run",
        lambda args, timeout=None: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom"),
    )
    try:
        slackdump.dedupe(tmp_path)
        assert False, "expected SlackdumpError"
    except slackdump.SlackdumpError as exc:
        assert "boom" in str(exc)


# --- subprocess timeout (sat-hh0) ---------------------------------------
# Observed 2026-08-09: `slackdump tools dedupe -mode message-key -execute`
# pegged at 100% CPU for 24+ minutes on a 966-message channel (weasel-shakers,
# similar scale, deduped in 185s for comparison) - a genuine algorithmic hang
# in slackdump itself, not I/O-blocked. Nothing bounded it. archive/resume/
# dedupe now pass an explicit timeout to _run(); subprocess.run's own timeout
# handling kills the child and raises TimeoutExpired, which _run converts to
# the same SlackdumpError callers already handle (backup_logic's per-channel
# catch, _dedupe_quietly) - no caller-side change needed.

def test_run_timeout_raises_slackdump_error(monkeypatch):
    def _fake_run(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    try:
        slackdump._run(["tools", "dedupe"], timeout=5)
        assert False, "expected SlackdumpError"
    except slackdump.SlackdumpError as exc:
        assert "timed out" in str(exc)
        assert "5" in str(exc)


def test_run_without_timeout_is_unaffected(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, capture_output, text, timeout: _fake_completed("ok"))
    assert slackdump._run(["workspace", "list"]).stdout == "ok"


def test_archive_passes_archive_timeout(monkeypatch, tmp_path):
    captured = {}

    def _run(args, timeout=None):
        captured["timeout"] = timeout
        return _fake_completed("")

    monkeypatch.setattr(slackdump, "_run", _run)
    slackdump.archive("C1", tmp_path)
    assert captured["timeout"] == slackdump.ARCHIVE_TIMEOUT_SECONDS


def test_resume_passes_resume_timeout(monkeypatch, tmp_path):
    captured = {}

    def _run(args, timeout=None):
        captured["timeout"] = timeout
        return _fake_completed("")

    monkeypatch.setattr(slackdump, "_run", _run)
    slackdump.resume(tmp_path)
    assert captured["timeout"] == slackdump.RESUME_TIMEOUT_SECONDS


def test_dedupe_passes_dedupe_timeout(monkeypatch, tmp_path):
    captured = {}

    def _run(args, timeout=None):
        captured["timeout"] = timeout
        return _fake_completed("Removed messages: 0\n")

    monkeypatch.setattr(slackdump, "_run", _run)
    slackdump.dedupe(tmp_path)
    assert captured["timeout"] == slackdump.DEDUPE_TIMEOUT_SECONDS


def test_archive_timeout_propagates_as_slackdump_error(monkeypatch, tmp_path):
    def _fake_run(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    try:
        slackdump.archive("C1", tmp_path)
        assert False, "expected SlackdumpError"
    except slackdump.SlackdumpError as exc:
        assert "timed out" in str(exc)
