# ADR-0007: Digest v6 Replaces the Merged `description` with Slack's `purpose`, Renamed to Match Slack's UI

Status: Accepted
Date: 2026-08-08

## Context

Since `slack-llm-digest-v2` (ADR-0001), each channel's digest metadata has carried a `description`
field produced by `catalog_logic.description_of()`: Slack's `topic` if set, else Slack's `purpose`.
`topic` and `purpose` were added alongside it, unmerged, specifically because that merge silently
drops one of the two whenever both are set (`_channel_context`'s docstring) — a channel can use
`topic` for logistics and `purpose` for its actual charter, and losing either is a real signal loss.

In practice this left three overlapping fields in front of the LLM consumer. Slack's own UI only
exposes two of these concepts: the small pinned text at the top of a channel (Slack's `topic`
field) and the "Description" field in the channel-details panel — which is Slack's `purpose` field
under the hood, not this project's synthesized merge. A user reading the digest has no way to
correlate this project's `description` with anything Slack shows them, and risks reading it as
authoritative when it may have silently dropped the `purpose` text `docs/llm-context/uploads/
ingestion-contract.md` already tells them to read independently. The merge itself was pure
passthrough in the digest — computed once by `catalog_logic.description_of()` for the catalog
cache, then re-surfaced as-is by `export_logic._channel_context` with no digest logic depending on
it (activity status, mentions, etc. never read it).

## Decision

`export digest`'s output becomes `schema_version: "slack-llm-digest-v6"`. The digest's channel
metadata field named `purpose` is renamed to `description`, carrying Slack's raw `purpose` value
verbatim — matching what Slack's own UI calls this field, rather than this project's internal API
name for it. The prior synthesized `description` field (topic-falls-back-to-purpose) is dropped.
`topic` is unchanged.

This is a digest-output naming change only. `catalog_logic.description_of()`, the catalog cache's
own `description` field, and other consumers of the catalog's merge (`catalog.py`'s CLI listing,
`channel_digest_logic.py`'s separate `slack-channel-digest-v2` schema) are unaffected — they are
not part of the LLM-facing digest this ADR addresses.

## Consequences

- A consumer reading the digest sees `topic` and `description`, matching the two fields Slack's own
  UI shows, with no synthesized third value to reconcile against them.
- No data loss: everything the old merged `description` could show was already present, unmerged,
  in `topic`/`purpose`. A consumer that read only `description` for a quick channel description
  string previously got a topic-or-purpose value; it now gets `purpose` alone, named `description`,
  which is what Slack's UI itself calls "Description" — closer to what such a consumer expected.
- A consumer that relied on the old merge's topic-falls-back-to-purpose behavior (reading
  `description` and expecting `topic` when `purpose` was unset) must now read `topic` explicitly;
  the two fields no longer overlap.
- Additive-only convention (ADR-0001) does not apply to this change — a field rename/removal is a
  breaking shape change, hence the version bump to v6, consistent with v3's removal of
  `posted_at_utc` (ADR-0002).
