# ADR-0008: LLM Context Pack Splits Schema/Policy/Domain/Prompts/Augmentations, with Conditional-Rank Augmentation Evidence

Status: Accepted
Date: 2026-08-08

## Context

Guidance for answering questions from Slack-derived F3 data lived in hand-maintained documents
(`docs/slack-ingestion.md`, `docs/report-queries.md`, `docs/f3-culture.md`, plus ad hoc prompt and
augmentation files) with duplicated evidence-precedence rules, no fixed home for one-off task
prompts, and no structured way to bring in dated facts the Slack export cannot express (e.g. an
F3-Nation regional admin roster). A migration plan (`sat-ejk`, formerly
`docs/llm-context/MIGRATION-PLAN.md`) proposed and then validated a replacement structure; a review
(formerly `docs/llm-context/REVIEW-2026-08-06.md`) found the plan's structure sound but flagged
several gaps before it was safe to build. Both documents, and the validation record (formerly
`docs/llm-context/VALIDATION-RESULTS.md`), are retired by this ADR — the decision they converged on
is recorded here; the documents themselves are superseded by the pack they specified and are
recoverable from git history if the reasoning trail is needed.

## Decision

Context material is decomposed by how it changes, under `docs/llm-context/`:

- `uploads/ingestion-contract.md` — schema, pairing, identity, timestamp, and initial-upload rules.
  Derived from and never authoritative over `docs/DESIGN-export.md`; a digest/profile/sidecar
  schema change requires updating both (`CLAUDE.md` §Design Documents).
- `uploads/query-policy.md` — the sole canonical home for evidence precedence, confidence
  vocabulary, authority boundaries, and report formats.
- `uploads/f3-domain-context.md` — culture and vocabulary, background only, with attributed source
  notes kept separate from generalized guidance.
- `uploads/supplemental/` — dated, hand-maintained facts the Slack export cannot express. Stable
  filenames (not dated filenames), with a required header block (`collected:`, `source:`,
  `collected_by:`, `fidelity:`, `coverage:`, `known_gaps:`, `refresh_trigger:`, `refresh_owner:`)
  so currency is a lookup, not a judgment call. A recurring source (e.g. a periodic call) uses one
  cumulative file with one header block per entry rather than overwriting.
- `prompts/` — specialized, paste-ready task prompts (newsletter, FNG guidance), kept out of the
  general query policy.
- `project-instructions.md` / `session-preamble.md` — the two deployment-mode surfaces. Project
  instructions carry every invariant that must apply to *every* answer (schema names, the sidecar
  join key, the sidecar asymmetry, identity/ambiguous-merge rules, the evidence order, the
  augmentation rule, authority non-equivalence) because ChatGPT Project knowledge is retrieved on
  demand, not guaranteed resident — a rule living only in a knowledge file applies only when the
  retriever happens to surface it. The session preamble is deliberately thin: everything is already
  in context for a one-off upload.

Evidence precedence keeps the existing 8-rank order unchanged (canvas/file content > channel
topic/purpose > role-holder announcement > structured digest fields > message/thread evidence >
file metadata without content > profile title > inference) rather than silently collapsing or
dropping ranks. A dated augmentation is added as a **conditional** rank, not a fixed one:

- Primary source when the Slack export structurally cannot express the fact.
- Otherwise ranks immediately below message/thread evidence (rank 5), with conflicts resolved by
  comparing dates, not just ranks — the more recent source is the working answer, the losing source
  and both dates are reported alongside it.

A `Contested` confidence label is added (sources materially disagree; the stated answer is the
stronger/more recent one, with the conflict shown) distinct from `Unresolved` (no answer
supportable). Augmentation `fidelity` (`system-extracted` / `hand-compiled` / `recalled`) caps the
confidence an augmentation can support and how a conflict with dated Slack evidence resolves.

## Consequences

- Both deployment modes were validated by construction against a representative evidence set
  (`sat-ejk.3`); two residency gaps surfaced (`archive_status` semantics and the
  `Vacant`/`Not identified` distinction missing from `project-instructions.md`) and were closed
  (`sat-6em`, `sat-8t3`). A live upload-and-ask run through an actual ChatGPT session/Project was
  never performed and remains open, tracked separately (`sat-dul`, filed alongside this ADR).
- Legacy flat documents (`docs/slack-ingestion.md`, `docs/report-queries.md`, `docs/f3-culture.md`,
  the two prompt docs, and the hand-maintained F3-Nation infrastructure augmentation) were retired
  once their canonical replacements were verified (`sat-ejk.5`); recoverable via
  `git log --follow -- <path>`.
- A pack-wide augmentation size budget and a refresh cadence/owner policy were deliberately left
  undecided pending real growth experience; each augmentation's own `refresh_trigger:`/
  `refresh_owner:` header fields are the interim freshness signal. Tracked separately
  (`sat-cvs`, filed alongside this ADR) rather than reopening this decision.
- Deterministic referential-integrity and cross-run drift checking was pushed into `export digest`
  as an emitted `consistency` block (`sat-ejk.6`) rather than left to ad hoc LLM-side arithmetic;
  the pack's job is to read and report that block plus the cross-source semantic judgments code has
  no basis to make.

## Addendum (2026-08-19)

`uploads/augmentations/` was renamed to `uploads/supplemental/` (and its index file
`f3-augmentation-index.md` to `f3-supplemental-index.md`) — terminology only, not a decision
change. "Supplemental" was chosen over the alternative "enrichment" as plainer English with no
data-engineering/ML jargon collision. Every path reference across this pack was updated to match;
the general English term "augmentation" (a dated manual fact supplementing the Slack record)
remains in prose where it refers to the concept, not the directory.
