"""Tests for prune_logic (tiered retention of ~/slack-exports snapshots) and
the `export prune` CLI handler. Retention rules: sat-v4t AC rev 2.

today is pinned to 2026-11-20 unless a test says otherwise:
  daily  = as_of <= 7 days old   (>= 2026-11-13)
  weekly = as_of <= 35 days old  (>= 2026-10-16), latest per ISO week
  monthly = every as_of month, whatever its age
A file survives if ANY tier keeps it.
"""
import argparse
from datetime import date
from pathlib import Path

from slackbackup import export, prune_logic

TODAY = date(2026, 11, 20)


def _digest(tmp_path, as_of, month="2026-05", prefix="f3-dev", content="{}"):
    p = tmp_path / f"{prefix}-digest-{as_of}-{month}.json"
    p.write_text(content)
    return p


def _plan(tmp_path, **kw):
    kw.setdefault("today", TODAY)
    return prune_logic.plan_prune(sorted(tmp_path.iterdir()), **kw)


def _names(paths):
    return sorted(p.name for p in paths)


# ---- parse_name -----------------------------------------------------------

def test_parse_old_digest_scheme():
    p = prune_logic.parse_name("f3-dev-digest-2026-08-17-2026-05.json")
    assert (p.prefix, p.kind, p.as_of, p.report_month) == ("f3-dev", "digest", date(2026, 8, 17), "2026-05")


def test_parse_new_digest_scheme():
    p = prune_logic.parse_name("f3-pugetsound-digest-2026-11.2026-11-05.json")
    assert (p.prefix, p.kind, p.as_of, p.report_month) == ("f3-pugetsound", "digest", date(2026, 11, 5), "2026-11")


def test_parse_dm_digest_and_users_have_no_report_month():
    d = prune_logic.parse_name("f3-dm-digest-2026-11-01.json")
    u = prune_logic.parse_name("f3-dev-users-2026-08-19.json")
    assert (d.prefix, d.kind, d.report_month) == ("f3-dm", "digest", None)
    assert (u.prefix, u.kind, u.report_month) == ("f3-dev", "users", None)


def test_parse_unrecognised_names_return_none():
    for name in (
        "f3-pugetsound-users-{month}.json",
        "f3-dm-digest-f3nation-2026-09-05.json",
        "llm-context",
        "notes.txt",
    ):
        assert prune_logic.parse_name(name) is None


# ---- tiers ----------------------------------------------------------------

def test_daily_tier_keeps_every_snapshot_in_last_7_days(tmp_path):
    for d in ("2026-11-13", "2026-11-14", "2026-11-15", "2026-11-19"):
        _digest(tmp_path, d)
    plan = _plan(tmp_path)
    assert plan.delete == []


def test_weekly_tier_keeps_latest_per_iso_week(tmp_path):
    # Mon 2026-10-19 week: 10-20,10-22 ; Mon 10-26 week: 10-27,10-28 ; all 15-32 days old.
    for d in ("2026-10-20", "2026-10-22", "2026-10-27", "2026-10-28"):
        _digest(tmp_path, d)
    plan = _plan(tmp_path)
    kept = {p.name for p in plan.keep}
    assert "f3-dev-digest-2026-10-22-2026-05.json" in kept
    assert "f3-dev-digest-2026-10-28-2026-05.json" in kept
    assert "f3-dev-digest-2026-10-20-2026-05.json" in kept  # Oct monthly keeper (earliest in Oct)
    assert _names(plan.delete) == ["f3-dev-digest-2026-10-27-2026-05.json"]


def test_monthly_keeper_survives_weekly_pruning(tmp_path):
    # Nov 2,3,5 share one ISO week; weekly keeper is 11-05 but the Nov
    # monthly keeper (earliest, 11-02) must also survive; only 11-03 goes.
    # Oct 30/31 share the previous ISO week: weekly=10-31, monthly(Oct)=10-30.
    for d in ("2026-10-30", "2026-10-31", "2026-11-02", "2026-11-03", "2026-11-05"):
        _digest(tmp_path, d)
    plan = _plan(tmp_path)
    assert _names(plan.delete) == ["f3-dev-digest-2026-11-03-2026-05.json"]


