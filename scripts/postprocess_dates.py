#!/usr/bin/env python3
"""Render bracketed ISO dates in LLM newsletter output, and flag any date
text that bypassed the bracket contract (sat-sa8).

Why this exists
---------------
An LLM gets day-of-week arithmetic wrong. On gh-5 a render printed
"Wed Aug 6" for 2026-08-06 (a Thursday) while the digest it read from
carried a 78-row date->weekday map that went entirely unused. Supplying
reference data does not make a model consult it.

So the newsletter render chain splits the work by what each half is good
at: the LLM reads "Aug 6" in a message posted 2026-07-06 and resolves it
to [2026-08-06] (interpretation, which it does well); this script turns
that into "Thursday, August 6, 2026" (arithmetic, which it does not).
Pair it with prompts/newsletter-postprocessed.md, which states the
output contract this script assumes.

Only the automated newsletter chain uses this. The interactive query path
(a user asking a ChatGPT Project for a report) has no post-processing
stage, so it gets a different rule for the same root cause - state a
weekday only when the source states it - in uploads/query-policy.md.

Why the flagging half matters as much as the rendering half
-----------------------------------------------------------
If the model writes an unbracketed "Aug 6", substitution simply finds
nothing, the raw text ships, and the run looks *identical to success*.
That is the same fail-open shape as the map that went unused. Findings
are reported to stderr and set a nonzero exit status so a bypassed run is
visibly different from a clean one.

Verbatim quoted source text is exempt from both halves: a newsletter
quoting a Slack message correctly contains the source's own wording, and
reformatting inside a quotation would corrupt the evidence.
"""
import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

BRACKET_RE = re.compile(r"\[(\d{4})-(\d{2})-(\d{2})\]")

_FULL_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
_ABBR_MONTHS = "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
_FULL_DAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
_ABBR_DAYS = "Mon|Tues|Tue|Weds|Wed|Thurs|Thur|Thu|Fri|Sat|Sun"

MONTH_RE = re.compile(rf"\b(?:{_FULL_MONTHS}|{_ABBR_MONTHS})\b\.?")
WEEKDAY_RE = re.compile(rf"\b(?:{_FULL_DAYS}|{_ABBR_DAYS})\b\.?")
NUMERIC_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Spans whose contents are source wording, not the report's own prose.
FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)
BLOCKQUOTE_RE = re.compile(r"^[ \t]*>.*$", re.MULTILINE)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
QUOTED_RE = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”")

# A weekday name is only a date assertion when it sits next to a date. A
# bare "we meet Saturday" is a recurring schedule, not something to
# normalize - flagging those would drown the real findings.
WEEKDAY_ADJACENCY_CHARS = 2


@dataclass(frozen=True)
class Finding:
    line: int
    kind: str  # unbracketed-date | invalid-date | out-of-range
    text: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.kind}: {self.text!r}"


@dataclass
class Result:
    text: str
    findings: list[Finding] = field(default_factory=list)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _protected_mask(text: str) -> list[bool]:
    """Character mask of regions that are verbatim source wording: fenced
    blocks, blockquote lines, inline code spans, and quoted spans."""
    mask = [False] * len(text)

    def mark(start: int, end: int) -> None:
        for i in range(start, min(end, len(text))):
            mask[i] = True

    fences = [m.start() for m in FENCE_RE.finditer(text)]
    for opening, closing in zip(fences[::2], fences[1::2]):
        end = text.find("\n", closing)
        mark(opening, len(text) if end == -1 else end + 1)
    # An unclosed fence protects everything after it.
    if len(fences) % 2 == 1:
        mark(fences[-1], len(text))

    for pattern in (BLOCKQUOTE_RE, INLINE_CODE_RE, QUOTED_RE):
        for m in pattern.finditer(text):
            mark(m.start(), m.end())
    return mask


def _is_protected(mask: list[bool], start: int, end: int) -> bool:
    return any(mask[start:end])


def _render(d: date, fmt: str | None) -> str:
    if fmt:
        return d.strftime(fmt)
    # Built explicitly rather than with "%-d", which is not portable.
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


