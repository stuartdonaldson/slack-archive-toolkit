# ADR-0002: Digest Condenses to slack-llm-digest-v3 by Dropping Redundant Timestamp and Compacting Serialization

Status: Accepted
Date: 2026-07-13

## Context

A real `slack-llm-digest-v2` export (2026-07, 7 workspaces) measured ~22.6 MB. Per-field
measurement found two large, avoidable contributors: `json.dumps(..., indent=2)` whitespace
accounted for ~26% of the file's bytes, and the per-message `posted_at_utc` field alone
accounted for ~1.0 MB — despite being fully redundant with `posted_at_local` (UTC is derivable
from either its ISO-8601 offset or the message's `ts` epoch). Both are pure serialization/schema
overhead with no information loss on removal.

Two approaches were considered for what else to drop alongside these:

- **Also drop `message_url`** (also mechanically derivable, from `workspace`/`channel_id`/`ts`
  via `digest_message_url`) — rejected. ADR-0001's ingestion prompt (`docs/slack-ingestion.md`)
  explicitly forbids the downstream LLM from constructing a `p<ts>` permalink itself; `message_url`
  exists to remove that construction from the LLM's responsibility, not merely to save it
  arithmetic. Dropping it would reintroduce the citation-construction risk ADR-0001 designed
  around, for a per-message byte savings smaller than `posted_at_utc`'s.
- **Drop `posted_at_utc` and compact the file's serialization** *(chosen)* — remove only the
  measured, genuinely redundant timestamp field, and switch the digest file's write from
  `indent=2` to `separators=(",", ":")` (no `ensure_ascii` escaping). Both are mechanical,
  reversible-in-derivation changes with no schema semantics lost.

## Decision

`export digest`'s output becomes `schema_version: "slack-llm-digest-v3"`: `posted_at_utc` is
removed from every message/reply (`posted_at_local` remains the digest's only timestamp field),
and the digest file itself is written compact
(`json.dumps(result, ensure_ascii=False, separators=(",", ":"))`) instead of `indent=2`.
`message_url` is retained unchanged. `export_month`'s per-channel-month export and the
`users_out` profile export are unaffected — both stay pretty-printed; only the digest file's
write path changes.

## Consequences

- Measured real-digest size dropped from ~22.6 MB (v2) to ~15.7 MB (v3), with parsed JSON content
  identical apart from the absence of `posted_at_utc`.
- A consumer that read `posted_at_utc` directly (rather than deriving UTC from
  `posted_at_local`'s offset or from `ts`) breaks against v3 output — an intentional, documented
  break, unlike v2's purely additive evolution over v1 (ADR-0001). `docs/slack-ingestion.md`'s
  ingestion prompt is updated accordingly to read `posted_at_local` only.
- The digest file is no longer human-readable by casual inspection (`cat`/scrolling); it must be
  formatted (`python -m json.tool`, `jq .`) for manual review. Accepted, since the digest's
  primary consumer is an LLM prompt, not a human reader.
- `export_month` and `users_out` keep their existing `indent=2` writes — this ADR only condenses
  the digest file. `users_out` (measured ~5.9 MB at `indent=2`) remains a candidate for the same
  treatment as a possible follow-up, not addressed here.
