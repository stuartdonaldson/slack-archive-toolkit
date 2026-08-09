# LL: subagent-implemented fixes duplicated existing code instead of extending it

Date: 2026-08-09
Domain: process (agent dispatch / code review composition)

## Observation

Two implementation tasks (sat-ece: CHANNEL_USER dedupe fast path; sat-b9b:
nightly-backup stop tool) were dispatched to background subagents, each in
an isolated worktree, each instructed to follow this project's
`implementation-gate` skill. Both agents self-reported "done" with passing
tests and were presented to the user as complete.

Post-hoc review (prompted by the user, not by any automated step) found:
1. The new `_dedupe_channel_user_fast(db_path)` function
   (`src/slackbackup/backup_logic.py`) duplicates the exists-check /
   connect / try-finally-close / catch-sqlite3.Error shape already present
   in `_max_message_ts(db_path)`, a few lines above it in the same file.
   The new function's own docstring states it "mirrors _max_message_ts's
   contract" but does not factor out a shared helper.
2. `scripts/dedupe-existing-archives.py` still calls the original slow
   `slackdump.dedupe()` path directly; the sat-ece fix was wired into only
   one of the two places in the codebase that dedupe an archive.

Neither gap was caught by the implementing agent, by the dispatch
instructions, or by any step performed by the orchestrating session
between "agent reports done" and "orchestrator reports done to user."

## Why Chain (branched — two independent causal paths)

Branch A — implementation-gate has no related-code-search step
  Why 1 — The agent added new code without surveying the file for an
  existing near-identical pattern, despite noticing and naming the
  similarity in its own docstring.
  Why 2 — implementation-gate's procedure (scope check, issue gate,
  AC/contract gate, ATDD phase, test-before-commit, crash-fix rule) has no
  step requiring a codebase search for related/similar/reusable code
  before or during implementation.
  Why 3 — The gate's "Addresses" section lists the specific historical
  failures it was built to prevent (scope overrun, crash silenced, AC
  skipped, fix committed untested) - duplication/related-code-discovery
  was never one of the incidents that shaped it.
  Why 4 — The check that *does* exist for this concern (reuse,
  simplification, consolidation) lives in a separate, later-stage skill
  (`simplify` / `code-review`) with no documented link from
  implementation-gate to it - the two skills are not composed together
  anywhere.
  Root cause A: implementation-gate is scoped purely as a pre-code
  discipline gate (scope/issue/AC/test) and has no step - nor a required
  handoff to the skill that does cover it - for surveying existing
  related code before implementing.

Branch B — subagent output reached the user without an independent review pass
  Why 1 — Both agents' self-reported "done" (tests passing, branch
  committed) was relayed to the user as the completion status without an
  independent code-review/simplify pass on the resulting diff.
  Why 2 — There is no rule stating that a background subagent's code
  output must go through a review skill (`code-review`, `simplify`)
  before the orchestrating session presents it as finished - review
  skills in this project are invoked explicitly/on request, not
  automatically after Agent-tool task completion.
  Why 3 — Dispatching implementation work to parallel background
  subagents is a newer composition pattern than the skill catalog's
  existing triggers assume; `merge-gate`/`increment-gate` exist for
  reviewing work at defined project gates but nothing ties "an Agent-tool
  task produced a code diff" to "run a review skill on it before
  reporting."
  Root cause B: no rule requires a review pass between "a dispatched
  subagent reports its code done" and "the orchestrator presents that
  work to the user as done" - subagent self-reports are currently trusted
  without independent verification.

## Initial Candidates

Branch A:
- c: add a "related-code survey" step to implementation-gate (global skill,
  ~/.claude/skills/implementation-gate/SKILL.md) - highest leverage, fixes
  this for every project using the gate, not just this one.
- b: add project-CLAUDE.md rule instead/in addition - lower leverage,
  project-scoped only.

Branch B:
- b: global CLAUDE.md instruction (Section 8, Implementation Gate) that
  dispatching implementation work to a subagent requires a code-review/
  simplify pass on its diff before reporting completion.
- c: update `merge-gate`/`increment-gate` (or a new lightweight check) to
  explicitly trigger on "Agent-tool task produced a code diff," not just
  defined project gates.
- e: bd memory noting the practice, lowest durability - fallback only.

[Full option development happens below - resolving now per explicit user request.]

## Resolution

Resolved 2026-08-09 (same session, per explicit user request to resolve
immediately rather than defer to next gate/phase transition - normally
this skill defers even single incidents for analytic depth; the user
directed an immediate resolve here).

**Selected: A2 + B1, applied at project scope (interim, not the durable
fix).** User explicitly chose the project-CLAUDE.md lever over the global
skill-level lever (A1/B1-global) for both clusters. Applied to this
project's CLAUDE.md as a new "Before Implementing (interim,
project-scoped)" section:
- Cluster A (no related-code-search step): require a codebase search for
  existing similar logic before implementing.
- Cluster B (no review pass on subagent output): require a code-review/
  simplify pass on any subagent-dispatched diff before reporting it done.

**This is explicitly an interim, project-scoped mitigation.** While
investigating for the DevStandard-side report, found this project's
incident is a second, independent recurrence of a root cause already
staged (unresolved) at
/mnt/c/dev/DevStandard/docs/lessons-learned/2026-07-20-duplicated-call-site-logic-not-flagged-by-any-gate.md
(F3Go30, 2026-07-20 - same Root Cause A: no in-flow check between "write
similar logic" and "stage the change"; that incident also landed the same
kind of interim CLAUDE.md mitigation at project scope, for the same
stated reason - blast radius vs. opt-in). Added this project's occurrence
as a new observation to that file rather than filing a disconnected new
one (per this skill's Mode 1 Step 2 - related incident found, same root
cause). Per this skill's resolve Step 2 ("≥2 incidents with the same root
cause: resolve together"), the global-tier fix (implementation-gate /
simplify skill update) is now confirmed needed across at least two
projects and should be revisited there rather than left as a per-project
convention indefinitely. Cluster B (subagent self-report trust gap) is a
new nuance not present in the F3Go30 incident - noted separately in the
DevStandard file as a variant of its Branch A, not a full third root
cause.

**Verification (skill Step 9):** would this have caught the original
failure? For Cluster A - yes, a required search step would have surfaced
`_max_message_ts` before `_dedupe_channel_user_fast` was written, and
would have surfaced `dedupe-existing-archives.py` as a related call site.
For Cluster B - yes, a required code-review/simplify pass on the sat-ece
diff before reporting it done would have flagged both gaps directly (that
is exactly the kind of finding `code-review`/`simplify` are built to
catch).