def process(
    text: str,
    fmt: str | None = None,
    *,
    min_date: date | None = None,
    max_date: date | None = None,
    strict_weekdays: bool = False,
) -> Result:
    """Substitute [YYYY-MM-DD] tokens and report anything that bypassed
    them. Returns the rendered text plus every finding; the caller decides
    what to do about them (see exit_status)."""
    mask = _protected_mask(text)
    findings: list[Finding] = []

    bracket_spans: list[tuple[int, int]] = []
    replacements: list[tuple[int, int, str]] = []

    for m in BRACKET_RE.finditer(text):
        bracket_spans.append((m.start(), m.end()))
        if _is_protected(mask, m.start(), m.end()):
            continue  # quoted source wording stays verbatim
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            findings.append(Finding(_line_of(text, m.start()), "invalid-date", m.group(0)))
            continue
        if (min_date and d < min_date) or (max_date and d > max_date):
            findings.append(Finding(_line_of(text, m.start()), "out-of-range", m.group(0)))
        replacements.append((m.start(), m.end(), _render(d, fmt)))

    def inside_bracket(start: int, end: int) -> bool:
        return any(bs <= start and end <= be for bs, be in bracket_spans)

    dateish: list[tuple[int, int]] = []
    for pattern in (MONTH_RE, NUMERIC_DATE_RE, ISO_RE):
        for m in pattern.finditer(text):
            if _is_protected(mask, m.start(), m.end()) or inside_bracket(m.start(), m.end()):
                continue
            dateish.append((m.start(), m.end()))
            findings.append(Finding(_line_of(text, m.start()), "unbracketed-date", m.group(0)))

    anchors = dateish + bracket_spans
    for m in WEEKDAY_RE.finditer(text):
        if _is_protected(mask, m.start(), m.end()):
            continue
        adjacent = any(
            0 <= start - m.end() <= WEEKDAY_ADJACENCY_CHARS
            or 0 <= m.start() - end <= WEEKDAY_ADJACENCY_CHARS
            for start, end in anchors
        )
        if strict_weekdays or adjacent:
            findings.append(Finding(_line_of(text, m.start()), "unbracketed-date", m.group(0)))

    out = []
    cursor = 0
    for start, end, rendered in sorted(replacements):
        out.append(text[cursor:start])
        out.append(rendered)
        cursor = end
    out.append(text[cursor:])

    findings.sort(key=lambda f: (f.line, f.text))
    return Result("".join(out), findings)


def exit_status(result: Result) -> int:
    """Fail-closed: a run that bypassed the contract must not be
    indistinguishable from a clean one."""
    return 1 if result.findings else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render [YYYY-MM-DD] tokens in LLM newsletter output and flag date text that bypassed them.",
    )
    parser.add_argument("input", nargs="?", help="input file (default: stdin)")
    parser.add_argument("-o", "--output", help="output file (default: stdout)")
    parser.add_argument("--format", dest="fmt", help="strftime format (default: 'Thursday, August 6, 2026')")
    parser.add_argument("--min-date", type=date.fromisoformat, help="flag rendered dates before this date")
    parser.add_argument("--max-date", type=date.fromisoformat, help="flag rendered dates after this date")
    parser.add_argument(
        "--strict-weekdays",
        action="store_true",
        help="also flag standalone weekday names (noisy: catches recurring schedules too)",
    )
    parser.add_argument("--lenient", action="store_true", help="always exit 0, even with findings")
    args = parser.parse_args(argv)

    text = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    result = process(
        text,
        args.fmt,
        min_date=args.min_date,
        max_date=args.max_date,
        strict_weekdays=args.strict_weekdays,
    )

    if args.output:
        Path(args.output).write_text(result.text, encoding="utf-8")
    else:
        sys.stdout.write(result.text)

    for finding in result.findings:
        print(f"postprocess-dates: {finding}", file=sys.stderr)
    if result.findings:
        print(
            f"postprocess-dates: {len(result.findings)} finding(s) - date text bypassed the "
            "[YYYY-MM-DD] contract and was NOT normalized",
            file=sys.stderr,
        )
    return 0 if args.lenient else exit_status(result)


if __name__ == "__main__":
    sys.exit(main())
