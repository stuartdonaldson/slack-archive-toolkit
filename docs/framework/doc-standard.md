---
framework-version: "2.2.1"
released: "2026-03-27"
---
# Documentation Framework — Shared Standards

> This file is the authoritative normative reference for the documentation framework.

This file defines standards that apply identically across all tiers of the documentation
framework (Minimal, Standard, Extended). doc-bootstrap.md references these standards.
Do not duplicate this content in doc-bootstrap.md — reference it.

---

## Tier Overview

| Tier | Profile |
|------|---------|
| **Minimal** | Solo tool, 1–2 modules, one contributor |
| **Standard** | Small team, multiple modules, internal stakeholders |
| **Extended** | Multiple stakeholder groups, compliance, distributed system, or safety-critical behavior |

Tier is determined during DocPhase 1 Discovery. The decision is recorded in CLAUDE.md and is
revisable as the project evolves.

**Tier defines adoption defaults, not a ceiling.** Tier determines which documents are
expected when integrating the framework into an existing repository, and which sections are
required vs optional at that scale. A project at any tier may use documents from a higher
tier if the content justifies it — a Minimal project with complex architecture can have a
CONTEXT.md or DESIGN.md without changing tier. Migration to a higher tier is operator-initiated:
apply the bootstrap prompt specifying the target tier when the project is ready.

---

## File Structure and Placement Rules

**Applies to all tiers.** Tier-specific variations (e.g., document count, naming) are
defined in doc-bootstrap.md.

### Project Root Files
These files live at the repository root across all tiers:

| File | Purpose | Tier Notes |
|------|---------|-----------|
| PLAN.md | Current state, in-flight work, open decisions | Superseded when bd is in use — may be present for human reference but is not used for AI planning or task tracking. Structure and rules apply only when bd is not in use. |
| BACKLOG.md | Identified but unscheduled work | Optional in Minimal tier; always in root if created. Standard/Extended use always. Superseded by bd when an issue tracker is in use. Remains the appropriate tool when bd is not in use. |
| CLAUDE.md | Framework reference, reading order, placement rules | AI agent reference and human navigation guide. |
| README.md | Project introduction | Minimal: combines CONTEXT, DESIGN, and OPERATIONS in one file; separate documents optional if content justifies them. Standard/Extended: navigation hub — required content is a brief description of what the project is and up-to-date getting started instructions; no documentation content (that lives in CONTEXT.md, DESIGN.md, OPERATIONS.md). Use `templates/README-standard.md` as a starting point. |
| CONTRIBUTING.md | Optional contributor guidelines | Only if multiple contributors or OS/IDE variations exist. |

### Directory Structure
| Directory | Purpose | Contents |
|-----------|---------|----------|
| `/docs/framework/` | Read-only copies of framework files | doc-standard.md, README.md, templates/, and optionally planning-guide.md. |
| `/adr/` (Minimal) or `/docs/adr/` (Standard/Extended) | Architecture decisions | Immutable once Accepted. See ADR Format in these standards. |
| `/docs/assets/` | Binary reference files | PDFs, images, diagrams. Create only when needed. |
| `/docs/lessons-learned/` | Staged LL incident files | Transient — one file per incident; deleted after batch resolve. Empty directory = no open incidents. |
| `/docs/interfaces/` | Protocol and API reference scoped to implementation | Create only when needed. |
| `/docs/references/` | AI-readable summaries of external documents | Create only when needed. See Reference Document Handling in these standards. |

### Planning Documents (Optional — when planning-guide.md is in use)

These documents form the planning funnel used alongside bd. They are the standard approach
when bd is in use. Absence of content in VISION.md or ROADMAP.md means nothing has reached
that level yet — not that the funnel is inactive. Governed by `docs/framework/planning-guide.md`,
which is the authoritative reference for the planning workflow. This framework defines their
placement and size targets only.

| Location | Purpose | Lifecycle |
|----------|---------|-----------|
| `docs/VISION.md` | Strategic themes — years-horizon goals that initiatives must align with | Permanent; reviewed annually; rarely changes |
| `docs/ROADMAP.md` | Pre-beads funnel: §Funnel (one-liner ideas) and §Review (lean business cases) | Permanent; evolves at monthly/biweekly planning reviews |
| `docs/staging/<n>.md` | Active scoping for work not yet decomposable into beads issues | **Transient — 2-week max**; deleted when work enters beads or pushed back to §Review |

