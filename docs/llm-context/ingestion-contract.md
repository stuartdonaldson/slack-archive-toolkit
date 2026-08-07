# Ingestion contract

Canonical home for: upload validation, schema versions, sidecar pairing, timestamps, channel context fields, identity scope, and Canvas/file currency. This is a consumer-facing restatement of the export schemas — it never decides a schema fact. [docs/DESIGN-export.md](../DESIGN-export.md) is the schema authority; if this document and the design doc disagree, the design doc wins and this file needs a fix.

**Schema versions covered:** `slack-llm-digest-v4`, `slack-llm-files-v1`, `slack-user-profiles-v1`.

You have been given Slack digest/export data, Slack user profile data, a companion file-content sidecar, and optional regional or cultural context documents for F3 Puget Sound and related regional workspaces.

Ingest and organize the data for later analysis. Do not generate a newsletter, leadership report, event digest, or other substantive analysis until asked — see [Initial response](#initial-response).

## Files and schemas

The uploaded data may include:

* `slack-llm-digest-v4` files containing channel metadata, messages, threads, links, mentions, activity counts, and lightweight file references
* a `slack-llm-files-v1` sidecar containing extracted canvas and document content
* a `slack-user-profiles-v1` file containing workspace-local user profiles
* regional, organizational, or cultural reference documents

Treat these schemas as the authoritative structure. Do not assume fields or behavior from earlier digest versions.

## Core rules

Use only the uploaded files unless outside information is explicitly requested.

Preserve source context whenever possible:

* workspace or region
* channel name and channel ID
* Slack message URL
* timestamp in local Pacific time
* author display name or F3 name
* Slack user ID
* source type: message, thread reply, channel topic, channel purpose, channel description, canvas or file content, file metadata, profile, structured digest field, or inference

Report timestamps and event times in Pacific time.

Digest messages already contain Pacific-local timestamps in `posted_at_local`. Use that value directly. When useful, include the timezone abbreviation, such as PST or PDT.

File-sidecar lifecycle and modification timestamps may be stored in UTC. Convert them to `America/Los_Angeles` before presenting them.

When referencing a conversation, message, thread, channel, canvas, file, AO, or event, include the full clickable Slack link whenever one is available. If no direct link is available, say so.

Prefer F3 names or display names in output. Use legal names only when useful for identity resolution, administration, or a request that specifically needs them.

Do not treat profile titles or display names as definitive. They may be stale. Use them as working signals unless confirmed by stronger evidence — see [query-policy.md](query-policy.md) for the full evidence order.

Flag uncertainty instead of guessing.

## Channel context fields

Each channel entry carries three distinct text fields — do not collapse them or drop any that are present:

* `topic` — the channel's current Slack topic, verbatim
* `purpose` — the channel's current Slack purpose, verbatim
* `description` — a convenience merge (topic if set, otherwise purpose); it can omit real content, since a channel may have both a topic and a purpose set to different things (e.g. topic is logistical, purpose states the channel's actual charter)

Read `topic` and `purpose` independently rather than relying on `description` alone. Either may be null if never set in Slack.

When `topic` and `purpose` say conflicting things, treat `topic` as the higher-priority signal (it matches `description`'s own fallback order) but still report the `purpose` content rather than discarding it — a channel may deliberately carry a short operational `topic` alongside a longer standing `purpose` that states its actual charter, and both are legitimate evidence.

## Digest and file sidecar

Every `slack-llm-digest-v4` file must be used with its companion `slack-llm-files-v1` sidecar when one is provided.

The digest contains file metadata under each channel's `files` array. Extracted canvas and document text is stored only in the sidecar.

Join a digest file reference to the sidecar using the complete composite key:

`workspace + channel_id + id`

Do not join on file ID alone. The same Slack file or canvas may appear in more than one channel or workspace context.

Interpret file fields as follows:

* `has_content: true` — retrieve and use the matching sidecar record's `content`
* `has_content: false` — no text was ever extractable for this file, not that the sidecar is missing; inspect `archive_status` for why
* `content_sha256` — identifies the extracted-content version when present
* `archive_status` — explains why content is or is not available
* `modification_history` — records observed edit notices, but does not establish exactly what changed or who originally authored the document
* `modification_history_completeness` — consider this before describing an edit history as complete

`archive_status` is exactly one of:

* `content_extracted` — extracted content is available
* `unsupported_type` — file metadata is available, but text extraction is not supported for this file type
* `no_blob` — Slack metadata exists, but the underlying file was never captured to the archive
* `tombstone` — the file is deleted or unavailable in Slack

To connect a file to its source message, match the file's `message_ts` to the digest message's `ts` within the same workspace and channel — both are Slack's native `seconds.microseconds` timestamp string; no format conversion is needed.

### Sidecar asymmetry — cumulative, not run-matched

The `slack-llm-files-v1` sidecar is **cumulative across runs, not window-relative** to the accompanying digest. Each run merges into whatever already sits at the sidecar's path; entries from channels outside the current digest's window are deliberately retained rather than pruned. This produces an asymmetry in what counts as a gap:

* A digest file reference with `has_content: true` and **no matching sidecar record** is a gap. Report it explicitly.
* A sidecar record with **no matching current digest reference** is the expected steady state, not a problem. Report it as a count when useful, not as a warning.

Do not describe `has_content: false` as meaning that no content ever existed. It means text extraction was never able to capture content for this file — check `archive_status` for why.

## Identity rules

Treat Slack identities as workspace-local.

Use the digest's top-level mention index to unify accounts across workspaces only where the supplied evidence supports the merge.

Interpret mention confidence as follows:

* `high` — deterministic or strongly supported match
* `medium` — likely match supported by name evidence
* `unknown` — insufficient profile evidence
* `ambiguous` — potentially different people; do not merge

Trust `high` and `medium` identity merges supplied by the digest.

Never merge an `ambiguous` entry. Report its listed identities separately.

Do not merge people beyond what the mention index supports unless the uploaded evidence strongly and explicitly establishes the identity.

Use workspace-local `user_index` or the user profile file to resolve Slack user IDs.

A legal name, username, display name, or email hash may help establish identity, but name similarity alone is weak evidence.

## Evidence fields in digest messages

Treat message fields as evidence, not conclusions.

Important fields include:

* `unfurls` — Slack-provided link-preview or quoted-message context; use with the same standing as message text
* `links` — parsed URLs from message text; prefer these over reparsing raw text
* `mentions` — Slack user IDs mentioned in the message; resolve through workspace-local user data
* `seq` — chronological order within one channel; use only for ordering and never cite it to the user
* `user_index` — workspace-local users referenced in the digest slice
* top-level mention index — cross-workspace mention locations and supported identity mappings
* `in_scope: false` — a thread parent predates the export scope but has an included reply; do not count that parent as a new root message in the period
* `message_url` — use the exact stored URL when citing a Slack message

Do not infer an edit, deletion, role, identity, or event outcome merely because a field is absent.

## Canvas and file evidence

When a canvas or document is relevant:

1. Find its digest file reference.
2. Join it to the sidecar.
3. Use the sidecar `content` as the substantive source.
4. Preserve the workspace, channel, permalink, title, file ID, and modification information.
5. Check whether newer messages announce changes that supersede the document.
6. Do not treat an edit notice as proof of the document's specific new contents.

If a canvas appears in multiple channel contexts, preserve the relevant channel context rather than assuming one occurrence is canonical.

### Canvas/file currency ranking

A Canvas or file's own currency (whether its content reflects a recent edit or a stale one) is a *separate* question from the evidence order in [query-policy.md](query-policy.md). Use this ranking, best to worst, when deciding how current a Canvas or file's content is:

1. `modification_history[].at` (surfaced as `last_modified_at`) — a real edit event: Slack's own "X made updates to a canvas tab" notice, with the editor's name and a link back to that message via `message_ts`.
2. `content_changed_at` — the extracted text's own sha256 changed between two backup runs. This survives even if the edit notice above was deleted from the channel (see the asymmetry below).
3. `last_shared_ts` / a re-share of the file in a later message — evidence the document is still in active use, weaker than an actual content change.
4. `created_at` — Slack's original creation time. **For a Canvas this is a creation date, not a currency date** — a Canvas is edited in place, so an old `created_at` does not imply the content is stale.

**Critical asymmetry — do not invert this:** presence of a `modification_history` event is fully authoritative (trust it). Absence of one is **not** evidence the file was never edited — these notices are sometimes manually deleted by channel members because they clutter the channel for human readers. Every Canvas entry carries `modification_history_completeness: "partial"` unconditionally for this reason. If asked "which canvases are out of date," never answer from an empty or old `modification_history` alone — check `content_changed_at` too, and if both are uninformative, say the currency is unknown rather than assuming staleness.

## Activity and counting rules

Use structured activity counts from the digest rather than recounting messages manually.

Understand:

* `root_message_count` counts top-level messages in scope
* `reply_count` counts nested replies
* `total_message_count` is roots plus replies
* `participant_count` follows the digest's stated counting rules
* `activity_status` reflects the export scope
* removed canvas-update bot notices do not count as ordinary channel activity

Do not manually add removed canvas-update notices back into activity counts.

## Be ready to analyze

Prepare to answer questions about:

* included workspaces and regions
* channels, channel purposes, topics, descriptions, and activity
* users, F3 names, legal names when available, Slack IDs, mentions, and recent activity
* leadership roles such as Nantan, Weasel Shaker, 1st F, 2nd F, 3rd F, IT Q, Commz Q, Site Q, AO Q, Slack admin, website admin, bot admin, or F3 Nation admin
* current, former, interim, emeritus, and informal leadership
* activities within a channel, AO, region, or date range
* events, CSAUPs, convergences, 2.0 or family events, service events, and recurring programs
* AO and site details, including Site Q, schedule, location, launch status, OTB status, and notable changes
* IT, communications, helpdesk, website, Slack, bot, GitHub, and account-management questions
* canvases, files, documents, source links, and maintained references
* gaps, conflicting evidence, stale records, unclear ownership, and continuity risks

## Consistency and drift checks (interim, LLM-side)

`export digest` does not yet emit a deterministic consistency block; this section is the interim manual check until one exists (tracked separately from this pack). Run it during ingestion validation, before substantive analysis:

1. **Referential integrity within the upload:** digest file references resolve against the sidecar in both directions, applying the asymmetry above; each file's `message_ts` matches a real digest message `ts` in the same workspace/channel; message `mentions` resolve against `user_index`; `channel_id` values are unique per workspace; `in_scope: false` parents actually have an in-scope reply.
2. **Cross-source consistency:** a manual augmentation's roster names resolve to a profile in that workspace where expected; a region present in an augmentation but absent from the digest, or the reverse; a role an augmentation asserts that newer dated Slack evidence contradicts (apply the `Contested`/`Unresolved` handling in [query-policy.md](query-policy.md)); an augmentation's `collected:` date older than the digest's own date range.
3. **Drift versus a prior upload, when one is available for comparison:** sidecar match rate, extracted-content coverage, unresolved-mention count, and channels with neither `topic` nor `purpose`. A declining match rate across uploads means an input needs fixing, not that one answer needs hedging.

Report material findings from this check as part of [Initial ingestion validation](#initial-ingestion-validation), not buried inside a later substantive answer.

## Initial ingestion validation

Before substantive analysis, validate the uploaded set.

Confirm:

* files recognized and their schema versions
* digest months or date ranges
* workspaces or regions included
* user-profile file recognized
* cultural or regional context files recognized
* digest file-reference count
* matching sidecar record count
* records with extracted content
* records without extracted content
* unmatched digest references (gaps — see sidecar asymmetry above)
* unmatched sidecar records (expected steady state — report as a count, not a warning)
* obvious schema, timestamp, or pairing problems
* the consistency and drift findings above

If a digest is present without its sidecar, state that canvas and document contents may be unavailable.

If a sidecar is present without a matching digest, state that the file content lacks complete message and channel context.

## Initial response

After ingestion, respond only with:

1. Files recognized
2. Workspaces or regions included
3. Major categories ready for analysis
4. Sidecar pairing and validation status
5. Obvious gaps or limitations

Keep the initial response brief.

Do not generate a newsletter, event digest, leadership report, or other substantive analysis until asked.
