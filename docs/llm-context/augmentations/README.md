# Augmentations index

Indexes the currently active dated manual augmentations. Each file uses a stable name (not a dated filename) and carries its currency in a header block (`collected:`, `source:`, `collected_by:`, `fidelity:`, `coverage:`, `known_gaps:`, `refresh_trigger:`, `refresh_owner:`) so "any applicable dated augmentation" in the upload set is a lookup, not a judgment call.

See [query-policy.md §Dated augmentation evidence](../query-policy.md#dated-augmentation-evidence) for how these rank against Slack evidence.

## Active

| File | Covers | Collected |
| --- | --- | --- |
| [f3-nation-operations.md](f3-nation-operations.md) | F3-Nation Slack bot features, role/ownership distinctions, diagnostic routing | 2026-06-30 |
| [f3-nation-admins.md](f3-nation-admins.md) | F3-Nation app admin roster by region | 2026-06-30 |

## Archive

Superseded snapshots, when history is useful, live under `archive/<name>-<date>.md`. None yet.

## Maintenance

- Update a roster or operations file by editing its Markdown table/content and header block together.
- Update the `collected:` date whenever the underlying facts are re-verified, even if unchanged.
- Generate a JSON derivative only for a demonstrated automated consumer; generate it from the reviewed Markdown, never hand-edit both.