### Document Tree (All Tiers)
Tier variations in what lives at root vs `/docs/` are defined in doc-bootstrap.md:
- Minimal: README.md is the default — combines CONTEXT, DESIGN, and OPERATIONS. Separate documents may be created if content justifies them.
- Standard: README.md is a navigation hub (description + getting started + links to docs). Separate CONTEXT.md, DESIGN.md, OPERATIONS.md in `/docs/`.
- Extended: README.md as Standard. Additional QUALITY.md in `/docs/`.

**Invariant:** CLAUDE.md and ADRs follow the placement rules above regardless of tier.
PLAN.md and BACKLOG.md follow these rules when present — both may be absent when bd and the
planning funnel are in use together (see §Issue Tracker Integration and §Planning Funnel).

---

## Document Structure Reference

Canonical section lists with per-tier presence markers. Document scaffolding templates are in
`docs/framework/templates/` in the central tooling location — use them when creating new documents.
doc-bootstrap.md references this section — do not duplicate these lists there.

These tables reflect adoption defaults for each tier — what is expected when migrating a
repository into the framework at that scale. Any section marked Optional or "Not expected"
may still be included if the content justifies it.

**Presence markers:** Required / Optional / Not expected by default / Extended only

### CONTEXT.md (Standard + Extended required; Minimal: README.md §CONTEXT by default, or CONTEXT.md if content justifies it)

| Section | Standard | Extended |
|---------|----------|----------|
| Introduction & Goals — Purpose | Required | Required |
| Introduction & Goals — Quality Goals | Optional | Required |
| Introduction & Goals — Stakeholders | Optional | Required (with Role column) |
| Constraints — Technical | Optional | Optional |
| Constraints — Organizational | Optional | Optional |
| Constraints — Regulatory | Optional | Optional |
| Core Capabilities | Required | Required |
| Use Cases | Optional | Required |
| Non-Goals | Optional | Optional |
| Glossary | Optional | Required |

### DESIGN.md (Standard + Extended required; Minimal: README.md §DESIGN by default, or DESIGN.md if content justifies it)

| Section | Standard | Extended |
|---------|----------|----------|
| Solution Strategy | Optional | Required |
| Runtime Architecture | Required | Required |
| Building Block View — Level 1 | Required | Required |
| Building Block View — Level 2 | Optional | Optional |
| Building Block View — Level 3+ | Not expected by default | Optional |
| Runtime View | Optional | Required |
| Deployment View | Optional | Required |
| Crosscutting Concepts | Optional | Required |
| Data Model | Optional | Optional |
| Dependency Rules | Optional | Optional |
| References | Optional | Optional |

### OPERATIONS.md (Standard + Extended required; Minimal: README.md §OPERATIONS by default, or OPERATIONS.md if content justifies it)

| Section | Standard | Extended |
|---------|----------|----------|
| Deployment — Model | Required | Required |
| Deployment — Development Environment | Optional | Optional |
| Deployment — Installation | Required | Required |
| Deployment — Environment Variables | Optional | Optional |
| Configuration — Configuration File | Optional | Optional |
| Configuration — Key Options | Optional | Optional |
| Running | Required | Required |
| Monitoring | Optional | Optional |
| Monitoring — Alerting | Not expected by default | Optional |
| Failure Modes | Required | Required |
| Recovery Procedures | Optional | Required |
| Audit and Compliance | Not expected by default | Optional (required when regulatory constraints exist) |

### QUALITY.md (Extended only)

| Section | Extended |
|---------|----------|
| Quality Tree | Required |
| Quality Scenarios | Required |
| Risks and Technical Debt — Known Risks | Required |
| Risks and Technical Debt — Technical Debt | Required |

### PLAN.md (when bd is not in use)

| Section | Minimal | Standard | Extended |
|---------|---------|----------|----------|
| Status | Required | Required | Required |
| In Progress | Required | Required | Required |
| Next | Required | Required | Required |
| Blocked | Optional | Optional | Optional |
| Open Decisions | Optional | Optional | Optional |
| Recent Findings | Optional | Optional | Optional |
| Backlog (inline table) | Optional | Not expected by default | Not expected by default |

