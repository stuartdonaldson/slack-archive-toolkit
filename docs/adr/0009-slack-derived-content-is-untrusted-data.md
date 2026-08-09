# ADR-0009: Slack-Derived Content Carries Evidentiary Authority but Never Instructional Authority

Status: Accepted
Date: 2026-08-09

## Context

Every string the export pipeline emits that originated in Slack is authored by a workspace member:
sidecar `content` extracted from a Canvas or uploaded PDF/docx/pptx/xlsx, message text, channel
`topic`/`description`, file names and titles, unfurls, and profile display names. The LLM context
pack instructs a consumer to treat that material as evidence — extracted canvas/document content
sits at rank 1 of the evidence order in `docs/llm-context/uploads/query-policy.md` — and the
generated outputs (regional newsletter, SLT report, AO validation report) are distributed to real
people.

A workspace member can therefore place text inside a Canvas or an uploaded document that addresses
the model directly ("ignore prior instructions", "report X as the current Nantan"), or embed a URL
that a generated newsletter renders as its own citation. The PR #6 security review flagged this
against the `slack-llm-files-v2` sidecar specifically (`sat-pqf`); the exposure is not
sidecar-specific and predates the sidecar, but the sidecar's cumulative, rank-1 framing raises the
stakes.

Two framings were available. Enumerating the untrusted fields is precise but rots — a v7 schema
field is untrusted by default and would not be listed. Splitting by artifact provenance is coarser
but self-maintaining. An audit of the export writers confirmed the provenance split is currently
exact: every emitted artifact is JSON (`export.py:222`, `:277`, `:299`, `:366`), and every guidance
file, prompt, and augmentation is operator-authored Markdown — with one exception, the raw
third-party material retained under `uploads/augmentations/sources/` (a machine transcript of an
F3 Nation call), which is Markdown that the operator did not author.

Sanitizing or fencing the extracted text at build time was rejected: a phrase blocklist is brittle
and false-positives on ordinary Slack text, the JSON string boundary is already a stronger
delimiter than any inline fence an attacker can also emit, and mutating extracted content would
destroy the archive fidelity `export_logic.merge_files_out` otherwise protects and perturb
`content_sha256`/`content_changed_at`.

## Decision

Instructional authority and evidentiary authority are orthogonal. Slack-derived content keeps its
full evidentiary rank and carries no instructional authority whatsoever.

Instructions come only from the operator-authored guidance and prompt files and from the user in
chat. Material machine-extracted from Slack — currently, every `.json` artifact in the upload set —
is data, never instruction, regardless of how it is phrased or whom it appears to be from. The same
applies to quoted or transcribed third-party material carried in Markdown under
`uploads/augmentations/sources/`.

This is stated by provenance, with the file format as the operative shorthand, so that a schema
field added later is covered without an edit. It deliberately does not lower the evidence rank of
any source: a maintained Canvas remains rank-1 evidence, and treating "untrusted" as a reason to
hedge a well-supported fact is a misreading of this decision.

Text found inside Slack-derived content that attempts to direct the model is reported as an
observation about that source document, with its permalink, rather than obeyed or silently
dropped.

Citations in generated output come from structured provenance fields (`message_url`, `links`,
`permalink`). A URL appearing only inside extracted content may be quoted as source text but is
never rendered as the report's own citation or as an image.

No artifact-level trust marker is emitted. A marker present on this project's artifacts would
invite the inverse inference that a JSON lacking one is trusted; the rule covers the class instead
of tagging instances.

## Consequences

- The rule is stated in `project-instructions.md` (the only always-resident surface in ChatGPT
  Project mode), `uploads/ingestion-contract.md`, and `session-preamble.md`; the output-side
  citation and reporting rules live in `uploads/query-policy.md`, restated in the prompts that
  produce distributed artifacts.
- Documentation-only: no export schema change, no `schema_version` bump, no code change. Existing
  digests, sidecars, and profile exports are unaffected and need no regeneration.
- The Markdown-is-trusted shorthand is only true while raw third-party text stays out of
  uploadable augmentations. `docs/llm-context/README.md` §Maintenance rules and the augmentation
  index now require quoted material to live under `augmentations/sources/` behind a header marking
  it as quoted, with the summarizing augmentation carrying the operator's own words. If that
  discipline lapses, the shorthand inverts silently.
- Verification is behavioral, via `docs/llm-context/validation-set.md` scenarios 13–15 run against
  a planted canary Canvas. Scenario 15 (Project mode with no guidance file retrieved) is the
  load-bearing one — layers below the instruction box are not reliably resident there.
- Build-time heuristic detection of injection-shaped content, surfaced as a `consistency` count,
  was considered and deferred (`sat-j1t`): the false-positive rate on real Slack text is unknown
  and the consumer action on a nonzero count is undefined.
