"""Tests for scripts/postprocess_dates.py - the newsletter render chain's
date post-processor (sat-sa8).

The chain is: digest -> LLM (emits every date in its own prose as
[YYYY-MM-DD]) -> this script (renders them to a localized form) -> posted.
Weekdays are computed here, never taken from the model's text, because an
LLM gets day-of-week arithmetic wrong (gh-5: "Wed Aug 6" for 2026-08-06,
a Thursday, with a 78-row date->weekday map sitting unused in the digest).

The flagging half matters as much as the rendering half: a single
unbracketed "Aug 6" would otherwise skip the mechanism silently and look
identical to a clean run (Andre's ask on gh-5).
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import postprocess_dates as pd


# --- rendering -------------------------------------------------------------

def test_bracketed_date_renders_default_format():
    result = pd.process("The party is [2026-08-06].")
    assert result.text == "The party is Thursday, August 6, 2026."


def test_weekday_is_computed_not_copied():
    # 2026-08-06 is a Thursday - the exact date the LLM called "Wed".
    assert date(2026, 8, 6).strftime("%A") == "Thursday"
    result = pd.process("Wed [2026-08-06]")
    assert "Thursday" in result.text
    # the model's own stray "Wed" is left alone in the text but reported
    assert any(f.kind == "unbracketed-date" for f in result.findings)


def test_day_is_not_zero_padded_by_default():
    assert pd.process("[2026-08-06]").text == "Thursday, August 6, 2026"


def test_custom_format_is_used():
    result = pd.process("[2026-08-06]", fmt="%Y/%m/%d")
    assert result.text == "2026/08/06"


def test_multiple_dates_all_rendered():
    result = pd.process("[2026-08-06] and [2026-12-25]")
    assert result.text == "Thursday, August 6, 2026 and Friday, December 25, 2026"
    assert result.findings == []


def test_clean_text_has_no_findings_and_is_unchanged():
    result = pd.process("No dates here at all.")
    assert result.text == "No dates here at all."
    assert result.findings == []


# --- invalid bracketed dates ----------------------------------------------

def test_invalid_bracketed_date_is_reported_and_left_alone():
    result = pd.process("Party on [2026-02-30].")
    assert "[2026-02-30]" in result.text
    kinds = [f.kind for f in result.findings]
    assert "invalid-date" in kinds


# --- the flagging half -----------------------------------------------------

def test_unbracketed_month_name_is_flagged():
    result = pd.process("The party is Aug 6.")
    assert [f.kind for f in result.findings] == ["unbracketed-date"]
    assert result.findings[0].line == 1


def test_unbracketed_full_month_name_is_flagged():
    result = pd.process("See you in August 2026.")
    assert any(f.kind == "unbracketed-date" for f in result.findings)


def test_numeric_date_is_flagged():
    result = pd.process("Meet on 8/6/2026.")
    assert any(f.kind == "unbracketed-date" for f in result.findings)


def test_bare_iso_date_outside_brackets_is_flagged():
    result = pd.process("Meet on 2026-08-06.")
    assert any(f.kind == "unbracketed-date" for f in result.findings)


def test_finding_line_numbers_are_reported():
    result = pd.process("clean line\nanother clean line\nAug 6 here")
    assert [f.line for f in result.findings] == [3]


def test_standalone_weekday_not_flagged_by_default():
    # "we meet Saturday" is a recurring schedule, not a date to normalize.
    assert pd.process("We meet Saturday at 0600.").findings == []


def test_standalone_weekday_flagged_under_strict_weekdays():
    result = pd.process("We meet Saturday at 0600.", strict_weekdays=True)
    assert any(f.kind == "unbracketed-date" for f in result.findings)


# --- quoted / verbatim exemptions -----------------------------------------

def test_double_quoted_source_text_is_exempt_from_flagging():
    result = pd.process('The message read "Aug 6 party at my place".')
    assert result.findings == []


def test_blockquote_line_is_exempt():
    result = pd.process("> Aug 6 party at my place")
    assert result.findings == []


def test_inline_code_span_is_exempt():
    result = pd.process("The raw text was `Aug 6 party`.")
    assert result.findings == []


def test_fenced_code_block_is_exempt():
    text = "before\n```\nAug 6 party\n```\nafter"
    assert pd.process(text).findings == []


def test_bracketed_date_inside_a_quote_is_not_rewritten():
    # quoted source wording stays verbatim, even if it looks like our token
    result = pd.process('He wrote "meet on [2026-08-06] sharp".')
    assert "[2026-08-06]" in result.text


# --- optional range sanity check ------------------------------------------

def test_date_outside_expected_range_is_flagged():
    result = pd.process(
        "[2025-08-06]", min_date=date(2026, 1, 1), max_date=date(2026, 12, 31)
    )
    assert any(f.kind == "out-of-range" for f in result.findings)


def test_date_inside_expected_range_is_not_flagged():
    result = pd.process(
        "[2026-08-06]", min_date=date(2026, 1, 1), max_date=date(2026, 12, 31)
    )
    assert result.findings == []


# --- exit status contract --------------------------------------------------

def test_exit_status_zero_when_no_findings():
    assert pd.exit_status(pd.process("nothing here")) == 0


def test_exit_status_nonzero_when_findings_exist():
    # fail-closed: a bypassed run must not look identical to a clean one
    assert pd.exit_status(pd.process("Aug 6")) != 0