When bd is in use: PLAN.md is superseded. If the file is present it is for human reference only — do not read it for task state, open decisions, or planning context. Use `bd ready`, `bd prime`, and `ROADMAP.md` instead.

### BACKLOG.md (Standard + Extended; not used in Minimal; when bd is not in use)

| Section | Standard | Extended |
|---------|----------|----------|
| Stories | Optional | Optional |
| Decisions Needed | Optional | Optional |
| Bugs | Optional | Optional |
| Debt | Optional | Optional |
| Research | Optional | Optional |

Superseded entirely when bd is in use. If the file is present it is for human reference only — do not read or update it.

---

## Use Case Scenario Format

Required for all use cases. Maximum 25 lines per use case.
Minimal tier: in README.md §CONTEXT. Standard and Extended: in CONTEXT.md.

```markdown
### UC-<N>: <Short Name>

Actor: <Primary actor>

Preconditions:
- <Condition>
- [If applicable] <Additional condition>

Primary Flow:
1. <Step>
2. <Step>
3. <Step>

Alternate Flows:
A1: <Condition> → <Outcome>
[If applicable] A2: <Condition> → <Outcome>

Postconditions:
- <Resulting system state>

Acceptance Criteria:
- <Behavioral criterion — testable; what the system must do; no implementation detail>
[If applicable] - <Additional criterion>

Constraints:
- <Invariant or rule that must hold>
[If applicable] - <Additional constraint>
```

**Rules:**
- Implementation-neutral — no module or service names
- No "As a user" phrasing
- No diagrams inside use case blocks
- Durable and stable — not sprint-specific
- Omit Alternate Flows if none exist
- Acceptance Criteria: behavioral only — no module or function names; implementation-specific criteria belong in the bd issue
- Omit Acceptance Criteria before feature delivery; required before delivery gate closes

---

## ADR Format

**Location:**
- Minimal: `/adr/NNNN-short-decision-name.md`
- Standard / Extended: `/docs/adr/NNNN-short-decision-name.md`

```markdown
# ADR-NNNN: <Short Decision Name>

Status: <Proposed | Accepted | Superseded | Rejected>
Date: <YYYY-MM-DD>
Supersedes: [If applicable] ADR-NNNN
Superseded by: [If applicable] ADR-NNNN

## Context
<What situation or problem prompted this decision. One to three sentences.>

## Decision
<What was decided. State it directly.>

## Consequences
<What becomes easier, harder, or different as a result.
For Proposed status: include the open question that must be resolved.>
```

**Rules:**
- Immutable once Accepted — supersede with a new ADR, do not edit
- Diagrams permitted only when they are the most concise expression of the decision;
  must be Mermaid
- One decision per ADR — do not bundle unrelated decisions

---

## Diagramming Standards

**Default: Mermaid.** Renders natively in GitHub and Claude Code, diffable in PRs,
generatable by AI agents without image handling.

| Location | Recommended Mermaid Type |
|----------|--------------------------|
| Runtime Architecture | `graph` or `C4Context` |
| Building Block / Code Structure | `graph` or `classDiagram` |
| Data Model | `erDiagram` |
| Deployment | `graph` |
| Runtime Scenarios / Failure Modes | `sequenceDiagram` |
| Quality Tree (Extended only) | `graph` |

**Diagram rules:**
- Readable in ≤60 seconds
- Prefer one high-value diagram over many small ones
- Do not duplicate clearly structured bullet or table content in diagram form
- Update diagrams when architecture changes
- CONTEXT.md and README.md §CONTEXT are diagram-free

**Escape hatch:** if a diagram cannot be expressed in Mermaid, store the image in
`/docs/assets/` and link from the relevant document with a comment:

```markdown
<!-- Mermaid not used: <reason> -->
![<Description>](../assets/<filename>)
```

---

## Managed-Section Convention

Some framework-owned content lives inside documents that also contain project-specific
content. These sections are marked with an HTML comment so they can be safely replaced
on upgrade without touching project content.

**Files carrying managed-section markers:**

