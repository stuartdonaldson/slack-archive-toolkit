# CLAUDE.md — <Project Name>

**Tier:** Minimal | Standard | Extended  ← delete inapplicable
**Standards:** /docs/framework/doc-standard.md _(read-only — do not edit)_

## Contributing _(optional — multiple contributors or OS/IDE setup variations)_
See CONTRIBUTING.md for developer environment setup variations and contribution workflow.

<!-- Framework sections — managed by the framework.
     On framework upgrade, replace from ## Reading Order through ## Memory System
     with the updated content from the CLAUDE.md template. Preserve all sections
     above this comment and any project-specific sections added below. -->
## Reading Order
1. Current state — PLAN.md _(bd not in use)_ / `bd prime` _(auto-loaded when bd in use)_
2. README.md §CONTEXT _(Minimal)_ / CONTEXT.md _(Standard+)_ — purpose, capabilities, use cases
3. README.md §DESIGN _(Minimal)_ / DESIGN.md _(Standard+)_ — architecture, modules
4. QUALITY.md _(Extended only)_ — quality scenarios, risks, debt
5. README.md §OPERATIONS _(Minimal)_ / OPERATIONS.md _(Standard+)_ — how to run it
6. /adr/ _(Minimal)_ / /docs/adr/ _(Standard+)_ — why key decisions were made
7. /docs/references/ _(optional)_ — external document summaries

## Document Map
| Content | Default Location |
|---------|---------|
| Purpose, capabilities | README.md §CONTEXT _(Minimal)_ / CONTEXT.md _(Standard+)_ |
| Quality goals, stakeholders | README.md §CONTEXT _(Minimal, optional)_ / CONTEXT.md _(Standard: optional; Extended: required)_ |
| Glossary | README.md §CONTEXT _(Minimal, optional)_ / CONTEXT.md _(Standard: optional; Extended: required)_ |
| Architecture, modules, data model | README.md §DESIGN _(Minimal)_ / DESIGN.md _(Standard+)_ |
| Quality scenarios, risks, debt | QUALITY.md _(Extended only)_ |
| Deployment, configuration, failure modes | README.md §OPERATIONS _(Minimal)_ / OPERATIONS.md _(Standard+)_ |
| Current state | PLAN.md _(bd not in use)_ / `bd ready` _(bd in use)_ |
| Identified work | PLAN.md §Backlog _(Minimal, optional)_ / BACKLOG.md _(Standard+, bd not in use)_ / bd _(bd in use)_ |
| Technical decisions | /adr/ _(Minimal)_ / /docs/adr/ _(Standard+)_ |
| Protocol details | /docs/interfaces/ _(optional)_ |
| External doc summaries | /docs/references/ _(optional)_ |
| Strategic themes | /docs/VISION.md _(optional — planning funnel)_ |
| Roadmap, funnel | /docs/ROADMAP.md _(optional — planning funnel)_ |
| Migration losses | /docs/ORPHANED-CONTENT.md _(optional)_ |

## Placement Rules
- New capabilities → README.md §CONTEXT _(Minimal)_ / CONTEXT.md §Core Capabilities _(Standard+)_ + use case if actor-driven
- Architecture changes → README.md §DESIGN _(Minimal)_ / DESIGN.md _(Standard+)_ + affected diagrams
- New quality scenario → QUALITY.md §Quality Scenarios _(Extended only)_
- New risk identified → QUALITY.md §Risks _(Extended)_ / BACKLOG.md §Debt _(Standard/Minimal)_ / `bd remember` _(bd in use)_
- Debt resolved → remove from QUALITY.md §Technical Debt; note in relevant ADR _(Extended only)_
- Operational changes → README.md §OPERATIONS _(Minimal)_ / OPERATIONS.md _(Standard+)_
- Resolved decisions → /adr/ _(Minimal)_ / /docs/adr/ _(Standard+)_
- New terms → README.md §CONTEXT §Glossary _(Minimal)_ / CONTEXT.md §Glossary _(Standard+)_
- Protocol detail → /docs/interfaces/[protocol].md _(optional)_
- Do not create new top-level document types — consult doc-standard.md §Tier Overview for tier guidance

## Maintenance Protocol

Claude does not monitor documents between sessions, detect drift, or update documents
without explicit instruction.

- At session start or phase transition: run `/session-start-check`
- After any code or architecture change: run `/doc-trigger-check`
- To trigger a state review: "review project state before we start"

## Memory System _(when bd is in use)_
| System | Scope | Use for |
|--------|-------|---------|
| `bd remember` / `bd memories` | Project-scoped | Project rationale, design decisions, process insights — travels with the repo |
| MEMORY.md (auto-memory) | User-scoped | User preferences, cross-project style conventions |

Do not use MEMORY.md for project rationale. Do not use `bd remember` for user preferences. When in doubt: if the insight is about a specific codebase or project decision, use `bd remember`; if it applies regardless of repo, use MEMORY.md.

