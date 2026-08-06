# ADR-0004: Digest v4 Moves Extracted File Content to a Companion `files_out` Sidecar

Status: Accepted
Date: 2026-08-06

## Context

`f3-pugetsound`'s nightly digest job (383 channels / 7 workspaces) was OOM-killed mid-run
(sat-811): the Linux OOM-killer SIGKILLed the process at ~2.3 GB RSS, at channel 50/383, with
`export digest --jobs jobs/f3-pugetsound.json` reproducing the death live. `_gather_digest_data`
accumulates every channel's `channels_meta` (including each file's extracted `content`) and every
channel's messages into one in-memory structure for the whole job before anything is written to
disk.

Measured against a real `slack-llm-digest-v3` output (f3-nation, 52 channels/1 workspace/1
month): `channels[]` was 5.74 MB of an 8.44 MB document, and `files[].content` alone was 4.61
MB — 55% of the whole document. Two properties made this the dominant, not merely a large, term:

- It is **month-invariant**: `build_monthly_digests` writes the identical `files[].content`
  payload into every monthly file, since a file has no natural month
  (`_referenced_ids_for_slice` already documents this "files have no natural month" wart). Four
  months of f3-nation duplicates it 4x.
- It is held **resident for the whole job**, not released per channel, because
  `_gather_digest_data` builds the full `channels_meta` list up front before any assembly pass
  runs.

Scaling f3-nation's numbers to f3-pugetsound's 383 channels and applying typical Python-object
overhead over compact JSON, `channels_meta`'s file content plausibly accounts for ~1 GB+ resident
before the message list is even considered — consistent with the observed 2.3 GB RSS kill.

Investigating this file content also surfaced a separate, related bug: Slack's own
`tabbed_canvas_updated` system messages ("X made updates to a canvas tab") were landing in
`messages[]` and being counted as root messages/participants for the `USLACKBOT` account, and
they carry exactly the Canvas edit-history data sat-2s9 needed (see Consequences).

Two fix shapes were considered:

- **Full month-sharded spill/streaming rewrite** (invert `_gather_digest_data`'s pipeline to spill
  each channel's messages to disk per month, then stream-assemble each month from the spill) —
  the structurally complete fix, but a large rewrite of the gather/assemble pipeline with its own
  correctness risk (byte-identical output vs. today, resumability, fd limits on the merge). Not
  chosen for this increment.
- **Move `content` out of the digest into a separate sidecar document** *(chosen)* — the single
  largest resident/duplicated structure disappears from the job with a schema change, not a
  pipeline rewrite, and is independently useful to the digest's LLM consumer regardless of the OOM
  (the sidecar can be cumulative rather than re-derived and duplicated every run).

## Decision

`export digest`'s output becomes `schema_version: "slack-llm-digest-v4"`:

- Each channel's `files[]` entry keeps every v3 field **except** `content`, and gains
  `has_content: true|false`. The extracted text moves to a companion **`files_out`** sidecar
  document (`schema_version: "slack-llm-files-v1"`), written per job (`export_logic.
  build_digest`/`build_monthly_digests(..., files_out_sink=...)`  →  `export._write_files_out` 
→ `export_logic.merge_files_out`), joined by `(workspace, channel_id, id)`. Unlike the digest,
  `files_out` is cumulative across runs (merged with whatever already exists at that path), not
  bounded by the digest's `--days` window — matching `_load_channel_files`'s existing behavior of
  reading the whole archive's `FILE` table every run regardless of `days`.
- `files_out` carries change-detection fields per file: `content_sha256`, `archive_status`
  (`content_extracted`/`no_blob`/`unsupported_type`/`tombstone`), `blob_captured_at`,
  `first_seen_at` (stamped once, carried forward), and `content_changed_at` (re-stamped only when
  `content_sha256` actually differs from the previous snapshot).
- `tabbed_canvas_updated` system messages are parsed for their Canvas edit history (editor
  display name, resolved to a user id only on an unambiguous roster match; timestamp; target
  `file_id`), attached to the sidecar's matching file as `modification_history` plus a derived
  `last_modified_at`, and then **stripped from `messages[]`** entirely — fixing the
  `USLACKBOT`-inflates-counts bug as a side effect of removing noise that carried no useful text
  anyway.

The month-sharded spill/streaming rewrite remains the design's Phase 2 (deferred) — see
`docs/DESIGN-export.md` §Known Gaps & Recommendations.

## Consequences

- The digest's single largest resident/duplicated structure is gone; `f3-pugetsound`'s job must
  be re-run to confirm this alone clears the OOM (sat-811 acceptance criterion) before Phase 2 is
  considered necessary.
- `f3-nation`'s v4 output differs from v3 only by `schema_version`, the new manifest entry,
  `files[].content` removal/`has_content` addition, and a small, expected drop in
  `root_message_count`/`participant_count` on channels that had a `tabbed_canvas_updated` notice
  (a correctness fix, not a regression) — messages/mentions/user_index/workspace_activity_index
  are otherwise unchanged.
- A consumer reading `files[].content` directly breaks against v4 output — an intentional,
  documented break (`docs/slack-ingestion.md` updated accordingly). A consumer that never uploads
  the `files_out` sidecar simply loses file text entirely (`has_content` still tells it this is
  the case, rather than silently vanishing).
- This directly narrows sat-2s9 ("canvas edits after first capture are invisible"): canvas
  content is independently detectable as changed via `content_changed_at`, and, when Slack's edit
  notice survives (it is sometimes manually deleted by channel members — presence is
  authoritative, absence proves nothing, hence `modification_history_completeness: "partial"`
  unconditionally on every Canvas entry), via `modification_history`. Proactively re-fetching
  Canvas blobs or reading Slack's own file `updated` field (sat-2s9's other investigated options)
  remain open, separate follow-ups if still wanted — not required to close sat-2s9, since
  detection (not re-fetching) was the agreed scope.
- `export_month`'s per-channel-month export and `users_out` are unaffected by this ADR.
