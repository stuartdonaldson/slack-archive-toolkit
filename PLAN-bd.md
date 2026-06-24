# Plan — Slack Backup

## Status
Project initialization complete. TDD red phase (acceptance + unit tests) is the active milestone.

## Open Decisions
- Session file secret format — base64 string vs multiline secret; impacts decode step in workflow

## Working
```
bd ready              # available work (unblocked, prioritized)
bd list               # all open issues
bd show <id>          # full issue detail with deps
bd update <id> --claim  # claim and start work (atomic: sets assignee + in_progress)
bd close <id>         # mark complete
/bd-report            # generate bdreport.md (snapshot with graph + narrative)
```
