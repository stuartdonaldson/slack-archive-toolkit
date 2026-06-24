# Plan — <Project Name>

<!-- Use this file when bd (beads) is in use WITHOUT the planning funnel. -->
<!-- When bd + planning funnel are both in use: do not create this file. -->
<!-- When bd is NOT in use: use templates/PLAN.md instead. -->

## Status
<Current milestone or phase — one sentence.>

## Open Decisions
[If applicable]
- <Decision needed> — <specific question>

## Recent Findings
[If applicable]
- <Observation not yet extracted to permanent home>

<!-- Prefer `bd remember "insight"` for operational observations —
     memories surface automatically in every session via bd prime without manual extraction.
     Use §Recent Findings only for structural/architectural findings not yet ready for a
     permanent document, or as a staging buffer when bd is temporarily unavailable. -->

## Working
```
bd ready              # available work (unblocked, prioritized)
bd list               # all open issues
bd show <id>          # full issue detail with deps
bd update <id> --claim  # claim and start work (atomic: sets assignee + in_progress)
bd close <id>         # mark complete
/bd-report            # generate bdreport.md (snapshot with graph + narrative)
```
