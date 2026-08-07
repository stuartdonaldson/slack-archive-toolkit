# Augmentations index

This is the place for dated, hand-maintained facts relevant to regional F3
questions that come from sources **outside** the Slack export — a call
transcript, a manual review of an app screen, a hand-compiled roster. It is
not a fixed set: expect it to grow over time as more such material is
identified. Some future augmentations may eventually be generated from an
automated source, but hand-maintained Markdown is the default and none are
auto-generated today.

Most files are a **single-snapshot** augmentation: one current state,
re-collected and overwritten in place when re-verified (`f3-nation-operations.md`,
`f3-nation-admins.md`). A file may instead be a **cumulative** augmentation
that appends a new dated entry each time its source recurs, without
superseding earlier entries (`sotn-transcripts.md`, for periodic call
transcripts) — check each file's own header for which pattern it follows.

Every file uses a stable name (not a dated filename) and carries its currency in a header block (`collected:`, `source:`, `collected_by:`, `fidelity:`, `coverage:`, `known_gaps:`, `refresh_trigger:`, `refresh_owner:`) so "any applicable dated augmentation" in the upload set is a lookup, not a judgment call. A cumulative file carries one header block per entry instead of one for the whole file.

See [query-policy.md §Dated augmentation evidence](../query-policy.md#dated-augmentation-evidence) for how these rank against Slack evidence.

## Active

| File | Covers | Collected |
| --- | --- | --- |
| [f3-nation-operations.md](f3-nation-operations.md) | F3-Nation Slack bot features, role/ownership distinctions, diagnostic routing | 2026-06-30 |
| [f3-nation-admins.md](f3-nation-admins.md) | F3-Nation app admin roster by region | 2026-06-30 |
| [sotn-transcripts.md](sotn-transcripts.md) | SLT State of the Nation call transcripts (cumulative — one entry per call) | 2026-07-30 (latest entry) |

## Archive

Superseded snapshots, when history is useful, live under `archive/<name>-<date>.md`. None yet.

## Maintenance

- Update a roster or operations file by editing its Markdown table/content and header block together.
- Update the `collected:` date whenever the underlying facts are re-verified, even if unchanged.
- Generate a JSON derivative only for a demonstrated automated consumer; generate it from the reviewed Markdown, never hand-edit both.
