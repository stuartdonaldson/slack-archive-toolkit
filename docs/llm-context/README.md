# LLM context pack

This folder contains the reusable guidance, prompt templates, and validation material for answering questions from Slack-derived F3 data. The documents under [uploads](uploads) are individually uploadable Project-knowledge files. The remaining root-level documents explain how to use or maintain them.

## How to use this pack

### ChatGPT Project

1. Paste [project-instructions.md](project-instructions.md) into the ChatGPT Project instruction box. Do not upload it as a knowledge file.
2. Upload these files individually as Project knowledge:
   - [ingestion-contract.md](uploads/ingestion-contract.md)
   - [query-policy.md](uploads/query-policy.md)
   - [f3-domain-context.md](uploads/f3-domain-context.md)
   - [F3 augmentations index](uploads/augmentations/f3-augmentation-index.md)
   - each augmentation needed for the questions the Project will answer
   - all current exported Slack-data artifacts for the intended coverage
3. Start a chat by requesting the initial intake validation. It reads each uploaded artifact and reports its coverage, freshness, pairing status, and material gaps.
4. Refresh or replace each artifact independently when newer data is available. A later explicitly uploaded file or chat instruction supersedes an earlier artifact only for the facts it covers.
5. Ask the required question directly. The uploaded query policy contains routing and report formats for common leadership, AO, and authority questions. Use a template from [prompts](prompts) only for specialized outputs such as a newsletter or FNG guide.

**Example — Project intake:** “Using the current Project knowledge files, run the initial intake validation only. State each artifact's date or coverage, workspaces, sidecar pairing status, and material gaps.”

**Example — Project report:** “Produce the current regional SLT report using the current uploaded artifacts.”

### Standalone ChatGPT session

1. Upload the same individual context files, selected augmentations, and current digest/profile/sidecar artifacts to a new chat.
2. Paste [session-preamble.md](session-preamble.md) as the first message.
3. Wait for its intake-validation response.
4. Ask the required question directly. Use a template from [prompts](prompts) only for a specialized output such as a newsletter or FNG guide.

**Example — standalone AO directory:** Upload the context and current artifacts, paste the session preamble, then ask: “Produce an AO/site directory for F3 Cascades.”

### Folders are repository organization only

ChatGPT Project knowledge does not reliably browse repository folders. Upload the individual files listed above. In particular, uploading the augmentation index does not upload its listed augmentations, and the prompt library contains specialized operator templates—not a group of files to upload by default.

## Validation workflow

Use [validation-set.md](validation-set.md) when changing the context pack, export schema, query policy, or Project instructions.

1. Prepare a real digest, profile export, sidecar, and any augmentations needed by the scenarios.
2. Test both modes: a one-off ChatGPT session using the session preamble, and a ChatGPT Project using the pasted Project instructions and individually uploaded knowledge files.
3. Run each applicable scenario with real names, channels, or files substituted.
4. Evaluate whether the answer follows the expected evidence and confidence behavior, not whether a time-sensitive factual answer happens to be unchanged.
5. Record the live ChatGPT test separately from the earlier static document review in [VALIDATION-RESULTS.md](VALIDATION-RESULTS.md). File remediation work for failures before declaring a mode validated.

## Source roles

| Source | What it provides | How to use it |
| --- | --- | --- |
| Slack digest | Messages, replies, channel metadata, structured activity/leadership fields, links, and file references | Primary evidence for visible Slack facts in the covered period. |
| User-profile export | Workspace-local display names, titles, and Slack roles | Resolves identities and Slack administration; titles are supporting signals and may be stale. |
| File-content sidecar | Extracted Canvas/document text matched to digest file references | Primary evidence when a maintained document answers the question. The sidecar is cumulative, not digest-window-matched. |
| Ingestion contract | Schema, pairing, identity, timestamp, and initial-upload rules | Consult before analysis. |
| Query policy | Evidence priority, confidence, authority boundaries, and output formats | Consult before answering substantive questions. |
| F3 domain context | Culture, vocabulary, and writing posture | Background only; not proof of a current role or event. |
| Dated augmentation | Facts unavailable in standard Slack exports | Upload the relevant file explicitly; state its collection date and limitations. |

## Authority boundaries

Do not equate these roles:

- Slack workspace admin/owner controls Slack workspace governance and app permissions.
- F3-Nation app admin configures regional F3-Nation settings.
- Regional SLT roles lead the region.
- Site Q/AO Q/OIC roles are scoped to a specific AO or site.

One role is not evidence of another. Current maintained Slack evidence outranks a dated manual augmentation when they conflict.

## Pack organization

| Location | Purpose | Upload by default? |
| --- | --- | --- |
| [uploads](uploads) | Individually uploadable knowledge documents and augmentations. | Yes, select individual files. |
| [prompts](prompts) | Specialized operator templates for a newsletter or FNG guide. | No; paste or attach one only when needed. |
| [project-instructions.md](project-instructions.md) | Paste-ready ChatGPT Project instructions. | No; paste into the instruction box. |
| [session-preamble.md](session-preamble.md) | First message for a one-off chat. | No; paste as the first message. |
| [validation-set.md](validation-set.md) | Maintainer test specification. | No; use during validation. |

The pack's decomposition and evidence-precedence decisions are recorded in
[ADR-0008](../adr/0008-llm-context-pack-decomposition.md). The migration plan, review, and
validation-results documents that preceded it are retired now that the migration is complete
(`sat-ejk`, closed) — retrieve them from git history if the reasoning trail is needed.

## Sources curated into the pack

The canonical upload files were copied from the retired sources below during the migration. Retrieve a retired source from git history if necessary.

| Current file | Retired source material |
| --- | --- |
| [uploads/ingestion-contract.md](uploads/ingestion-contract.md) | `docs/slack-ingestion.md` |
| [uploads/query-policy.md](uploads/query-policy.md) | `docs/report-queries.md` and the evidence/confidence sections of `docs/slack-ingestion.md` |
| [uploads/f3-domain-context.md](uploads/f3-domain-context.md) | `docs/f3-culture.md` |
| [prompts/newsletter.md](prompts/newsletter.md) | `docs/newsletter-prompt.md` |
| [prompts/fng-getting-started.md](prompts/fng-getting-started.md) | `docs/fng-getting-started-prompt.md` |
| [uploads/augmentations/f3-nation-operations.md](uploads/augmentations/f3-nation-operations.md) | F3-Nation role distinctions, operations, and diagnostic guidance. |

## Maintenance rules

- Maintain one canonical home for each rule.
- Keep the trust split intact: the Markdown files in this pack are operator-authored and carry
  instructions; the `.json` run artifacts are machine-extracted Slack content and carry none
  (ADR-0009). Never paste raw Slack or other third-party text into an uploadable augmentation.
  Quoted material goes under `uploads/augmentations/sources/` behind a header marking it as
  quoted, with the summarizing augmentation carrying the operator's own words. Letting unmarked
  third-party text into a `.md` inverts the shorthand silently.
- Add a source date and refresh trigger to every manual augmentation.
- Keep current operational facts in the supplied Slack exports whenever possible.
- Update a dated roster by editing its Markdown table and limitations together.
- Generate any later JSON derivative from the reviewed Markdown source; do not hand-edit both.
- Do not treat a static document review as live ChatGPT validation.