def test_old_months_keep_only_earliest_snapshot_of_each_as_of_month(tmp_path):
    for d in ("2026-08-17", "2026-08-18", "2026-08-19", "2026-09-03", "2026-09-04"):
        _digest(tmp_path, d)
    plan = _plan(tmp_path)
    assert _names(plan.delete) == [
        "f3-dev-digest-2026-08-18-2026-05.json",
        "f3-dev-digest-2026-08-19-2026-05.json",
        "f3-dev-digest-2026-09-04-2026-05.json",
    ]
    assert plan.partial == []


def test_as_of_month_equal_to_report_month_is_partial_keeps_latest(tmp_path):
    _digest(tmp_path, "2026-08-10", month="2026-08")
    _digest(tmp_path, "2026-08-20", month="2026-08")
    plan = _plan(tmp_path)
    assert _names(plan.delete) == ["f3-dev-digest-2026-08-10-2026-08.json"]
    assert len(plan.partial) == 1 and "2026-08" in plan.partial[0]


def test_groups_are_independent_by_prefix_kind_and_report_month(tmp_path):
    # Same as_of date, different report months / prefixes / kinds: none supersede each other.
    for m in ("2026-05", "2026-06", "2026-07"):
        _digest(tmp_path, "2026-08-17", month=m)
    _digest(tmp_path, "2026-08-17", prefix="f3-plateau")
    (tmp_path / "f3-dev-users-2026-08-17.json").write_text("{}")
    assert _plan(tmp_path).delete == []


def test_dm_digest_without_report_month_uses_earliest_per_as_of_month(tmp_path):
    for d in ("2026-09-05", "2026-09-09", "2026-09-11"):
        (tmp_path / f"f3-dm-digest-{d}.json").write_text("{}")
    assert _names(_plan(tmp_path).delete) == ["f3-dm-digest-2026-09-09.json", "f3-dm-digest-2026-09-11.json"]


# ---- idempotence / safety ---------------------------------------------------

def test_apply_then_replan_is_noop(tmp_path):
    for d in ("2026-08-17", "2026-08-18", "2026-10-30", "2026-10-31", "2026-11-02", "2026-11-03", "2026-11-05"):
        _digest(tmp_path, d)
    plan = _plan(tmp_path)
    assert plan.delete
    prune_logic.apply_plan(plan)
    assert _plan(tmp_path).delete == []


def test_idempotent_across_month_rollover(tmp_path):
    for d in ("2026-10-02", "2026-10-03", "2026-10-30", "2026-11-01"):
        _digest(tmp_path, d)
    prune_logic.apply_plan(_plan(tmp_path, today=date(2026, 11, 20)))
    first = _names(tmp_path.iterdir())
    prune_logic.apply_plan(_plan(tmp_path, today=date(2026, 12, 2)))
    prune_logic.apply_plan(_plan(tmp_path, today=date(2026, 12, 2)))
    # Oct keeper (10-02) and Nov keeper (11-01) survive the rollover.
    assert "f3-dev-digest-2026-10-02-2026-05.json" in _names(tmp_path.iterdir())
    assert "f3-dev-digest-2026-11-01-2026-05.json" in _names(tmp_path.iterdir())
    assert set(_names(tmp_path.iterdir())) <= set(first)


def test_zero_byte_keeper_candidate_is_skipped_and_never_deleted(tmp_path):
    bad = _digest(tmp_path, "2026-08-17", content="")
    _digest(tmp_path, "2026-08-18")
    _digest(tmp_path, "2026-08-19")
    plan = _plan(tmp_path)
    assert bad not in plan.delete
    assert bad in plan.invalid
    assert "f3-dev-digest-2026-08-18-2026-05.json" in {p.name for p in plan.keep}
    assert _names(plan.delete) == ["f3-dev-digest-2026-08-19-2026-05.json"]