| File | Managed section |
|------|----------------|
| `CLAUDE.md` | `## Reading Order` through `## Memory System` |
| `/docs/README.md` | "Planning and Documentation Framework" section |

**Exempt templates** (project scaffold — created once, then project-owned; reconciled on
upgrade rather than replaced):
`BACKLOG.md`, `CLAUDE.md` project sections, `CONTEXT.md`, `DESIGN.md`, `OPERATIONS.md`,
`PLAN.md`, `PLAN-bd.md`, `QUALITY.md`, `README-minimal.md`

When adding a new template, determine at creation time whether it contains a managed
section and add the comment marker immediately if so.

---

## Writing Standards

- Current code takes priority over legacy docs when conflicts exist
- Bullet points over prose
- No marketing tone, narrative history, or duplicated explanations
- Scannable in ≤5 minutes per file
- All terms defined once in the Glossary
- Stable, descriptive headings — no clever or ambiguous names
- If verbose, simplify — do not expand
- **Empty sections must be omitted, not stubbed.** Remove placeholder stubs from
  finished documents. Add a section only when it has content.
- **Each factual claim about file placement or copy behavior must appear in exactly
  one document.** Other documents reference it. Duplicate claims diverge silently.
- **When authoring a procedure or runbook:** identify the possible entry states before
  finalising steps — what if an assumed file or precondition is absent? what if the
  target is a different tier or variant? Note handling for degraded or unexpected states.

---

## Graduation Rules

Content in PLAN.md graduates as follows:

| Content | Graduates To |
|---------|-------------|
| Resolved decision | ADR (Accepted) |
| Confirmed architecture | DESIGN.md (Standard/Extended) or README.md §DESIGN (Minimal) |
| Observed operational behavior | OPERATIONS.md (Standard/Extended) or README.md §OPERATIONS (Minimal) |
| New term in use | Glossary |
| Completed capability | §Capabilities / §Core Capabilities |
| Protocol quirk confirmed | /docs/interfaces/[protocol].md + ADR if decision required |
| Identified risk | §Risks (Extended) or BACKLOG.md §Debt (Standard/Minimal); `bd remember` when bd is in use |
| Spike result (planning funnel in use) | `bd close <spike-id> --reason="..."` + `bd remember "insight"` — not a document |
| Staging document decomposed into beads | Delete `docs/staging/<n>.md` |

**When bd is in use:** include `bd close <id>` as a final step for any graduation that resolves a work item. The bead is the record of completion; the document update is the permanent artifact.

---

## Trigger Rules

| Event | Required Action |
|-------|----------------|
| Decision made | Create or update ADR |
| Milestone completes | Update PLAN.md |
| Architecture changes | Update DESIGN.md or README.md §DESIGN + affected diagrams |
| New capability ships | Add or update use case in CONTEXT / README.md §CONTEXT |
| Open decision resolved | Graduate from PLAN.md to ADR (Accepted); remove from PLAN.md |
| Story shipped | Delete from BACKLOG.md; update relevant use case |
| PLAN.md exceeds size target | Extract content to permanent documents before adding more |
| Any document exceeds size target | Flag to operator before expanding |
| External document updated | Update reference summary in /docs/references/ |
| New protocol behavior observed | Add to interface doc; create ADR if decision required |
| Work item claimed (bd in use) | `bd update <id> --claim` |
| Work started on non-trivial item (bd in use) | `bd create` issue first; set `--status=in_progress` before writing code |
| Work item completed (bd in use) | `bd close <id>`; confirm linked doc (ADR, use case) updated |
| Blocking relationship found (bd in use) | `bd dep <blocker> --blocks <blocked>` |
| Decision resolved into ADR (bd in use) | `bd close <decision-issue>`; create ADR |
| Failure, gate finding, or rework occurs | Create `docs/lessons-learned/<YYYY-MM-DD>-<slug>.md`; do not resolve inline |
| Project phase changes (Standard/Extended, README has Status line) | Update README.md Status line to current phase |
| Session starts and `docs/lessons-learned/` has files | Prompt user to resolve staged LL incidents before beginning work |
| Gate or phase transition completes | Check `docs/lessons-learned/`; prompt for batch resolve if files present |
| Contradiction found between framework documents | Flag both claims to operator with source locations; do not resolve unilaterally |
| More than two files being created or rewritten together, or any change that is hard to reverse (restructure, public API change, document rewrite) | Present design summary for operator review before writing any file |
| New initiative identified (planning funnel in use) | Add one-liner to `docs/ROADMAP.md §Funnel` |
| Initiative passes value/risk review | Promote to `docs/ROADMAP.md §Review` with lean business case |
| Initiative selected for execution | Create `docs/staging/<n>.md`; identify open questions as spikes |
| Spike resolves open question | `bd close <spike-id> --reason="..."` + `bd remember "insight"` |
| Staging work fully decomposed into beads | Delete `docs/staging/<n>.md`; execute via `bd ready` |
| Staging document exceeds 2-week TTL | Push back to `ROADMAP.md §Review`; delete staging doc |
| Strategic theme changes | Update `docs/VISION.md`; review ROADMAP.md for alignment |
| New risk identified _(Extended only)_ | Add to QUALITY.md §Risks |
| Risk resolved or mitigated _(Extended only)_ | Update QUALITY.md §Risks; note in relevant ADR |
| Debt item resolved _(Extended only)_ | Remove from QUALITY.md §Technical Debt |
| Compliance requirement changes _(Extended only)_ | Update CONTEXT.md §Constraints + OPERATIONS.md §Audit |
| Quality scenario fails _(Extended only)_ | Update QUALITY.md; create ADR if architectural change required |

