# LLM context pack migration plan

## Status

**Phase 5 complete; post-migration alignment in progress.** This plan adopts the 2026-08-06 review decisions. The canonical context files exist under `docs/llm-context/` ([sat-ejk.2](#migration-tracking)), copied from the legacy sources with transitional headers added. The pack was validated ([sat-ejk.3](#migration-tracking); see `VALIDATION-RESULTS.md` — 10/12 scenarios pass, two remediation issues filed rather than editing the pack ad hoc) and integrated ([sat-ejk.4](#migration-tracking)): the nightly copy workflow (`scripts/nightly-backup-digest.sh`), `README.md`, and `docs/OPERATIONS.md` reference the canonical pack, and `CLAUDE.md` carries the schema placement rule below. Legacy sources have now been retired ([sat-ejk.5](#migration-tracking); see Phase 5 below) — each is removed from the working tree and recoverable only from git history. [sat-ejk.7](#migration-tracking) aligns the guidance with periodically refreshed run artifacts held as Project knowledge.

## Decision

Create a Markdown-first context pack for shared ChatGPT sessions and ChatGPT Projects. It separates:

1. the Slack export and ingestion contract;
2. the query and reporting policy;
3. F3 vocabulary, cultural background, and style guidance;
4. task-specific prompts; and
5. optional, dated supplemental augmentations.

Hand-maintained supplemental facts belong in Markdown, not hand-authored JSON. Markdown tables are reviewable, editable, citeable, and can retain the facts with their source date, scope, limitations, and refresh guidance. JSON remains appropriate for generated or automated-consumer artifacts, including the Slack digest, user-profile export, and `slack-llm-files-v1` sidecar. If an automated consumer later needs an augmentation in JSON, generate it from reviewed Markdown rather than maintaining two hand-edited sources.

## Goals

- Give an LLM clear, non-duplicated guidance for ingestion, evidence evaluation, reporting, F3 context, and task prompts.
- Support both one-off sessions and ChatGPT Projects without assuming they retain or retrieve files in the same way.
- Make source authority, date, and uncertainty visible when using manually collected facts.
- Preserve existing documents and workflows until their replacements are validated and integrated.
- Provide a repeatable validation set and a clear retirement path for legacy documents.

## Non-goals

- Replace generated digest, profile, or file-sidecar data with prose.
- Treat a manually collected augmentation as automatically more current than maintained Slack evidence.
- Implement the migration in this planning increment.
- Fold historical design-feedback documents into the runtime context pack. In particular, `docs/llm-export-suggestion.md`, `docs/llm-digest2-idea.md`, and `docs/llm-leadership-improvement.md` remain historical design inputs.

## Target layout

```text
docs/llm-context/
├── README.md                         # Operator-facing assembly and maintenance guide
├── MIGRATION-PLAN.md                 # This planning record
├── project-instructions.md           # Paste-ready ChatGPT Project instructions
├── session-preamble.md               # First-message instruction for a one-off session
├── ingestion-contract.md             # Derived consumer-facing export contract
├── query-policy.md                   # Canonical evidence and reporting rules
├── f3-domain-context.md              # Culture, vocabulary, and writing posture
├── validation-set.md                 # Re-runnable golden-question scenarios
├── prompts/
│   ├── initial-intake.md
│   ├── regional-slt.md
│   ├── ao-directory.md
│   ├── authority-routing.md
│   ├── newsletter.md
│   └── fng-getting-started.md
└── augmentations/
    ├── README.md                     # Current-supplement index
    ├── f3-nation-operations.md
    ├── f3-nation-admins.md
    └── archive/                      # Optional superseded snapshots
```

| Target file | Canonical responsibility | Derived from | Maintenance rule |
| --- | --- | --- | --- |
| `ingestion-contract.md` | Upload validation, schema versions, sidecar pairing, timestamps, channel fields, identity scope, Canvas/file currency, and the brief initial-ingestion response. | `docs/slack-ingestion.md` | Derived from the schema authority; update when digest/profile/sidecar schemas change. |
| `query-policy.md` | Evidence precedence, conflict resolution, confidence labels, authority boundaries, question routing, and standard report tables. | `docs/report-queries.md` plus policy fragments in `docs/slack-ingestion.md` | The only canonical home for general evidence and reporting rules. |
| `f3-domain-context.md` | F3 culture, vocabulary, 3 Fs, writing posture, and attributed source notes. | `docs/f3-culture.md` | Cultural guidance is background, not proof of current facts. Keep known provenance attributed. |
| `project-instructions.md` | Invariants that must be resident in the ChatGPT Project instruction box. | New, distilled from the contract and policy. | Must remain within the applicable platform character limit; verify the limit during implementation. |
| `session-preamble.md` | Thin first message for a one-off session, directing the LLM to read the uploaded contract and policy before substantive analysis. | New. | Do not duplicate detail already reliably available in the one-off upload set. |
| `prompts/*.md` | Paste-ready prompts for intake, reports, authority routing, newsletter generation, and FNG guidance. | New prompts plus `docs/newsletter-prompt.md` and `docs/fng-getting-started-prompt.md`. | Keep task-specific output requirements out of the general policy. |
| `validation-set.md` | Golden questions with expected evidence type, confidence treatment, and behavior—not fixed factual answers. | Current failure modes and review findings. | Re-run after relevant schema or policy changes. |
| `augmentations/f3-nation-operations.md` | Dated F3-Nation capabilities, role distinctions, ownership routing, and diagnostic guidance unavailable in ordinary exports. | `docs/f3-it-infrastructure-augmentation-2026-06-30.md` | Apply the recommended augmentation metadata during this migration. |
| `augmentations/f3-nation-admins.md` | Manually maintained regional F3-Nation administrator roster and limitations. | The existing infrastructure companion Markdown/JSON data. | Markdown is authoritative; retain or generate JSON only for a demonstrated automated consumer. |
| `augmentations/README.md` | Indexes the active augmentations and any archived superseded snapshots. | New. | Identifies the current source without relying on a date in the filename. |

## Deployment modes and upload guidance

### One-off session

Upload the current context files and run artifacts together. Start with `session-preamble.md`; it directs the LLM to read the ingestion contract and query policy before analysis. A later chat message or uploaded replacement file may supersede an earlier uploaded knowledge file when the conversation explicitly establishes that precedence.

### ChatGPT Project

Use `project-instructions.md` as the paste-ready invariant instruction set. It must contain every rule that cannot rely on knowledge-file retrieval, including identity boundaries, source/link requirements, time-zone rules, evidence precedence, authority non-equivalence, sidecar asymmetry, and augmentation conflict handling.

Any context file or run artifact may be a Project knowledge file when that is appropriate for the Project. Project instructions must identify the `as_of` date for any resident run data and must state how newer uploaded or chat-provided material supersedes it. Do not assume Project knowledge retrieval makes a detailed rule available for every answer.

### Nightly/operator copy

During integration, replace the current per-file nightly list with a deliberate context-pack directory copy or a curated deployment subtree. The implementation must avoid copying planning records, review notes, or archived snapshots into the runtime upload area.

## Schema and sidecar authority

[docs/DESIGN-export.md](../DESIGN-export.md) is the schema authority for digest, profile, and sidecar behavior. `ingestion-contract.md` is a consumer-facing restatement and never the place where a schema fact is decided. It must visibly identify the schema versions it covers.

The file sidecar is cumulative rather than run-window-matched:

- A digest file reference with `has_content: true` but no matching sidecar record is a gap.
- A sidecar record with no current digest reference is expected in the steady state. Report it as a count when useful, not as a warning.
- Use `workspace + channel_id + id` as the file join key.
- Use `archive_status` to explain why extracted text is absent; do not equate `has_content: false` with a claim that the source had no content.

## Evidence and conflict policy

`query-policy.md` retains the current eight-rank Slack evidence order unchanged:

1. Current extracted content of a maintained canvas or document from the matching sidecar
2. Current channel topic or purpose
3. Direct announcement from the responsible person, organizer, role holder, or system owner
4. Structured digest fields
5. Message text or thread replies
6. File metadata without extracted content
7. User profile title or display name
8. Inference or name similarity

A dated augmentation is conditional evidence:

- It is the primary source when the Slack exports structurally cannot express the fact, such as the F3-Nation regional administrator roster.
- When the Slack exports can express the same fact, treat it immediately below message/thread evidence and apply recency and source strength rather than silently overriding the Slack record.
- Never present augmentation-derived facts without their collection date.
- When materially conflicting sources still permit a working answer, use `Contested`: state the selected answer, the conflicting source, and both dates. Use `Unresolved` when the conflict cannot support an answer.

Augmentation `fidelity` is recommended guidance, not a permanently mandatory schema. During this migration, apply it to the migrated augmentations:

| Suggested value | Meaning | Maximum ordinary confidence |
| --- | --- | --- |
| `system-extracted` | Transcribed directly from a system screen or maintained system record. | `High` for its collection date. |
| `hand-compiled` | Assembled manually from several sources. | `Medium`. |
| `recalled` | Based on memory or an informal report. | `Working signal`. |

On a conflict with dated Slack evidence, report the conflict and apply `Contested` or `Unresolved` as appropriate. Future augmentation structure, including metadata fields, is recommended rather than required; each future augmentation should choose the level of metadata appropriate to its source and risk.

## Migration phases

### Phase 1 — Plan and tracking

Complete this plan revision, record the approved structure, and track the work in the epic with dependent children. No context-pack implementation occurs in this phase.

**Exit criteria:** The plan, evidence rules, deployment modes, and tracking structure are approved.

### Phase 2 — Create canonical context files

Create the target files by **copying**, not moving, the necessary legacy content. Add a short transitional header to each legacy source naming its future canonical home and directing contributors not to edit the legacy copy. Keep legacy files complete while the existing nightly workflow still copies them.

When porting cultural guidance, preserve known source attribution. Either express F3-general guidance as clearly generalized background or retain the supporting Slack material in a labeled source-notes section; do not present an attributed regional leadership post as timeless organizational doctrine.

Create the validation set and the augmentation index. Use stable augmentation paths with dated metadata inside the file; archive superseded snapshots only when history is useful.

**Exit criteria:** Every rule has one canonical target home, legacy documents remain operational, and no existing copy workflow has been changed.

### Phase 3 — Validate the pack

Run `validation-set.md` against a matched digest, profile export, cumulative sidecar, and applicable augmentations. Include scenarios for administrator-role separation, ambiguous identity entries, Canvas currency with empty modification history, conflicting topic/purpose, missing extracted content, and a dated augmentation conflict.

**Exit criteria:** The validation set passes or creates recorded remediation work. Validation confirms source links, authority separation, confidence handling, sidecar asymmetry, and both deployment modes.

### Phase 4 — Integrate deployment

Update the documentation index, nightly context-copy workflow, and operator guidance to use the canonical pack. Establish the bounded runtime-copy layout. Add the approved schema placement rule to [CLAUDE.md](../../CLAUDE.md): digest/profile/sidecar schema change requires updates to [docs/DESIGN-export.md](../DESIGN-export.md) and `docs/llm-context/ingestion-contract.md`.

**Exit criteria:** Active session and Project instructions use the pack; runtime copy behavior excludes planning and archival material; legacy sources remain available. **Met:** `scripts/nightly-backup-digest.sh` now copies a curated `~/slack-exports/llm-context/` subtree (contract, policy, domain context, both deployment-instruction files, prompts, active augmentations — excluding `README.md`, this plan, review notes, `VALIDATION-RESULTS.md`, `validation-set.md`, `augmentations/README.md`, and `augmentations/archive/`) alongside the unchanged legacy per-file copy; `README.md` §7–8 and its documentation table, and `docs/OPERATIONS.md`'s nightly step table, point at the canonical pack; `CLAUDE.md` carries the digest/profile/sidecar → `ingestion-contract.md` schema placement rule.

### Phase 5 — Retire legacy documents

Only after Phase 3 validation and Phase 4 integration are complete, redirect, archive, or remove legacy files. Do not retire a file while it is referenced by automation or contains material not present in the canonical pack.

**Complete (`sat-ejk.5`, 2026-08-07).** Each condition below was re-verified before removal: every legacy file still carried its Phase 2 transitional header claiming completeness; `scripts/nightly-backup-digest.sh` was the only automation reference (it copied the legacy files into `~/slack-exports/` alongside the canonical pack) and has been updated to drop that copy step; `README.md` (newsletter/FNG sections and the documentation table) and `docs/OPERATIONS.md` (nightly step 0) referenced the legacy paths directly and have been repointed at the canonical pack only; `docs/llm-context/README.md`'s source-curation table now records the retirement instead of describing an in-progress copy. `docs/f3-it-infrastructure-augmentation-2026-06-30.json` had no automated consumer (`grep` across `*.py`/`*.sh` found none) and the Markdown roster (`augmentations/f3-nation-admins.md`) is authoritative, so it was removed outright rather than redirected. Historical mentions of the legacy paths in ADRs, `CHANGELOG.md`, and `work-log.md` were left as-is — those are immutable historical records of past sessions, not live references, and per `doc-standard.md` an ADR is not edited after acceptance. All seven legacy files were deleted (not archived): each is fully superseded by a canonical file with no content gap, and git history preserves the pre-retirement text if it is ever needed (`git log --follow -- <path>`).

| Legacy item | Disposition | Condition verified before removal |
| --- | --- | --- |
| `docs/slack-ingestion.md` | Removed; replaced by `ingestion-contract.md` | Schema and initial-ingestion guidance fully migrated; all references redirected. |
| `docs/report-queries.md` | Removed; replaced by `query-policy.md` | Reporting rules and table templates fully migrated; all references redirected. |
| `docs/f3-culture.md` | Removed; replaced by `f3-domain-context.md` | Cultural framing, terminology, attributed source notes, and style guidance fully migrated. |
| `docs/newsletter-prompt.md` | Removed; replaced by `prompts/newsletter.md` | Prompt fully migrated and runtime copy workflow redirected. |
| `docs/fng-getting-started-prompt.md` | Removed; replaced by `prompts/fng-getting-started.md` | Prompt fully migrated and runtime copy workflow redirected. |
| `docs/f3-it-infrastructure-augmentation-2026-06-30.md` | Removed; split into `augmentations/f3-nation-operations.md` and `augmentations/f3-nation-admins.md` | Operations guidance and roster metadata/table fully migrated and reviewed. |
| `docs/f3-it-infrastructure-augmentation-2026-06-30.json` | Removed as a hand-maintained source | Verified no automated consumer; Markdown roster is authoritative. |

## Consistency and drift follow-up

The context pack will describe an interim LLM-side consistency review, but deterministic work belongs in the export pipeline. Track the following separately from document migration:

- referential integrity within the upload: file joins, `message_ts`, mentions, profiles, channel IDs, and in-scope thread relationships;
- cross-source consistency: augmentation freshness, regions, identities, and contested role claims; and
- cross-run drift: sidecar-match and extracted-content coverage, unresolved identities, and channel metadata coverage.

The deterministic integrity and drift half should be emitted by `export digest` as a consistency block. The LLM pack should interpret and report that block rather than recreate arithmetic or joins ad hoc.

## Open operating decisions

`docs/llm-context/augmentations/` is the general place and pattern for dated,
hand-maintained facts relevant to regional F3 inquiries that come from
sources outside the Slack export. It is expected to grow on an ongoing basis
as more such material is identified — not a fixed set closed at migration
time. Most augmentations are a single current snapshot, re-collected in
place; a source that recurs (a periodic call, a periodic report) instead
gets a cumulative file that appends a new dated entry per occurrence without
overwriting earlier ones — see `augmentations/README.md` for both patterns.
Some future augmentations may eventually be generated from an automated
source rather than hand-compiled, but that is out of scope for now; every
augmentation today is hand-maintained Markdown per the Decision above.

**Resolved:** the untracked State of the Nation transcript is now in the
repository as a cumulative augmentation (`sat-oxl`): `augmentations/sotn-transcripts.md`
holds the dated per-call summary and header block, `augmentations/sources/`
holds the raw transcript. New SOTN calls get a new dated entry appended, per
that file's own maintenance section — not a new open decision each time.

**Still open:** no fixed context-pack size budget, augmentation refresh
cadence, or refresh owner has been selected as a general policy. This needs
more information before it can be decided — in particular, real experience
with how large and how fast the augmentation set grows now that new
augmentations (SOTN calls and others as they're discovered) are expected on
an ongoing basis, rather than a one-time migration snapshot. Until decided,
each augmentation's own `refresh_trigger:`/`refresh_owner:` fields and known
gaps remain the practical freshness signal, not a pack-wide policy.

## Migration tracking

| Bead | Scope | Status / dependency |
| --- | --- | --- |
| `sat-ejk` | Parent epic: migrate LLM context pack | Open |
| `sat-ejk.1` | Revise this migration plan from review decisions | Closed; Phase 1 |
| `sat-ejk.2` | Create canonical context files | Closed; Phase 2 |
| `sat-ejk.3` | Validate the context pack | Closed; depends on `sat-ejk.2` |
| `sat-ejk.4` | Integrate canonical pack into workflows | In progress; depends on `sat-ejk.3`; Phase 4 |
| `sat-ejk.5` | Retire legacy context documents | Closed; depends on `sat-ejk.4`; Phase 5 |
| `sat-ejk.6` | Emit deterministic digest consistency metrics | Open; related export-pipeline work, not a prerequisite for the planning revision |
| `sat-ejk.7` | Align Project knowledge guidance for refreshed run artifacts | Closed; post-migration support adjustment |
| `sat-ejk.8` | Add explicit Project knowledge routing instructions | Closed; post-migration support adjustment |

## Validation checklist

- Every context file identifies its purpose, source scope, and deployment use.
- `query-policy.md` is the only canonical source for general evidence precedence and confidence vocabulary.
- `ingestion-contract.md` identifies the schema versions it covers and defers schema decisions to [docs/DESIGN-export.md](../DESIGN-export.md).
- The cumulative sidecar asymmetry is handled correctly.
- Project instructions carry all invariant rules that cannot depend on knowledge-file retrieval.
- The culture file separates general guidance from attributed source evidence.
- The administrator roster does not imply Slack administration, AO ownership, or regional SLT status.
- Every migrated augmentation carries the agreed metadata guidance; future augmentations apply it as appropriate, not as a hard schema requirement.
- The validation set has been run before integration and again after relevant schema or policy changes.
- Legacy documents are not retired before their canonical replacement and workflow redirect are verified.
