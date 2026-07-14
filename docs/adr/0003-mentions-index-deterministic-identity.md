# ADR-0003: Digest Carries a Cross-Workspace Mention Index Built on Deterministic Identity Evidence Only

Status: Accepted
Date: 2026-07-13

## Context

Slack user ids are workspace-local, while F3 names are intended to identify the same PAX across
regional workspaces. Answering "where is this PAX mentioned, first/last mention, which channels
and workspaces" previously required the downstream LLM to walk every message's `mentions[]` and
merge identities itself — ADR-0001 deliberately left *all* cross-workspace identity merging to
the LLM, and `docs/slack-ingestion.md` instructed it to treat identities as workspace-local.

In practice a useful subset of that merging is deterministic, not semantic: two accounts with the
same email address are the same person; "Pure LEAD" in one workspace and "Pure" in another with
the same real name are the same person. Leaving mechanical joins to the LLM costs accuracy and
tokens without adding judgment. Three approaches were considered:

- **Keep all merging LLM-side** (status quo per ADR-0001) — rejected: mention-tracking questions
  are common in the newsletter use case, and re-deriving the same deterministic joins in every
  prompt is wasteful and error-prone.
- **Full precomputed per-PAX reports** (counts, first/last dates, URLs materialized per user) —
  rejected: duplicates message data, bloats the digest, and freezes report shapes the consumer
  might not want.
- **Compact inverted index on deterministic evidence** *(chosen)* — a top-level `mentions` key
  in the digest, keyed by canonical F3 name, storing only message `ts` grouped
  workspace → channel. Counts, first/last dates, and Slack URLs are derived downstream from
  `ts` + `channel_id` + workspace. Accounts unify only on deterministic evidence: matching
  `email_hash`, or normalized-F3-name match (case/space/punctuation/hyphen variants fold) with
  real-name or username support; a bare name match merges at `medium` confidence. Same name with
  conflicting evidence (both email hashes present and differing AND both real names present and
  differing) is never merged — one key, `match_confidence: "ambiguous"`, unmerged `identities[]`.

Emails are evidence but must not be disclosed: `_clean_user` has always stripped `profile.email`
from every exported document. Matching therefore uses `email_hash` — a truncated SHA-256 of the
lowercased address — as the only persisted email-derived value.

## Decision

The v3 digest gains a top-level `mentions` index keyed by canonical F3 name (the f3 handler's
`possible_f3_name` when available, else display name), listing per entry the raw `aliases`,
workspace-local `accounts` pairs, a `match_confidence` (`high` / `medium` / `unknown` /
`ambiguous`), and `workspaces → channels → message_ts` locations. Identity unification uses
deterministic evidence only (email hash; normalized name plus supporting real-name/username
match); conflicting evidence is flagged, never merged. This narrows ADR-0001's "all identity
merging is LLM-side" boundary: *deterministic* merging moves into the builder, and every
non-deterministic judgment — including every entry flagged `ambiguous` — remains with the LLM.

## Consequences

- Mention questions (where/when/how often a PAX is mentioned, with citations) become index
  lookups plus URL derivation instead of a full-digest scan and ad-hoc identity merging.
- Message ids stay workspace-local and message bodies/URLs are never duplicated into the index,
  so the index stays small relative to `messages` and cannot drift from it.
- `build_user_profiles` output gains `email_hash` on every profile — a one-way, truncated digest;
  the raw address remains unpersisted everywhere. A consumer of the users file sees one more
  field it can ignore.
- `docs/slack-ingestion.md`'s identity guidance changes: the LLM should trust `high`/`medium`
  merges from the index, and must treat `ambiguous` entries as unresolved rather than merging
  them itself.
- ADR-0001 is not superseded — its additive-evidence decision and the nested message shape stand;
  only its "all merging is LLM-side" allocation is narrowed, and only for evidence that is
  deterministic by construction.
- Mention completeness for bot-posted Block Kit backblasts depends on extraction also reading
  `blocks[].text.text` (the *PAX*: line lives there, not in the fallback `text`) — fixed
  alongside this index; without it the index would silently miss the most common backblast form.
