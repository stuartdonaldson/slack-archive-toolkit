"""Tests for src/slackbackup/export.py's CLI-layer functions (_digest,
_run_job, _resolve_handler) - the --jobs batch runner, per-job days/handler
resolution, and clean-failure handling. export_logic.py's pure functions
(build_digest, build_user_profiles, load_job, ...) are tested in
tests/test_export_digest_logic.py; this file only covers the CLI plumbing
around them, so their real implementations are monkeypatched out.
"""
import argparse
import json
from pathlib import Path

import pytest

from slackbackup import export, export_logic


_SAMPLE_FILES_OUT_ENTRY = {
    "workspace": "f3pugetsound", "channel": "helpdesk", "channel_id": "C1", "id": "F1",
    "content": "hello", "content_sha256": "abc123",
}


def _write_job(path: Path, **fields) -> Path:
    job = {"type": "digest", "out": str(path.parent / (path.stem + "-out-{as_of}.json"))}
    job.update(fields)
    path.write_text(json.dumps(job))
    return path


def _base_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        jobs=None,
        archive_root=None,
        channels_file="./channels.json",
        workspace_glob="f3*",  # args.workspace_glob is the dest for the --workspace CLI flag
        days=180,
        as_of="2026-07-01",
        out=None,
        leadership_handler=None,
        split_by_month=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _stub_profiles(monkeypatch, raise_for_glob=None):
    """Monkeypatches export_logic.build_user_profiles and build_digest with
    fakes that need no real archive on disk. If raise_for_glob is given,
    the fake build_user_profiles raises for a job whose workspace_glob
    matches it (used to simulate one job's processing blowing up)."""

    def fake_build_user_profiles(channels_file, archive_root, workspace_glob, convert_fn, handler=None):
        if raise_for_glob is not None and workspace_glob == raise_for_glob:
            raise RuntimeError(f"simulated failure for {workspace_glob}")
        return {"schema_version": "slack-user-profiles-v1", "workspaces": []}

    def fake_build_digest(
        channels_file, archive_root, workspace_glob, days, as_of, convert_fn,
        catalog_cache_dir=None, handler=None, profiles_doc=None, files_out_sink=None,
    ):
        fake_build_digest.calls.append(days)
        if files_out_sink is not None:
            files_out_sink.append(_SAMPLE_FILES_OUT_ENTRY)
        return {"channels": [], "messages": []}

    def fake_build_monthly_digests(
        channels_file, archive_root, workspace_glob, days, as_of, convert_fn,
        catalog_cache_dir=None, handler=None, profiles_doc=None, files_out_sink=None,
    ):
        fake_build_monthly_digests.calls.append(days)
        if files_out_sink is not None:
            files_out_sink.append(_SAMPLE_FILES_OUT_ENTRY)
        return {
            "2026-04": {"channels": [], "messages": [], "export_scope": {"month": "2026-04"}},
            "2026-05": {"channels": [], "messages": [], "export_scope": {"month": "2026-05"}},
        }

    fake_build_digest.calls = []
    fake_build_monthly_digests.calls = []

    monkeypatch.setattr(export.export_logic, "build_user_profiles", fake_build_user_profiles)
    monkeypatch.setattr(export.export_logic, "build_digest", fake_build_digest)
    monkeypatch.setattr(export.export_logic, "build_monthly_digests", fake_build_monthly_digests)
    return fake_build_digest, fake_build_monthly_digests


# --- Change 1: --days default of 180, and --jobs per-job fallback ---


def test_run_job_falls_back_to_args_days_when_job_omits_days(tmp_path, monkeypatch):
    fake_build_digest, _ = _stub_profiles(monkeypatch)
    job_file = _write_job(tmp_path / "job.json", archive_root=str(tmp_path), workspaces=["f3ok"])
    job = export_logic.load_job(job_file)
    args = _base_args(days=180)

    export._run_job(str(job_file), job, args, "2026-07-01")

    assert fake_build_digest.calls == [180]


