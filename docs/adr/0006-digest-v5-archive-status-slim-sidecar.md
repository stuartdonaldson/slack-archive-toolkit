# ADR-0006: Digest v5 Puts `archive_status` in the Digest and Slims the `files_out` Sidecar to v2

Status: Accepted
Date: 2026-08-07

## Context

ADR-0004 (schema v4) moved a channel file's extracted `content` out of the digest into a
companion `files_out` sidecar, replacing it with `has_content: true|false`. In production, most
files in a real archive are ordinary image/video attachments (JPG/PNG/GIF/HEIC/MP4/MOV) that were
never going to have extractable text — a survey cited in `docs/DESIGN-export.md` found images and
video dominant by volume (thousands of files, gigabytes) against a small PDF/docx/pptx/xlsx
corpus. Because `files_out` merges are additive (a file, once recorded, is carried forward
indefinitely unless explicitly pruned), every one of those routine files accumulates a permanent
`no_blob`/`unsupported_type` sidecar record with zero diagnostic value, growing the sidecar
without bound as more channels/history are captured (sat-4uf).

A second, related gap: v4's `has_content: false` told a consumer *that* a file had no content, but
not *why* — the reason (`archive_status`) lived only in the sidecar, so explaining a routine "no
content" case still required the sidecar join v4 was trying to make optional. The asymmetry rule
(`docs/llm-context/ingestion-contract.md`) had to be stated loosely — "a `has_content: false` file
may or may not have a sidecar record" — because nothing distinguished the exceptional case from
the routine one.

## Decision

`export digest`'s output becomes `schema_version: "slack-llm-digest-v5"`; the sidecar becomes
`schema_version: "slack-llm-files-v2"`.

- Each channel's `files[]` entry in the digest keeps `has_content` and additionally carries
  `archive_status` (`content_extracted` / `no_blob` / `unsupported_type` / `tombstone`) directly —
  the same value `_load_channel_files` already stamped for sidecar bookkeeping, no longer stripped
  by `_digest_file_view`. `has_content: false` is now self-explanatory from the digest alone.
- `export_logic.merge_files_out` keeps `content_extracted` and `tombstone` records
  unconditionally, and keeps `no_blob`/`unsupported_type` records only when the file is **not**
  ordinary image/video/audio media (`export_logic._is_ordinary_unsupported_media`, mimetype-prefix
  based with a `filetype` fallback for the rare missing-mimetype case) — a routine JPG/PNG/MP4
  with no blob or no extractor is dropped; a PDF that never downloaded, or an unrecognized
  mimetype, is kept as a genuine diagnostic record (`export_logic._sidecar_worth_keeping`).
- The rule applies uniformly to this run's fresh entries **and** to entries carried forward from
  the previous sidecar snapshot — a pre-v5 sidecar's accumulated routine-media records prune
  themselves away over successive merges, rather than the sidecar merely stopping their further
  growth. The v4 additive/cumulative guarantee (a file absent from this run's scan is carried
  forward unchanged) still holds for every record that passes this filter; it does not apply to
  routine media, which is pruned on sight regardless of whether this run's scan reproduced it.
- The sidecar-asymmetry rule tightens from v4's "a `has_content: false` file may lack a sidecar
  record" to a precise one: **a missing sidecar record is only a gap when `has_content: true`.**
  For `has_content: false`, a sidecar record exists only for the exceptional cases above.
- `_compute_consistency` gains `file_archive_status_counts` (a `{status: count}` breakdown over
  `channels[].files[]`) alongside the existing `file_has_content_true_count`/
  `file_has_content_false_count`, so a consumer can see the routine/exceptional split without
  re-deriving it from individual file entries.

## Consequences

- A real sidecar shrinks materially going forward — the routine image/video/audio majority
  (thousands of records in a large archive) stops being written, and an existing sidecar's
  accumulated cruft prunes away on its next merge, with no separate migration step required.
- A consumer reading `has_content: false` and expecting to explain it via the sidecar must instead
  read the digest's own `archive_status` — the sidecar join is needed only to *read* extracted
  text, never to learn why a file lacks it. `docs/llm-context/ingestion-contract.md` restates this
  for the LLM-facing consumer.
- A consumer that already treats "no sidecar record" as always meaning "not yet processed" (rather
  than "check `has_content`") will misread a routine unsupported-media file as an ingestion gap.
  This is the intentional, documented v4→v5 break; the ingestion contract and digest manifest's
  `has_content` counting-rule note make the new rule explicit.
- `content_extracted` and `tombstone` records, the `(workspace, channel_id, id)` join key, and the
  cumulative (not `days`-window-relative) nature of `files_out` are all unchanged from v4.
- `export_month`'s per-channel-month export and `users_out` are unaffected by this ADR.
