# Prompt overlay: newsletter with post-processed dates

**Overlay, not a replacement.** Paste [newsletter.md](newsletter.md) first, then this
block. Everything in the base prompt still applies; this changes only how dates are
written, so the two files cannot drift apart on newsletter content.

**For the automated render chain only.** This overlay assumes a post-processing step
runs on your output before anyone reads it — `scripts/postprocess_dates.py` in this
repo. Do not use it for an interactive ChatGPT session, where nobody post-processes
the answer and a reader would be left staring at raw `[2026-08-06]` tokens. The
interactive path handles the same problem differently; see
[query-policy.md](../uploads/query-policy.md).

## Why

An LLM gets day-of-week arithmetic wrong. A render of this newsletter printed
"Wed Aug 6" for 2026-08-06 — a Thursday — while the digest it read from carried a
78-row date-to-weekday map that went entirely unused. Supplying reference data does
not make a model consult it.

So the work splits by what each half is actually good at. You resolve "Aug 6" in a
message posted 2026-07-06 to a specific calendar date, which is interpretation, and
you do it well. The script computes the weekday and formats the date, which is
arithmetic, and it does not get it wrong.

## The contract

Write **every date in your own prose** as `[YYYY-MM-DD]`, brackets included.

Do not write weekday names or month names in your own text. The post-processor
renders `[2026-08-06]` into "Thursday, August 6, 2026" — whatever localized format
the operator has configured.

Resolve partial and relative dates ("Aug 6", "next Thursday", "this weekend") using
the source message's own posting date. If the year or the exact date cannot be
determined confidently, say what is uncertain rather than emitting a bracketed date
you had to guess at — a wrongly resolved date renders into a confidently wrong
sentence.

Do not write the weekday yourself even when you are sure of it. If it is right, the
script would have produced it anyway; if it is wrong, you have introduced the exact
error this contract exists to prevent.

## Quoted source text is exempt

When you quote a Slack message, canvas, or channel description verbatim, reproduce
the source's own wording exactly — including its dates. Do not convert a date inside
a quotation to bracket form. The post-processor skips quoted spans (double quotes,
blockquote lines, inline code, fenced blocks) for the same reason: reformatting
inside a quotation would corrupt the evidence.

So this is correct, and both halves are intentional:

> The party is [2026-08-06]. The original post read "Aug 6 party at my place".

## What happens if you skip a bracket

The post-processor flags any date-shaped text that never went through a bracket and
exits nonzero. An unbracketed "Aug 6" is not silently tolerated — but it does reach
the operator as a failed run rather than as a corrected newsletter, so the contract
is worth following rather than relying on.

## Running it

```bash
python3 scripts/postprocess_dates.py draft.md -o newsletter.md
# --format '%b %-d'      alternate output format
# --min-date/--max-date  flag dates outside the expected window (catches a
#                        misresolved year, which bracket form alone cannot)
```