def test_run_job_uses_jobs_own_days_when_present(tmp_path, monkeypatch):
    fake_build_digest, _ = _stub_profiles(monkeypatch)
    job_file = _write_job(tmp_path / "job.json", archive_root=str(tmp_path), workspaces=["f3ok"], days=30)
    job = export_logic.load_job(job_file)
    args = _base_args(days=180)

    export._run_job(str(job_file), job, args, "2026-07-01")

    assert fake_build_digest.calls == [30]


# --- Bug 2a: one bad job must not abort the whole --jobs batch ---


def test_digest_jobs_batch_continues_after_one_job_fails(tmp_path, monkeypatch):
    fake_build_digest, _ = _stub_profiles(monkeypatch, raise_for_glob="f3fail")

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    _write_job(jobs_dir / "a-fail.json", archive_root=str(tmp_path / "archive1"), workspaces=["f3fail"])
    _write_job(jobs_dir / "b-ok.json", archive_root=str(tmp_path / "archive2"), workspaces=["f3ok"])

    args = _base_args(jobs=str(jobs_dir / "*.json"))

    exit_code = export._digest(args)

    assert exit_code != 0
    # The second (good) job's processing still happened.
    assert fake_build_digest.calls == [180]
    out_file = jobs_dir / "b-ok-out-2026-07-01.json"
    assert out_file.exists()
    # The failing job's own output must not have been written.
    assert not (jobs_dir / "a-fail-out-2026-07-01.json").exists()


# --- Bug 2b: a "workspaces" job field of the wrong type is rejected cleanly ---


def test_digest_jobs_batch_skips_job_with_non_list_workspaces(tmp_path, monkeypatch):
    fake_build_digest, _ = _stub_profiles(monkeypatch)

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    _write_job(jobs_dir / "bad.json", archive_root=str(tmp_path), workspaces="f3pugetsound")

    args = _base_args(jobs=str(jobs_dir / "*.json"))

    exit_code = export._digest(args)

    assert exit_code != 0
    assert fake_build_digest.calls == []


# --- Bug 2c: an unknown --leadership-handler must not crash on the direct path ---


def test_digest_direct_path_reports_unknown_handler_cleanly(tmp_path, capsys):
    args = _base_args(archive_root=str(tmp_path), leadership_handler="bogus")

    exit_code = export._digest(args)

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "bogus" in captured.err


# --- SlackBackup-1sx: digest file is written compact, not pretty-printed ---


def test_run_digest_writes_compact_json(tmp_path, monkeypatch):
    """indent=2 whitespace was ~26% of a real digest file; the digest must be
    written compact (and unescaped UTF-8) with content otherwise unchanged."""
    _stub_profiles(monkeypatch)
    out_path = tmp_path / "digest.json"

    export._run_digest(Path("channels.json"), tmp_path, "f3*", 180, "2026-07-01", out_path, None)

    text = out_path.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))


# --- Change 2: --workspace has no default; required unless --jobs is given ---


def test_digest_direct_path_requires_workspace_when_no_jobs(tmp_path, capsys):
    args = _base_args(archive_root=str(tmp_path), workspace_glob=None)

    exit_code = export._digest(args)

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "--workspace is required unless --jobs is given" in captured.err


# --- --split-by-month: one digest document per calendar month ---


def test_digest_split_by_month_rejects_out_without_month_placeholder(tmp_path, monkeypatch, capsys):
    _stub_profiles(monkeypatch)
    args = _base_args(
        archive_root=str(tmp_path), out=str(tmp_path / "digest.json"), split_by_month=True,
    )

    exit_code = export._digest(args)

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "{month}" in captured.err


def test_digest_split_by_month_writes_one_file_per_month(tmp_path, monkeypatch):
    _, fake_build_monthly_digests = _stub_profiles(monkeypatch)
    out_template = str(tmp_path / "digest-{month}.json")
    args = _base_args(archive_root=str(tmp_path), out=out_template, split_by_month=True)

    exit_code = export._digest(args)

    assert exit_code == 0
    assert fake_build_monthly_digests.calls == [180]
    assert (tmp_path / "digest-2026-04.json").exists()
    assert (tmp_path / "digest-2026-05.json").exists()


