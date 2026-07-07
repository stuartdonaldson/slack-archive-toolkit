# CLAUDE.md — Slack Backup

**Tier:** Standard
**Standards:** docs/framework/doc-standard.md _(read-only — do not edit)_

<!-- Framework sections — managed by the framework.
     On framework upgrade, replace from ## Reading Order through ## Memory System
     with the updated content from the CLAUDE.md template. Preserve all sections
     above this comment and any project-specific sections added below. -->
## Reading Order
1. Current state — `bd prime` _(auto-loaded when bd in use)_
2. CONTEXT.md — purpose, capabilities, use cases
3. DESIGN.md — architecture, modules
4. docs/adr/ — why key decisions were made
5. docs/references/ _(optional)_ — external document summaries

## Document Map
| Content | Default Location |
|---------|---------|
| Purpose, capabilities | docs/CONTEXT.md |
| Quality goals, stakeholders | docs/CONTEXT.md |
| Glossary | docs/CONTEXT.md |
| Architecture, modules, data model | docs/DESIGN.md |
| Deployment, configuration, failure modes | docs/OPERATIONS.md |
| Authorization / session re-auth workflow | docs/OPERATIONS.md §Authorization |
| Current state | `bd ready` |
| Identified work | bd |
| Technical decisions | docs/adr/ |
| External doc summaries | docs/references/ _(optional)_ |

## Placement Rules
- New capabilities → docs/CONTEXT.md §Core Capabilities + use case if actor-driven
- Architecture changes → docs/DESIGN.md + affected diagrams
- New risk identified → `bd remember`
- Operational changes → docs/OPERATIONS.md
- Resolved decisions → docs/adr/
- New terms → docs/CONTEXT.md §Glossary

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

Do not use MEMORY.md for project rationale. Do not use `bd remember` for user preferences.

## Design Documents (project-specific)

This project has split `docs/DESIGN.md` by capability rather than keeping one
monolithic file — check all of these, not just `docs/DESIGN.md`:

| Document | Covers |
|----------|--------|
| docs/DESIGN.md | Per-channel message backup (archive/resume, channels.json) |
| docs/DESIGN-export.md | Monthly JSON export of an archived channel |
| docs/DESIGN-files.md | Channel catalog + canvas/file harvesting — **designed, not yet implemented** |
| docs/references/slackdump-cli-notes.md | slackdump CLI behavior/cost/gotchas — check before re-deriving anything about how slackdump itself behaves |

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