def test_non_object_json_is_invalid(tmp_path):
    _digest(tmp_path, "2026-08-17", content="[1, 2]")
    _digest(tmp_path, "2026-08-18")
    plan = _plan(tmp_path)
    assert _names(plan.invalid) == ["f3-dev-digest-2026-08-17-2026-05.json"]


def test_month_with_no_valid_snapshot_is_a_gap_and_nothing_in_it_is_deleted(tmp_path):
    _digest(tmp_path, "2026-08-17", content="")
    _digest(tmp_path, "2026-08-18", content="{bad")
    plan = _plan(tmp_path)
    assert plan.delete == []
    assert len(plan.gaps) == 1 and "2026-08" in plan.gaps[0]


def test_keeper_deleted_by_hand_falls_back_to_next_best(tmp_path):
    for d in ("2026-08-17", "2026-08-18", "2026-08-19"):
        _digest(tmp_path, d)
    (tmp_path / "f3-dev-digest-2026-08-17-2026-05.json").unlink()
    plan = _plan(tmp_path)
    assert _names(plan.delete) == ["f3-dev-digest-2026-08-19-2026-05.json"]


# ---- scope ------------------------------------------------------------------

def test_files_sidecars_and_unrecognised_names_untouched_by_default(tmp_path):
    for d in ("2026-08-17", "2026-08-18"):
        (tmp_path / f"f3-dev-files-{d}.json").write_text("{}")
    (tmp_path / "f3-pugetsound-users-{month}.json").write_text("{}")
    (tmp_path / "f3-dm-digest-f3nation-2026-09-05.json").write_text("{}")
    (tmp_path / "llm-context").mkdir()
    plan = _plan(tmp_path)
    assert plan.delete == []
    assert {p.name for p in plan.skipped} >= {
        "f3-dev-files-2026-08-17.json", "f3-dev-files-2026-08-18.json",
        "f3-pugetsound-users-{month}.json", "f3-dm-digest-f3nation-2026-09-05.json", "llm-context",
    }


def test_include_files_prunes_sidecars_but_always_keeps_latest(tmp_path):
    for d in ("2026-08-17", "2026-08-18", "2026-08-19"):
        (tmp_path / f"f3-dev-files-{d}.json").write_text("{}")
    plan = _plan(tmp_path, include_files=True)
    kept = {p.name for p in plan.keep}
    assert "f3-dev-files-2026-08-17.json" in kept   # monthly keeper
    assert "f3-dev-files-2026-08-19.json" in kept   # cumulative sidecar: latest always survives
    assert _names(plan.delete) == ["f3-dev-files-2026-08-18.json"]


# ---- CLI handler --------------------------------------------------------------

def _args(tmp_path, **kw):
    d = dict(exports_dir=str(tmp_path), today="2026-11-20", apply=False, include_files=False)
    d.update(kw)
    return argparse.Namespace(**d)


def test_cli_dry_run_is_default_and_deletes_nothing(tmp_path, capsys):
    for d in ("2026-08-17", "2026-08-18"):
        _digest(tmp_path, d)
    assert export._prune(_args(tmp_path)) == 0
    assert len(list(tmp_path.iterdir())) == 2
    assert "dry run" in capsys.readouterr().err.lower()


def test_cli_apply_deletes_and_exits_zero(tmp_path):
    for d in ("2026-08-17", "2026-08-18"):
        _digest(tmp_path, d)
    assert export._prune(_args(tmp_path, apply=True)) == 0
    assert _names(tmp_path.iterdir()) == ["f3-dev-digest-2026-08-17-2026-05.json"]


def test_cli_exits_nonzero_on_monthly_gap_and_does_not_delete(tmp_path):
    _digest(tmp_path, "2026-08-17", content="")
    _digest(tmp_path, "2026-08-18", content="{bad")
    assert export._prune(_args(tmp_path, apply=True)) == 1
    assert len(list(tmp_path.iterdir())) == 2


def test_cli_registered_under_export_group():
    from slackbackup import cli
    args = cli.build_parser().parse_args(["export", "prune", "--apply", "--today", "2026-11-20"])
    assert args.handler is export._prune and args.apply is True