def test_digest_split_by_month_default_out_includes_month_placeholder(tmp_path, monkeypatch):
    _, fake_build_monthly_digests = _stub_profiles(monkeypatch)
    args = _base_args(archive_root=str(tmp_path), split_by_month=True)

    exit_code = export._digest(args)

    assert exit_code == 0
    assert fake_build_monthly_digests.calls == [180]


def test_run_job_split_by_month_uses_build_monthly_digests(tmp_path, monkeypatch):
    fake_build_digest, fake_build_monthly_digests = _stub_profiles(monkeypatch)
    job_file = _write_job(
        tmp_path / "job.json", archive_root=str(tmp_path), workspaces=["f3ok"], split_by_month=True,
        out=str(tmp_path / "job-out-{as_of}-{month}.json"),
    )
    job = export_logic.load_job(job_file)
    args = _base_args(days=180)

    export._run_job(str(job_file), job, args, "2026-07-01")

    assert fake_build_monthly_digests.calls == [180]
    assert fake_build_digest.calls == []
    assert (tmp_path / "job-out-2026-07-01-2026-04.json").exists()
    assert (tmp_path / "job-out-2026-07-01-2026-05.json").exists()


def test_resolve_job_out_substitutes_month_placeholder():
    resolved = export_logic.resolve_job_out("~/exports/digest-{as_of}-{month}.json", "2026-07-01", month="2026-04")

    assert resolved.name == "digest-2026-07-01-2026-04.json"


def test_run_job_writes_files_out_sidecar_when_job_sets_files_out(tmp_path, monkeypatch):
    _stub_profiles(monkeypatch)
    job_file = _write_job(
        tmp_path / "job.json", archive_root=str(tmp_path), workspaces=["f3ok"],
        files_out=str(tmp_path / "job-files-{as_of}.json"),
    )
    job = export_logic.load_job(job_file)
    args = _base_args()

    export._run_job(str(job_file), job, args, "2026-07-01")

    files_out_path = tmp_path / "job-files-2026-07-01.json"
    assert files_out_path.exists()
    doc = json.loads(files_out_path.read_text())
    assert doc["schema_version"] == "slack-llm-files-v1"
    assert doc["files"][0]["id"] == "F1"
    assert doc["files"][0]["first_seen_at"] == doc["generated_at"]


def test_run_job_omits_files_out_write_when_job_has_no_files_out_field(tmp_path, monkeypatch):
    _stub_profiles(monkeypatch)
    job_file = _write_job(tmp_path / "job.json", archive_root=str(tmp_path), workspaces=["f3ok"])
    job = export_logic.load_job(job_file)
    args = _base_args()

    export._run_job(str(job_file), job, args, "2026-07-01")

    assert list(tmp_path.glob("job-files-*.json")) == []


def test_run_job_files_out_carries_forward_first_seen_at_across_runs(tmp_path, monkeypatch):
    _stub_profiles(monkeypatch)
    job_file = _write_job(
        tmp_path / "job.json", archive_root=str(tmp_path), workspaces=["f3ok"],
        files_out=str(tmp_path / "job-files-{as_of}.json"),
    )
    job = export_logic.load_job(job_file)
    args = _base_args()

    export._run_job(str(job_file), job, args, "2026-07-01")
    first_seen_at = json.loads((tmp_path / "job-files-2026-07-01.json").read_text())["files"][0]["first_seen_at"]

    export._run_job(str(job_file), job, args, "2026-07-02")
    second_run = json.loads((tmp_path / "job-files-2026-07-02.json").read_text())["files"][0]

    assert second_run["first_seen_at"] == first_seen_at
    assert second_run["content_changed_at"] is None