---

## Story Rules

- Stories are delivery units, not documentation
- Stories link to the use case they deliver (e.g. "Delivers UC-2")
- Stories are **deleted** when shipped — not archived
- The use case update is the permanent record of the delivered capability
- Never migrate a completed story into CONTEXT.md — update the use case instead

---

## Reference Document Handling

External documents (PDFs, specs, websites) must not be copied into project documentation.

1. Store the document in `/docs/assets/`
2. Create a summary in `/docs/references/` covering only sections relevant to this project
3. Add an entry to the References table in DESIGN.md
4. Document deviations and implementation-specific behaviors as ADRs
5. Add implementation-scoped detail to `/docs/interfaces/[protocol].md`

**Reference summary template:**

```markdown
# <Document Title>

Source: <File path in /docs/assets/ or URL>
Version: <Version or date and time retrieved>
Relevance: <One sentence — why this document matters to this project>

## Summary
<3–5 sentence overview of the document's scope and purpose>

## Relevant Sections

### <Section Name>
<Concise paraphrase of content relevant to this project.
Not verbatim — a useful summary of what matters here.>
[If applicable] ### <Additional Section Name>
<Paraphrase>

## Key Terms
[If applicable]
| Term | Definition |
|------|------------|

## Project-Specific Notes
[If applicable]
<How this project uses or deviates from this document's content.
ADR references where applicable.>
```

**Rules:**
- Summaries cover only sections relevant to this project
- Do not reproduce verbatim spec content — paraphrase and reference
- Keep each summary ≤800 words unless it is a primary protocol reference
- Update summary and note version change when source document updates

---

## CONTRIBUTING.md

`CONTRIBUTING.md` is an optional conventional file at the repository root. It is not
part of the CONTEXT / DESIGN / OPERATIONS structure and is not managed by the framework.

**Include CONTRIBUTING.md when:**
- More than one contributor works on the project
- Developer environment setup varies meaningfully by OS, IDE, or toolchain
- Project-specific conventions need to be stated for new contributors

**CONTRIBUTING.md covers:**
- Developer environment setup variations not covered by the canonical path in OPERATIONS.md
- IDE-specific configuration
- OS-specific notes beyond the standard activation command
- Contribution workflow (branching, PR expectations if applicable)

**OPERATIONS.md covers:**
- The canonical virtual environment setup — the standard path that works
- The Python version requirement reference (stated in CONTEXT.md §Constraints)
- Brief OS variation note for activation command

**CONTEXT.md covers:**
- Python version as a technical constraint

If CONTRIBUTING.md exists, CLAUDE.md should note it:
```markdown
## Contributing
See CONTRIBUTING.md for developer environment setup variations and
contribution workflow.
```

---

## Document Size Targets

