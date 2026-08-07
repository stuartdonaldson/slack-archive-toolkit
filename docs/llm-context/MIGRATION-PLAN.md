# LLM context pack migration plan

## Decision

Create a Markdown-first context pack for shared ChatGPT sessions and projects. It separates the Slack export contract, query/reporting policy, F3 background, and dated supplemental facts. Existing documents remain unchanged during this migration; this plan names their eventual replacements and removal criteria.

Hand-maintained supplemental facts belong in Markdown, not hand-authored JSON. Markdown tables are easier to review, edit, cite, and upload alongside the other context files. JSON remains appropriate for generated or machine-consumed artifacts such as the Slack digest, user-profile export, and file-content sidecar. If structured augmentation data is later needed by code, generate JSON from the reviewed Markdown source rather than maintaining both independently.

## Goals

- Give an LLM one unambiguous source for schema rules, evidence rules, F3 background, and dated supplemental facts.
- Make source authority and freshness visible in every manually maintained supplement.
- Provide reusable prompts and report formats without duplicating the underlying rules.
- Keep the context pack concise enough to upload with a digest, profile roster, and file sidecar.
- Preserve the existing documents until their replacements have been reviewed and adopted.

## Non-goals

- Replace the generated Slack digest, profile roster, or file-content sidecar with prose.
- Treat manually collected facts as more current than maintained Slack evidence.
- Change existing documentation, automation, or nightly copy behavior in this planning increment.

## Target layout

```text
docs/llm-context/
├── README.md
├── MIGRATION-PLAN.md
├── ingestion-contract.md
├── query-policy.md
├── f3-domain-context.md
└── augmentations/
    ├── f3-nation-operations-2026-06-30.md
    └── f3-nation-admins-2026-06-30.md
```

| Target file | Canonical responsibility | Derived from | Maintenance rule |
| --- | --- | --- | --- |
| `ingestion-contract.md` | Upload validation, schema versions, sidecar pairing, timestamps, channel fields, identity scope, file currency, and the brief initial-ingestion response. | `docs/slack-ingestion.md` | Changes with digest/profile/sidecar schema. |
| `query-policy.md` | Evidence precedence, currency/conflict resolution, confidence labels, authority boundaries, question routing, and SLT/AO table templates. | `docs/report-queries.md` plus policy fragments in `docs/slack-ingestion.md` | Changes when reporting or evidence practice changes. |
| `f3-domain-context.md` | F3 culture, vocabulary, 3 Fs, writing posture, and cultural source notes. | `docs/f3-culture.md` | Changes when the curated cultural context is refreshed. |
| `augmentations/f3-nation-operations-2026-06-30.md` | Dated F3-Nation capabilities, role distinctions, ownership routing, and diagnostic questions not available in normal Slack exports. | `docs/f3-it-infrastructure-augmentation-2026-06-30.md` | Must state collection date, source, scope, known gaps, and refresh trigger. |
| `augmentations/f3-nation-admins-2026-06-30.md` | Manually maintained regional F3-Nation administrator roster and its limitations. | `docs/f3-it-infrastructure-augmentation-2026-06-30.json` and companion Markdown table | Markdown is the review/edit source. A generated JSON derivative is optional only if an automated consumer needs it. |

## Source authority model

Use the target files to explain how to interpret evidence, not to overwrite it. For current operational facts, apply this order:

1. Current maintained Slack canvas/file content and current channel topic/purpose
2. Recent explicit announcement by the responsible role holder, organizer, or system owner
3. Structured fields in the supplied Slack digest/profile export
4. Message or thread evidence
5. Dated manual augmentation for a fact absent from Slack exports
6. Profile title/display name
7. Inference or name similarity

A dated augmentation may answer a question that the Slack exports cannot answer, such as who can configure an F3-Nation setting. It must never be presented as current without its collection date or be used to infer unrelated Slack, AO, or regional-leadership authority.

## Migration phases

### Phase 1 — Proposal scaffold

Create this folder, the migration plan, and the upload guide. Do not alter current source documents or automation.

**Exit criteria:** The intended structure, source authority, and Markdown-first augmentation policy are agreed.

### Phase 2 — Create canonical context files

Create the five target content files. Move content rather than copy it where possible. Each target file should link to the legacy source while both remain present.

**Exit criteria:** Each rule has exactly one canonical target home; cross-links identify the legacy source as transitional.

### Phase 3 — Validate an upload set

Upload the context pack with one digest, matching user-profile export, and matching file-content sidecar. Exercise the prompts in `README.md` for ingestion, SLT, AO, and F3-Nation authority questions.

**Exit criteria:** Answers preserve source links, separate authority types, label uncertainty, and do not confuse dated augmentation data with current Slack facts.

### Phase 4 — Redirect integrations

Update the repository documentation index and the nightly LLM-context copy list to use the new canonical files. Update any project instructions or shared ChatGPT Project instructions to name the pack and required run-specific exports.

**Exit criteria:** New upload workflows use the pack without relying on legacy documents.

### Phase 5 — Retire legacy documents

Only after Phase 3 validation and Phase 4 integration are complete, remove or archive the legacy files listed below. Do not remove a file while it remains a canonical source, is referenced by automation, or contains content not migrated to a target file.

| Legacy item | Planned disposition | Condition before removal |
| --- | --- | --- |
| `docs/slack-ingestion.md` | Replace with `ingestion-contract.md` | Schema and initial-ingestion guidance fully migrated; all references redirected. |
| `docs/report-queries.md` | Replace with `query-policy.md` | Reporting rules and table templates fully migrated; all references redirected. |
| `docs/f3-culture.md` | Replace with `f3-domain-context.md` | Cultural framing, terminology, and source notes fully migrated. |
| `docs/f3-it-infrastructure-augmentation-2026-06-30.md` | Split into the two dated augmentation Markdown files | Operational routing and roster metadata/table fully migrated and reviewed. |
| `docs/f3-it-infrastructure-augmentation-2026-06-30.json` | Remove as a hand-maintained source | The Markdown roster is authoritative; retain or generate JSON only if a machine consumer demonstrably requires it. |

## Validation checklist

- Every context file identifies its purpose and source scope.
- Every dated augmentation gives its collection date, author/source, coverage, exclusions, and refresh trigger.
- `query-policy.md` is the only source for evidence precedence and confidence vocabulary.
- `ingestion-contract.md` is the only source for digest/profile/sidecar schema and initial-ingestion behavior.
- The culture file contains background and style guidance, not current leadership or authority assignments.
- The administrator roster does not imply Slack administrator, AO ownership, or regional SLT status.
- The upload guide names the required matching run-specific files and optional augmentations.
