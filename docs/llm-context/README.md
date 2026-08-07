# LLM context pack

This folder is a Markdown-first context pack for a shared ChatGPT session or ChatGPT Project. It prepares an LLM to safely answer questions about Slack-derived F3 information without treating profile signals or manually collected facts as current proof.

See [MIGRATION-PLAN.md](MIGRATION-PLAN.md) for the staged migration. The canonical context files below now exist (Phase 2), copied from the legacy documents named in [Sources curated into the completed pack](#sources-curated-into-the-completed-pack), have been validated (Phase 3; see [VALIDATION-RESULTS.md](VALIDATION-RESULTS.md)), and are the active upload/copy source (Phase 4) — `scripts/nightly-backup-digest.sh` refreshes a curated `~/slack-exports/llm-context/` subtree from this folder each run, and `README.md`/`docs/OPERATIONS.md` reference it. The legacy per-file documents named below have been retired (Phase 5, `sat-ejk.5`); their content lives only in this pack now and in git history.

## Why Markdown for manual supplements

Use Markdown for human-maintained context such as a regional F3-Nation administrator roster. It is easy to review in pull requests, edit as a table, cite in an answer, and upload with the other guidance files. It also permits the source date, scope, limitations, and refresh instructions to sit beside the facts.

Use JSON for generated data or an automated consumer: the Slack digest, user-profile export, and file-content sidecar are already structured exports. If automation later requires a supplemental roster as JSON, generate it from the reviewed Markdown source instead of editing both formats by hand.

## Intended upload set

### Context files for a shared project

Upload the completed versions of these context documents:

1. `ingestion-contract.md`
2. `query-policy.md`
3. `f3-domain-context.md`
4. Any applicable dated augmentation under `augmentations/`

### Run artifacts in a shared project

Project knowledge may hold the current run artifacts and augmentations. Refresh or replace them periodically, preserving their dates and indicating which file is current. The same artifacts may instead be attached to an individual chat when that is more appropriate.

Provide the current available artifacts for a reporting run:

1. The Slack digest export
2. The Slack user-profile export
3. The current `slack-llm-files-v2` sidecar, when supplied
4. Any relevant dated manual augmentation not represented in the exports

Use the most current artifact for each source type and preserve its coverage, generated, or collected date. The sidecar is cumulative, so it does not need to share the digest's exact export window; sidecar records outside the digest window are expected. Join digest file references to sidecar records using `workspace + channel_id + id`. State material freshness mismatches rather than silently treating an older profile roster, augmentation, or sidecar as current.

## Source roles

| Source | What it provides | How to use it |
| --- | --- | --- |
| Slack digest | Messages, replies, channel metadata, structured activity/leadership fields, links, and file references | Primary evidence for visible Slack facts in the covered period. |
| User-profile export | Workspace-local display names, titles, and Slack roles | Resolves identities and Slack administration; titles are supporting signals and may be stale. |
| File-content sidecar | Extracted Canvas/document text matched to digest file references | Primary evidence when a maintained document answers the question. |
| Ingestion contract | Schema, pairing, identity, timestamp, and initial-upload rules | Read before analysis. |
| Query policy | Evidence priority, confidence, authority boundaries, and output formats | Read before answering substantive questions. |
| F3 domain context | Culture, vocabulary, and writing posture | Background only; not proof of a current role or event. |
| Dated augmentation | Facts unavailable in standard Slack exports | Use only for its stated scope; state its collection date and limitations. |

## Authority boundaries

Do not equate these roles:

- Slack workspace admin/owner controls Slack workspace governance and app permissions.
- F3-Nation app admin configures regional F3-Nation settings.
- Regional SLT roles lead the region.
- Site Q/AO Q/OIC roles are scoped to a specific AO or site.

One role is not evidence of another. Current maintained Slack evidence outranks a dated manual augmentation when they conflict.

## Project instruction

Use [project-instructions.md](project-instructions.md) verbatim in the ChatGPT Project instruction box. It defines the invariant handling of knowledge-file retrieval, freshness, supersession, evidence, and authority boundaries.

## Reusable prompts

### Initial data intake

> Review the uploaded digest, user-profile export, file-content sidecar, and context pack. Do not produce a substantive report yet. Confirm the recognized schemas, exact data date range, workspaces/regions, sidecar pairing status, extracted-content coverage, and material gaps.

### Current regional leadership

> Using the uploaded Slack data and context pack, produce a current regional SLT report for every represented region. State the exact Slack-data date range. Use the source hierarchy in the query policy, provide the required SLT roles first, link the strongest available provenance for every named role, and include only a short Qualifications section for conflicts, vacancies, transitions, and profile-only assignments.

### AO and site directory

> Using the uploaded Slack data and context pack, produce an AO/site directory for the requested region. For each identifiable AO, report its Slack channel, Site Q when supported, topic, purpose, schedule, location, and source/confidence. Keep topic and purpose separate. Do not infer missing operating details from activity patterns or administrator roles.

### F3-Nation or Slack authority

> Using the uploaded Slack data and any applicable dated augmentation, identify the likely authority for this question: Slack workspace administration, F3-Nation regional configuration, regional leadership, AO/Site Q ownership, or F3-Nation dev/ops. State the supporting source and its date. Do not infer one authority from another. If the supplied data cannot establish the answer, explain the gap and the next evidence to seek.

### Evidence review

> Answer this question from the uploaded data. First identify the scope and the strongest available evidence. Resolve material conflicts by source strength and recency. Preserve direct Slack links. Distinguish confirmed facts, profile-only working signals, dated-manual facts, former roles, and unresolved gaps.

## Sources curated into the completed pack

Copied in Phase 2, then retired in Phase 5 (`sat-ejk.5`) once Phase 3 validation and Phase 4 integration were confirmed complete. Each legacy path below no longer exists in the working tree; retrieve it from git history (e.g. `git log --follow -- docs/slack-ingestion.md`) if needed.

| Context file | Retired legacy source material |
| --- | --- |
| `ingestion-contract.md` | `docs/slack-ingestion.md` |
| `query-policy.md` | `docs/report-queries.md` and the evidence/confidence sections of `docs/slack-ingestion.md` |
| `f3-domain-context.md` | `docs/f3-culture.md` (culture-framing claims de-attributed from a specific person; sourced quotes moved to a `Source notes` section) |
| `prompts/newsletter.md` | `docs/newsletter-prompt.md` |
| `prompts/fng-getting-started.md` | `docs/fng-getting-started-prompt.md` |
| `augmentations/f3-nation-operations.md` | The role distinctions, operations, and diagnostic guidance in `docs/f3-it-infrastructure-augmentation-2026-06-30.md` |
| `augmentations/f3-nation-admins.md` | The dated roster and limitations from `docs/f3-it-infrastructure-augmentation-2026-06-30.md` and its companion JSON (`docs/f3-it-infrastructure-augmentation-2026-06-30.json`, removed — no automated consumer, Markdown roster is authoritative) |
| `prompts/initial-intake.md`, `prompts/regional-slt.md`, `prompts/ao-directory.md`, `prompts/authority-routing.md` | New, distilled from this file's §Reusable prompts below |
| `project-instructions.md`, `session-preamble.md` | New |
| `validation-set.md` | New |

## Maintenance rules

- Maintain one canonical home for each rule.
- Add a source date and refresh trigger to every manual augmentation.
- Keep current operational facts in the supplied Slack exports whenever possible.
- Update a dated roster by editing its Markdown table and limitations together.
- Generate any later JSON derivative from the reviewed Markdown source; do not hand-edit both.