Size targets prevent documents from becoming unwieldy and trigger extraction or refactoring.

| Document | Minimal | Standard | Extended | Rationale |
|----------|---------|----------|----------|-----------|
| README.md | ≤800 | ≤200 | ≤200 | Minimal: single file for all contexts. Standard/Extended: navigation hub only — description, getting started, links |
| CONTEXT.md | — | ≤1200 | ≤1500 | Extended allows additional constraint categories and stakeholder detail |
| DESIGN.md | — | ≤2500 | ≤3000 | Extended allows deeper levels of component detail |
| OPERATIONS.md | — | ≤1500 | ≤2000 | Extended allows detailed audit and compliance sections |
| QUALITY.md | — | — | unlimited | Scales with system complexity; quality scenarios are concise units |
| PLAN.md | ≤400 | ≤600 | ≤600 | Living document; size constraint forces content graduation to permanent homes |
| docs/VISION.md | — | ≤400 | ≤400 | Optional (planning funnel); strategic themes only — stable, concise |
| docs/ROADMAP.md | — | ≤800 | ≤1200 | Optional (planning funnel); exceeding signals need for triage or promotion |
| docs/staging/<n>.md | — | ≤300 | ≤300 | Optional (planning funnel); transient, 2-week max; growing = needs more spikes first |
| docs/lessons-learned/<n>.md | ≤150 | ≤150 | ≤150 | Transient; observation + 5-why chain only; no candidates table; growing = resolve more frequently |

**Trigger:** When any document approaches its size target, flag to operator. Do not exceed without explicit decision recorded in an ADR.

**When bd is in use:** PLAN.md and BACKLOG.md are superseded. Size targets for these documents apply only when bd is not in use.

---

## Issue Tracker Integration (Optional — bd / beads)

This section applies only when a project uses bd (beads) as its issue tracker. The framework
operates identically without it — bd is additive, not required.

### What bd Replaces

| Current Framework Element | With bd |
|---------------------------|---------|
| PLAN.md §In Progress | `bd list --status in_progress` |
| PLAN.md §Next | `bd ready` |
| PLAN.md §Blocked | `bd list` (blocked deps) |
| PLAN.md §Backlog | bd issues (low priority) |
| PLAN.md §Open Decisions | `ROADMAP.md §Funnel` → bd issue → ADR |
| PLAN.md §Status | `bd status` (computed) |
| PLAN.md (file) | Superseded — do not use for AI planning or task tracking |
| BACKLOG.md | Superseded — do not use for AI planning or task tracking |

### PLAN.md and BACKLOG.md When bd Is in Use

Both files are superseded when bd is in use. They may exist in the repository for human reference but must not be consulted or updated for AI planning, task tracking, or decisions. `bd ready`, `bd prime`, and `ROADMAP.md` are the authoritative sources of work state and planning context.

If PLAN.md exists, its prior content maps as follows:

| PLAN.md content | Now lives in |
|-----------------|-------------|
| §Status | `bd status` (computed) |
| §Open Decisions | `ROADMAP.md §Funnel` as one-liners until actionable; then bd issue |
| §Recent Findings | `bd remember` |
| §Working | `bd prime` (auto-injected each session) |

### Unavailability Protocol

When bd is unavailable (daemon offline, file lock, network failure):

1. Add one-liners to `ROADMAP.md §Funnel` as a temporary staging area
2. On bd recovery: create the bd issue, remove the one-liner from ROADMAP.md

### Open Decisions Ownership

| Decision state | Home | Action when resolved |
|---------------|------|---------------------|
| Unresolved question with no clear path yet | `ROADMAP.md §Funnel` as a one-liner | When actionable: create bd issue, remove from ROADMAP.md |
| Actionable decision requiring investigation or design work | bd issue (type `decision`) | `bd close <id>`; create ADR |

ROADMAP.md §Funnel holds speculative and pre-actionable questions. Once a decision has an owner and is estimable, it exits ROADMAP.md and becomes a bd issue.

### bdreport.md — Generated Snapshot

`bdreport.md` is a generated view of bd state. It is **never committed** — add to `.gitignore`.
Generate on demand with `/bd-report`.

