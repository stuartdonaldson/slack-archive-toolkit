# ADR-0001: Digest Evolves Additively to slack-llm-digest-v2, Preserving Raw Evidence Only

Status: Accepted
Date: 2026-07-13

## Context

`export digest`'s v1 output (`schema_version: "slack-llm-digest-v1"`) reduced every message down
to `ts`/`user`/`display_name`/`text`/`files`, a UTC-only `posted_at_utc`, and structural thread
nesting. External feedback (`docs/llm-leadership-improvement.md`, `docs/llm-digest2-idea.md`) and
two rounds of LLM consumer feedback on real digests identified concrete gaps: reactions, message
edits, subtypes, and link unfurls were silently dropped; a reply carried no `thread_ts` back to
its parent; timestamps forced every consuming LLM prompt to re-derive Pacific local time from
UTC; there was no stable per-channel ordering key once threads were nested (a reply can sort
before or after later root messages in true post-time); channels and messages had no citable
Slack URL; user mentions and links embedded in message text were unextracted; and there was no
compact, per-workspace way to resolve a referenced user id to a display name without shipping the
full user roster.

Three approaches were considered for fixing these gaps:

- **Flat message-array redesign** — drop the nested `replies[]` structure in favor of one flat,
  chronologically-sorted array of messages (root and reply alike), disambiguated by a
  `thread_ts`/`parent_ts` field. Rejected: two independent rounds of LLM consumer feedback on the
  existing digest explicitly endorsed the nested `messages → replies` reading shape as useful for
  following a conversation; a flat redesign would improve ordering at the cost of the structure
  reviewers said was already working.
- **Prompt-side-only fixes** — leave the exported JSON schema alone and instead patch
  `docs/slack-ingestion.md`'s ingestion prompt to ask the LLM to infer missing evidence (e.g.
  "guess whether a message was edited from its content"). Rejected: reactions, edits, subtypes,
  and unfurls are facts Slack already records; asking an LLM to infer facts that are simply
  absent from its input produces hallucination risk with no accuracy upside over just including
  the evidence.
- **Additive schema evolution to v2** *(chosen)* — keep every v1 field and the nested shape
  unchanged, and add new fields only: evidence fields (`reactions`, `edited`, `subtype`,
  `unfurls`) gated behind digest-only enrichment; `thread_ts` on replies; `posted_at_local`
  alongside `posted_at_utc`; a per-channel `seq` for stable chronological ordering across nested
  threads; `channel_url` and per-message `message_url` anchors; file `id`/`message_ts` anchors;
  `mentions`/`links` extraction; and a bounded, per-workspace `user_index`.

## Decision

The digest evolves **additively** to `schema_version: "slack-llm-digest-v2"`: v1's fields and
nested `messages → replies` structure are preserved unchanged, and v2 adds deterministic,
mechanically-derived enrichment on top — raw Slack evidence (reactions, edits, subtypes,
unfurls), structural/addressing fields (`thread_ts`, `seq`, `channel_url`, `message_url`, file
anchors), Pacific-local timestamps, and extracted `mentions`/`links`/`user_index`. All semantic
inference — continuation detection across message boundaries, event de-duplication, message
classification, resolving an ambiguous reference, and cross-workspace identity merging — is
deliberately left to the downstream LLM; the digest supplies evidence, not conclusions.

## Consequences

- Existing consumers reading only v1 fields (`ts`, `user`, `display_name`, `text`, `files`,
  `posted_at_utc`, the nested `replies[]` shape) continue to work unmodified against v2 output —
  no breaking change, no migration required for a consumer that ignores unfamiliar fields.
- `docs/slack-ingestion.md`'s ingestion prompt can drop its UTC-to-Pacific conversion instruction
  in favor of reading `posted_at_local` directly, removing a class of LLM arithmetic error.
- The digest stays a bounded, mechanical transform of the archive (no new Slack API calls, no
  new external dependency) — every v2 field is derived from data `slackdump convert -f export`
  and the archive's own `FILE`/catalog tables already expose.
- The nested `messages → replies` shape is preserved, so a future need for pure chronological
  flattening (e.g. a different consumer that wants one flat array) must still do its own
  flattening using `seq`, rather than getting it for free — an accepted cost of keeping the shape
  reviewers already validated.
- Because v2 is additive, no `schema_version` value is retired; a consumer that branches on
  `schema_version` still needs a code path per version if it wants to be strict about it, though
  in practice a v1-only consumer can safely ignore the new fields without checking the version at
  all.
