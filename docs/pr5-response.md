# PR #5 Response — Analysis and Recommended Reply

Status: Draft — for review
Date: 2026-08-11
Source PR: [#5](https://github.com/stuartdonaldson/slack-archive-toolkit/pull/5) (`andreBurnt`)
Companion: [pr5-recovery-plan.md](pr5-recovery-plan.md) (2026-08-09 evaluation of the stale diff)

This document covers the state of PR #5 **after Andre's 2026-08-10 reply**, in which he responded to
all three points, conceded two of them with supporting data, and asked a direct question that is still
unanswered. It records what each issue actually is, what our analysis found, what we recommend doing,
and what to say back to him.

---

## Context: the pipeline, and why it drives two different answers

Most of the disagreement on this PR dissolves once the workflow is written down. **The digest has two
downstream consumers, and only one of them has a stage after the LLM.**

```
                          ┌─────────────────────────────────────────────┐
                          │  PATH 1 — newsletter production (automated) │
                          │                                             │
  slackdump archive       │   render prompt → LLM → post-processor →    │
        ↓                 │                        published newsletter │
  slackbackup backup run  │                                             │
        ↓                 └─────────────────────────────────────────────┘
  slackbackup export      ↗
    digest + sidecar  ────
    + user profiles     ↘
                          ┌─────────────────────────────────────────────┐
                          │  PATH 2 — interactive query (human in loop)  │
                          │                                             │
                          │   ChatGPT Project / session → answer read    │
                          │   directly by the person who asked           │
                          └─────────────────────────────────────────────┘
```

**slackbackup's scope ends at the digest.** The LLM step, the render prompt, and any post-processing
are outside this repo. What this repo *does* own on both paths is the guidance that shapes the LLM's
behavior: `docs/llm-context/` (ingestion contract, query policy, prompt templates).

The two paths differ in the one way that matters here:

| | Path 1 — newsletter chain | Path 2 — interactive query |
|---|---|---|
| Stage after the LLM | Deterministic post-processor, then published | None — the user reads the answer |
| Enforcement available | Machine-checkable | Instruction-layer only |
| Output variety | One fixed prompt | Any question |
| Failure blast radius | Published to the region, unattended | One reader, in context |

The consequence, and the through-line of this whole response: **instruction-layer rules suffice where
a human reads the answer in context; deterministic checks are required where output publishes
unattended.** Where a fix belongs, and what form it takes, depends on which path it serves.

### Assumptions we have not confirmed with Andre

The recommendations below depend on these. If any is wrong, say so before we reply:

1. **Andre's render prompt is his own file**, not this repo's `docs/llm-context/prompts/newsletter.md`.
   He referred to "my render prompt," and this repo's `README.md` frames `prompts/` as templates a
   human pastes into a chat — i.e. Path 2 artifacts. So the repo currently ships **no** Path 1 artifacts.
2. **No post-processor exists on his side yet.** He wrote "if you build it," which reads as an open
   question about ownership rather than a claim that he has one.
3. **His chain is automated and its output is published** to PAX, not just read by him.
4. **He is running the toolkit himself** across six workspaces and would keep doing so.

---

## Issue 1 — Dates and weekdays

### What Andre asked

Originally: add `calendar_reference_2026`, a date→weekday map, to the digest manifest, because a render
invented "Wed Aug 6" for 2026-08-06 (a Thursday).

In his reply he **withdrew this** and adopted the normalization approach instead: instruct the LLM to
emit every date as `[YYYY-MM-DD]`, then post-process into a localized format. His one remaining ask:

> "have the post-processor flag date-shaped strings that are not in `[YYYY-MM-DD]`. Otherwise one
> unbracketed 'Aug 6' skips the mechanism silently, and that looks identical to success."

### What our analysis showed

Andre's own receipt killed the original design, and it is worth restating because it generalizes: the
digest he rendered from **did** carry `calendar_reference_2026` — 78 entries, 2026-05-01 to 2026-07-17.
The date he got wrong, 2026-08-06, fell outside that range, because the map is bounded by the digest
window and the message was announcing a *future* event. Worse, by his account the map went unused for
the dates it *did* cover. **Supplying reference data does not make a model consult it.**

His ask is sound and the reasoning generalizes past dates: a mechanism that silently fails to apply,
while producing confident output, is indistinguishable from one that worked. That is the same shape as
the unused map. Any control we add should be fail-closed where a machine can check it.

Two refinements his version needs:

- **Quoting must be exempt.** A newsletter quoting a Slack message correctly contains "Aug 6". The pack
  requires verbatim reproduction of source wording in several places, so a naive detector both
  false-positives and pressures the model to alter quotes.
- **Bracket form does not fix date *resolution*.** The model still infers the year and resolves
  relatives like "next Thursday." A confidently wrong `[2025-08-06]` renders into a perfectly formatted
  wrong date. A range check against the digest's own coverage window catches that class; the bracket
  check cannot.

And critically — **the contract is wrong for Path 2.** Forcing bracketed dates into interactive answers
hands a reader raw `[2026-08-06]` tokens that nothing will ever render. Same root cause, different fix.

### Recommended solution — built, `sat-sa8`, commit `6c6b0ac`

**Path 1:** `docs/llm-context/prompts/newsletter-postprocessed.md` (an overlay on `newsletter.md`, so
newsletter content cannot drift between two copies) states the contract, the quoting exemption, and the
rationale. `scripts/postprocess_dates.py` renders bracketed dates with a computed weekday, flags
date-shaped text that bypassed the contract, exempts quoted spans (quotes, blockquotes, inline code,
fenced blocks), and exits nonzero on findings. Optional `--min-date`/`--max-date` implements the range
check. 23 tests; full suite 488 green.

Demonstration against his exact failure case:

```
The Sausage birthday party is Thursday, August 6, 2026 at the AO.
The next convergence is Wed Aug 6.
> Original message: "Aug 6 post-ao-thoreau-sasquatch party at my place"

postprocess-dates: line 2: unbracketed-date: 'Aug'
postprocess-dates: line 2: unbracketed-date: 'Wed'
EXIT=1
```

Line 1 normalized; line 2 bypassed the contract and is flagged rather than silently shipped; line 3 is
quoted source and left verbatim.

**Path 2:** `prompts/newsletter.md` and `uploads/query-policy.md` now say to state a weekday only when a
source states it, and to report a source-stated weekday that contradicts its date as a conflict rather
than silently correcting either.

`sat-rve` (manifest `calendar_reference`) is closed as superseded. **Note:** `pr5-recovery-plan.md`
§Next Steps has the `sat-hds`/`sat-tdv` labels swapped relative to the actual bd issues — worth fixing
in that document.

**Still outstanding:** none of this has faced a real LLM render. Manual testing pending.

---

## Issue 2 — `convert -files=false`

### What Andre asked

Run `slackdump convert` with `-files=false` so one deleted Slack attachment cannot kill an entire
95-channel digest run. In his reply he supplied a full repro:

```
ERROR file converter: error processing message
  ├ ts: 1776952524.936029
  └ err: copy error: file ID=F0AUY7QQ74L: file does not exist
```

`f3tundra/ao-woodhs-tundra`, Slackdump 4.4.0 (901ed8b0), exit 6 without the flag and exit 0 with it.
Across his archive root: 26 file IDs in 5 of 95 channels against 2,434 that convert fine, of which 9 are
`MODE='tombstone'` — gone on Slack's side while slackdump still emits a FILE row.

### What our analysis showed

**Verified safe.** `_load_channel_files` (`src/slackbackup/export_logic.py:778`) builds
`blob_path = channel_dir / "__uploads" / id / name` — the **archive** tree written by `slackdump
archive`. `convert` writes to a separate `-o` directory. Nothing in the digest, the files sidecar,
`content_sha256`, or `archive_status` reads convert's output. Disabling its file copying cannot affect
extracted content.

The digest already models the underlying data condition gracefully: `_file_archive_status` emits
`tombstone` and `no_blob`. So this is purely about not letting convert's file-copy stage abort a
text-only pipeline. Andre's point that regular backups don't protect you is correct — someone deleting a
photo after the archive recorded it is enough.

One caution on his synthetic repro: `rm -rf <archive>/__uploads/<file-id>` deletes from the real
archive, which also flips that file to `no_blob` in every future digest. Fine for reproducing, not for
an archive you care about.

### Recommended solution

**Take it, as `sat-tdv`.** This is the one piece ready to land unchanged. Andre offered to make it a
parameter with the digest path passing files off; that is unnecessary complexity for now — nothing in
this repo wants convert's copies. A flag can be added if an export mode ever needs them.

---

## Issue 3 — Channel categories

### What Andre asked

`derive_channel_category` (classifying `ao-*`, `event-*`, `1st-f`, bot/log, …) plus an
`is_probably_bot_or_log_channel` flag, so a render can slice 95 channels by role. His use case is one
line in his render prompt: coordination channels are the events source, `ao-*` is the culture source.

In his reply he **conceded the architecture** — `handlers/f3.py` is the right home — and proposed
returning `(category, basis)` with no F3 patterns in the core pipeline. He answered the topic/purpose
question with data: across 95 channels, **name settles 88, description settles 1, 6 unknown** (topic
non-empty on 68, description on 82). AO descriptions carry the workout or the address, not the role:

```
ao-mother-rucker  Building mental and physical endurance.
ao-bobcat         Hartman Park - Park near the soccer field, 17301 NE 104th St, Redmond
```

He ended with: **"Send it, or hold until you've settled the extension shape?"** — still unanswered.

### What our analysis showed

His proposal matches `sat-hds` and `DESIGN-export.md` §Known Gaps, which already called for the
`handlers/f3.py` route rather than a bare function in `export_logic.py`.

**The extension shape is already settled**, which answers his question directly. `handlers/f3.py`
exposes two established shapes: `build_leadership(profiles_doc)` (whole-document) and
`annotate_profile(display_name, title)` (per-record, called at `export_logic.py:2494`). His
`(category, basis)` per channel is `annotate_profile`'s shape exactly — an `annotate_channel(name,
description)` mirrors it with no new extension design needed.

**One conflict nobody has noticed.** `uploads/query-policy.md`'s routing table sends "What does a
channel exist for?" to topic and purpose, and explicitly lists "Channel name alone" under *do not infer
from*. Andre's 88-vs-1 measurement is direct evidence that for AO/coordination taxonomy the name is the
reliable signal. These aren't strictly contradictory — taxonomy and charter are different questions —
but if a handler-derived category ships, the policy needs either a carve-out or the category promoted
to a structured digest field (rank 4) that the policy can cite. Otherwise the pack instructs the model
to ignore the very signal the export just computed.

### Recommended solution

Answer the extension-shape question with `annotate_profile` as the precedent, and let him send it
against that contract. File the `query-policy.md` routing conflict as a follow-up so it doesn't surface
after `sat-hds` lands.

---

## The coordination problem — decide before replying

`pr5-recovery-plan.md` records the plan of record as **close PR #5 and deliver the three intents as
fresh work**. That decision has never been stated on the thread.

Meanwhile Andre has offered to do work three times: "I'll rebase onto current main," "I can split them
if that helps," and "Send it, or hold?" He is about to spend an evening rebasing a 78-commit-stale diff
toward a PR we intend to close, while two of its three pieces are already re-specified as our own bd
issues and the third has changed design entirely.

Whatever we decide, the thread needs it said plainly, including which pieces we would still take from
him directly. Given the quality of that last comment — a self-refuting receipt against his own patch, a
complete repro with prevalence data, and a measured answer to the topic/purpose question — the better
outcome is him contributing to `sat-hds` rather than being closed out against a plan document he cannot
see.

---

## Recommended reply to Andre

> That reply is exactly what I needed on all three — thanks, particularly for going back and checking
> your own digest on the calendar item.
>
> **Housekeeping first:** don't rebase. Main has moved 78 commits since your branch point (v6 digest
> schema, files sidecar, a `topic`/`description` split), so the diff won't survive the trip. I'm going
> to close this PR and land the three intents as fresh work — not a rejection of the content, just the
> cheapest path from here. Tracked as separate issues, and I'd like your name on the third one.
>
> **1) Dates.** Agreed, and your receipt settles it — a map bounded by the digest window can't cover an
> upcoming-event announcement, and it went unused for the dates it did cover anyway. I've built the
> normalization side: a prompt overlay stating the `[YYYY-MM-DD]` contract, and a post-processor that
> renders them with a computed weekday.
>
> Your ask is in, with two changes. Quoted spans are exempt — a newsletter quoting "Aug 6 party at my
> place" should reproduce it verbatim, so the detector skips quotes, blockquotes, inline code and
> fenced blocks — otherwise the check fights the pack's own verbatim-quoting rules. And I added an
> optional date-range check, which I think is the more valuable half: bracket form fixes weekday
> fabrication but not date *resolution*, so a confidently wrong `[2025-08-06]` still renders into a
> perfectly formatted wrong date. The range check catches that; the bracket check can't.
>
> One thing worth flagging: this contract is right for your automated chain and wrong for the
> interactive path, where people query the data in a ChatGPT Project and nothing post-processes the
> answer. Handing them raw `[2026-08-06]` would be worse than the bug. So the shared prompt and query
> policy get a different fix for the same root cause — state a weekday only when the source states one.
>
> **2) `convert -files=false`.** Taking it as-is. I traced the read path to be sure: the digest reads
> blobs from the archive's own `__uploads/`, while convert writes to a separate output dir, so nothing
> in the pipeline reads what convert copies and the flag can't affect extracted content. Not making it
> a parameter for now — nothing here wants the copies. Thanks for the prevalence numbers and the
> synthetic repro; the tombstone class is the part that convinced me, since regular backups genuinely
> don't protect against it.
>
> **3) Channel categories — send it.** The extension shape is already settled and I should have said so
> earlier: `handlers/f3.py` has two established shapes, `build_leadership(profiles_doc)` for
> whole-document work and `annotate_profile(display_name, title)` per record. Your `(category, basis)`
> is `annotate_profile`'s shape exactly, so `annotate_channel(name, description)` mirrors it and the
> core pipeline just carries an optional handler-supplied field. No new extension design needed.
>
> Your 88-vs-1 number also surfaced something on my side: my own query policy tells the model to answer
> "what is this channel for?" from topic/purpose and explicitly *not* from the channel name. Your data
> says the opposite for the AO/coordination taxonomy. I don't think they actually conflict — taxonomy
> and charter are different questions — but I need to reconcile that before the category field ships,
> or the guidance will tell the model to ignore the field the export just computed. Filing that
> separately.

---

## Open decisions

1. **Close PR #5, or keep it open for the category work?** Nothing goes to Andre until this is settled.
2. **Is the prompt overlay the right form**, or does Andre's chain need one standalone pasteable file?
3. **Does the render prompt become a repo artifact?** Today the repo ships only Path 2 artifacts. If the
   chain should be reproducible by us, `prompts/` needs splitting by consumer, because the two kinds
   carry contradictory date rules.
4. **An ADR for the two-consumer split?** The "instruction-layer where a human reads, deterministic
   where it publishes" principle will shape future pack rules and is currently recorded only here.