Contents:
- Narrative summary of current milestone and ready work
- Ready, In Progress, Blocked, and Done issue lists
- Mermaid dependency graph (auto-derived from `bd dep` relationships)

This replaces any hand-maintained Mermaid dependency graph in PLAN.md. The graph is always
current because it is generated, not maintained.

### Dependency Types

| Type | Effect | Use For |
|------|--------|---------|
| `blocks` | Gates `bd ready` — blocked tasks hidden until blocker closes | Scheduling constraints |
| `discovered-from` | Provenance only — does not gate `bd ready` | Lineage and discovery tracking |

### Session Start When bd Is in Use

Replace PLAN.md and BACKLOG.md review steps with:

```
bd ready    # what is actionable now
```

Document-focused steps (size checks, ADR candidates, doc drift) remain unchanged.

---

## Planning Funnel (Standard when bd is in use — docs/framework/planning-guide.md)

The planning funnel governs how ideas mature into executable beads issues. It is defined and
governed by `docs/framework/planning-guide.md`. This framework defines placement and size
targets for its documents (see §Planning Documents and §Document Size Targets) and trigger
rules for its lifecycle events (see §Trigger Rules).

**Relationship to this document:** `planning-guide.md` governs how work enters the execution
layer; this document governs how permanent artifacts are structured and maintained. They are
complementary — neither replaces the other.

**Three entry patterns** (defined in planning-guide.md):

Pattern A, B, and C describe how an individual work item enters beads — not whether the
project uses the funnel. A project using the funnel will use Pattern A for most items.
Absence of content in VISION.md or ROADMAP.md means nothing has reached that level yet,
not that the funnel is inactive.

| Pattern | When | Pre-beads work |
|---------|------|----------------|
| A — Direct to beads | Clear what + how; can write acceptance criteria now | None |
| B — Scope, then beads | Multi-task, known scope | One staging document, deleted on entry |
| C — Full funnel | Large, uncertain, open questions | VISION → ROADMAP → staging → spikes → beads |

Most work is Pattern A. Reach for B or C only when Pattern A doesn't fit.

**Knowledge capture rule:** Spike results and operational observations belong in
`bd remember`, not in documents. `bd remember` surfaces automatically in every session via
`bd prime`. Document only what is durable and structural — use ADRs for decisions,
DESIGN.md for architecture, OPERATIONS.md for procedures.

**Anti-patterns** (from planning-guide.md):
- Staging documents that grow beyond 2 weeks — push back to Review
- PLAN.md prose that restates beads state — beads owns operational state
- Issues used as knowledge articles — use `bd remember` for constraints, ADRs for decisions
- Skipping the memory step after a spike — unrecorded decisions get rediscovered

**Molecule formulas** (optional — defined in planning-guide.md §Molecule Formulas): Example
formulas in `docs/beads-formulas/` formalize Pattern C and feature delivery as parameterized
molecule templates. Molecules are also the recommended tool for **cross-cutting concerns** —
work spanning multiple epics or teams where all areas must complete before the concern closes.

---

## CLAUDE.md

CLAUDE.md structure is defined by `docs/framework/templates/CLAUDE.md` in the central tooling
location. Use that template when creating or auditing a project's CLAUDE.md.

**Memory System Ownership (when bd is in use):**

| System | Scope | Use for |
|--------|-------|---------|
| `bd remember` / `bd memories` | Project-scoped | Project rationale, design decisions, process insights, lessons learned |
| MEMORY.md (auto-memory) | User-scoped | User preferences, cross-project style conventions, persona |

Do not use MEMORY.md for project rationale. Do not use `bd remember` for user preferences.

---

## Universal Success Criteria

All tiers define success as:

| Criterion | Observable Outcome |
|-----------|-------------------|
| Developer re-entry | Working context reached in ≤10 minutes via `bd prime` (when bd in use) or PLAN.md (when bd not in use) |
| AI retrieval | Claude Code locates correct document without ambiguity |
| No duplication | No definition or decision in more than one document |
| No empty sections | All placeholder stubs removed from finished documents |
| Diagrams | All diagrams are Mermaid or have documented escape hatch |
| PLAN.md discipline | Current state only; resolved content graduated |

---

*Saturday, March 21, 2026*
