# ADR-0005: Month-Sharded Spill for `export digest --split-by-month`

Status: Accepted
Date: 2026-08-07

## Context

ADR-0004 moved a digest's extracted file content out of `channels[]` into a companion `files_out`
sidecar, on the explicit condition that `f3-pugetsound`'s job (383 channels/7 workspaces — the job
that originally OOM-killed at ~2.3 GB RSS, sat-811) be re-run to confirm the fix before its deferred
Phase 2 (a month-sharded spill/streaming rewrite) was considered necessary.

Re-measured live on 2026-08-07 (`export digest --jobs jobs/f3-pugetsound.json`, `/usr/bin/time -v`):
the job **still OOM-killed**, at ~4.5 GB RSS — worse than the original 2.3 GB, not fixed. Two
contributing causes, found in order:

1. `_gather_digest_data`'s `files_out_sink` parameter (added by ADR-0004) accumulates every
   channel's raw file entries, content included, into one in-memory list for the whole job — the
   exact same whole-job accumulation the sidecar was meant to eliminate, just moved from
   `channels_meta` to a new sink. `messages` (the digest's message list) was never addressed either.
2. The actual proximate cause of this specific kill, found after the month-sharded spill (below)
   *still* died at the identical channel (`f3cascades/ao-stray-balls`, position 50/383, three runs
   in a row - v3 baseline, v4 sidecar, and the streaming rewrite): `_extract_file_content`'s fallback
   branch called `path.read_text()` on **every** file whose mimetype it has no dedicated extractor
   for - images, video, anything - before checking whether the mimetype was even text-shaped, and
   discarded the result anyway for a non-text/HTML-like type. That channel's archive holds a 503 MB
   `.MOV` plus a dozen multi-MB images; the video alone got fully decoded into one Python string per
   run, for nothing. This is a single-channel spike, not cross-channel accumulation - explaining why
   it reproduced at the exact same channel regardless of which whole-job accumulation was or wasn't
   fixed around it, and why the month-sharded spill alone did not clear it.

## Decision

Implement sat-811's originally-deferred Phase 2 for the `split_by_month` path specifically (the only
path with jobs large enough to be at risk):

- **`gather_and_shard_digest_data`** replaces whole-job accumulation with a spill: each channel's
  cleaned messages are partitioned by month (`partition_messages_by_month`, applied per channel) and
  appended to `<spill_dir>/months/<YYYY-MM>/<workspace>__<channel_id>.ndjson`; each channel's file
  entries (with content) are streamed to `<spill_dir>/files.ndjson`. Both are released from memory
  immediately after writing. Only `channels_meta` (bounded by channel count, already content-
  stripped per ADR-0004) and a `months_seen` set stay resident for the whole gather.
- **`write_monthly_digests`** assembles and writes one month's document at a time: `_load_month_
  messages` reads back just that month's shard files, then the existing, unmodified `_assemble_
  digest` builds the document exactly as `build_monthly_digests` did — same function, same output,
  only the memory shape of getting there differs. The month's slice and document are discarded
  before the next month starts.
- `merge_files_out` (unchanged) merges the sidecar from a generator reading `files.ndjson` one line
  at a time rather than an in-memory list — it never actually required a resident list.
- `--spill-dir`/`--resume` (also job fields `spill_dir`/`resume`) let an operator recover from an
  interrupted run without redoing already-sharded channels. A resumed channel contributes no fresh
  `files_out` entries; ADR-0004's existing "absent from this run's scan → carried forward unchanged"
  merge behavior covers it, rather than re-deriving canvas modification history (which needs a full
  reconvert `--resume` exists to avoid).

The non-`split_by_month` `build_digest` path is untouched — no current job both skips month-
splitting and spans enough channels to be at risk; it keeps its simpler whole-job-in-memory shape.

- **`_extract_file_content`** now checks the mimetype up front and returns `None` immediately for
  anything that isn't PDF/docx/pptx/xlsx/HTML-like/`text/*`, instead of reading the file's bytes
  first and discarding them after the fact. Behaviorally identical output (an unsupported mimetype
  already returned `None`) - purely a memory fix, verified by a test that makes `Path.read_text`
  raise if called at all for a `video/mp4` file, rather than provisioning an actual multi-hundred-MB
  fixture.

Two-pass `heapq.merge`-based streaming emit (the exact mechanism the original sat-811 design
sketched) was considered and not built: loading one month's shards into a list (`_load_month_
messages`) already bounds memory to O(one month) instead of O(whole job), which measurement shows is
sufficient, and reusing `_assemble_digest` unchanged carries far less correctness risk than
reimplementing its section builders (`_channels_for_slice`, `build_mentions_index`,
`_compute_consistency`, ...) against a streaming iterator.

## Consequences

- `export digest --jobs jobs/f3-pugetsound.json` completes without an out-of-memory kill: 383
  channels / 4,726 files / 6 monthly digests, peak RSS **164 MB** (`/usr/bin/time -v`, 2026-08-07) —
  down from 2.3 GB (v3 baseline), 4.5 GB (v4 sidecar, spill not yet applied), and 2.9 GB (spill
  applied, `_extract_file_content` bug not yet fixed), all against the same job/data.
- `write_monthly_digests` output is identical to `build_monthly_digests` (aside from `generated_at`)
  — proven on a 3-channel × 3-month fixture, not just asserted from the shared `_assemble_digest`
  call.
- A resumed run can silently miss a canvas's modification history recorded only in the interrupted
  attempt's own conversion pass, if that entry never made it into a prior sidecar snapshot either —
  narrow (only affects `--resume`, an operator recovery path, not the nightly default) and consistent
  with ADR-0004's existing carry-forward semantics rather than a new failure mode.
- `export_logic.py` gains a second, streaming code path (`gather_and_shard_digest_data`/`write_
  monthly_digests`) alongside the original in-memory one (`_gather_digest_data`/`build_monthly_
  digests`/`build_digest`) — accepted duplication, scoped to the one path (`split_by_month`) that
  needs it, rather than forcing every caller (including small single-workspace jobs) through spill
  machinery they don't need.
