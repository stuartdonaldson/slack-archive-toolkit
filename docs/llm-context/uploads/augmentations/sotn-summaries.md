# F3 State of the Nation call summaries

Cumulative, dated augmentation. This file is **not** a verbatim transcript. It
is a hand-compiled summary of each SLT-hosted State of the Nation (SOTN) call.
The raw machine transcript for a call is retained separately under `sources/`.

Unlike the single-snapshot roster/operations augmentations, this file grows by
**appending a new dated entry each time a SOTN call is held** — it does not
describe a single point-in-time state and is never fully superseded by a later
entry. Earlier entries remain valid for the facts and dates they carry even
after a newer call happens.

See [query-policy.md §Dated augmentation evidence](../query-policy.md#dated-augmentation-evidence)
for how each entry ranks against Slack evidence. Apply `fidelity` per entry,
not once for the whole file.

## Purpose

SOTN calls are the shared leadership team's periodic address to the nation:
role/roster changes, tech-stack and tool updates, growth and membership
figures, safety-practice guidance, and named initiatives that are not otherwise
captured in Slack messages, channel topics, or the digest export. These are
nation-level leadership updates that may affect regions or PAX; they are not
reports about a specific region or individual PAX. Use this augmentation when a
question needs a fact the SLT stated directly on a call — a role holder, a
stated headcount, a program name — and Slack evidence doesn't already answer
it.

Each entry summarizes facts likely to matter for regional inquiries, not a
verbatim replay. The full raw transcript is retained under `sources/` for direct
quotation or dispute resolution — cite the entry for the fact, and the source
transcript only for the exact wording.

## Entries

### 2026-07 SOTN (call labeled "July 2026" in the recording; transcribed 2026-07-30)

| Field | Value |
| --- | --- |
| `collected:` | 2026-07-30 |
| `source:` | Audio transcript of the July 2026 F3 Nation State of the Nation call |
| `collected_by:` | Project maintainer (manual transcription/extraction) |
| `fidelity:` | `hand-compiled` |
| `coverage:` | SLT roster and roles as stated on the call; tech-stack/tool status and usage counts; growth/membership figures; new growth-team role structure; a named PAX loss and associated safety-practice guidance; resource/program links |
| `known_gaps:` | Exact calendar date of the call is not stated in the transcript, only "July 2026"; figures are as spoken on the call and may already be stale by the time this is read; transcript is machine-generated from audio and may contain transcription errors, especially names |
| `refresh_trigger:` | Next SOTN call (add as a new entry below; do not edit this one) |
| `refresh_owner:` | Project maintainer |

Source transcript: [`sources/sotn-2026-07-30-transcript.md`](sources/sotn-2026-07-30-transcript.md).

**SLT roster and roles named on this call:**

| Nickname | Name | Role |
| --- | --- | --- |
| Tinkerbell | Brent Bearinger | Weasel shaker (SLT), STL County Line region |
| Dark Helmet | Frank Schwarz | Nantan |
| Scratch (and win) | John Horton | Executive director of the nation |
| Moneyball | Evan Pzle | Head of IT |
| Huckleberry | Jonathan Stevens ("Huck Elberry" as introduced) | Head of culture |
| Vanilla Ice | Matthew Melton | Head of growth |
| Power Clean | Drew Ishmail | Head of sectors |
| Camo | Kevin Weaver | Head of leadership development |
| Gilligan | Peter Madison | SLT |

**Tech / tools (from Moneyball, head of IT):**

- New consolidated tools landing page at `apps.fnation.com`.
- Usage as stated on the call: F3 Map ~40,000 monthly users; Exacon/Lexicon ~14,000 users; Pax Vault (Slack-app attendance dashboard); F3 Nation Slack app ~325 regions, ~20,000 daily active users.
- "Crash" (Denver South) joined the IT team as code cue.
- Stated in-progress/future work: new integrations with upcoming stack changes, a knowledge-management effort, and early scoping of a unified F3 app.
- Support channels named: `tech-general`, the map channel, `slackbot`, `codeex`; email `it@f3nation.com` (as spoken — verify domain before citing externally).

**Growth figures (as stated, not audited):**

- Over 100,000 men nation-wide; ~550 regions, growing by ~3/week; over 6,600 AOs, growing by ~3/day.
- 25+ international regions active, 60+ pending, spanning multiple countries (Australia, Brazil, Canada, El Salvador, France, the country of Georgia, Hong Kong, Singapore, India, Papua New Guinea named as examples).

**New growth-team role structure (from Power Clean, head of sectors):** DOA, sector cues, state cues, area cues, feeding into a growth cue per state; stated need for a growth cue in every state.

**Named PAX loss and safety guidance (from Camo, head of leadership development):** a PAX known as "Jigalo" (FTX region, age 47) died of a cardiac event following a Saturday workout. Cited best practices credited with readiness in that region: queue carries a phone, PAX know their physical address for emergency response, a designated sweeper so no man is dropped, a designated CPR queue, and run "man down" drills. Regions without these practices were pointed to Sectors or LDP for help implementing them.

**Programs/resources named:** `F3nationresources` (curated top-20 resource list); a nationwide mentorship "wetstone/blade" program, sign-up via the Leadership Development Slack channel; the F3 Advisory Council (a non-governing, non-fiduciary donor/strategic-guidance group, recruiting additional members); "Region in a Box" (new-region starter kit) and a lighter "tier two" kit for starfished regions; the annual "Accelerate" giving campaign (next cycle launching October 1).

<!-- Add the next SOTN call as a new "### <period> SOTN" entry below this line, oldest first. Do not edit or delete a prior entry; superseded facts get a note in the new entry pointing back at what changed. -->

## Maintenance

- After each new SOTN call: transcribe or obtain the transcript, save the raw source under `sources/`, and append a new dated entry above using the same header-block fields.
- Extract facts relevant to regional inquiries (roles, tools, figures, named programs, safety guidance); don't try to make the summary a full replay — cite the source transcript for exact wording.
- Note explicitly in a new entry when it corrects or updates a fact from an earlier entry; leave the earlier entry's text unchanged (it's a historical record of what was said on that date).
- Add the new entry to [the context-pack README](../../README.md)'s Active table `Collected` column update, and to this file — the README table points at "this file", not at each entry.
