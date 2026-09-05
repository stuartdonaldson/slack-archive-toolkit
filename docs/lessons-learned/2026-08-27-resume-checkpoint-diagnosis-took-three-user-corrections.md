# LL: fix design for resume-checkpoint-dead channels was wrong twice and root-caused incompletely, each time only corrected by direct user pushback

Date: 2026-08-27
Domain: process (investigation/diagnosis discipline, single session, no subagent involved)

## Observation

Diagnosing why 8 Slack channels' nightly `resume` permanently fails (sat-zg9),
three designs/claims were presented in sequence within one conversation,
each stated with confident/settled language, each requiring the user to
find the flaw before the next iteration happened:

1. Root cause first stated as a "thread-only channel" quirk, called
   "confirmed" on the strength of one injection test (adding a MESSAGE row
   to a TYPE_ID=0 chunk unblocks `resume`). That test verified a mechanism
   (what `resume` requires), not the root cause (why these channels never
   got such a row). The actual mechanism - `slackdump archive -v` always
   writes a TYPE_ID=0 chunk, even empty, but `resume` needs a MESSAGE row
   linked to one, not just the chunk - only surfaced after the user asked
   "so do we have a real problem right now" and a second, deeper
   verbose-trace investigation was run.

2. Fix design #1 proposed: "adopt a fresh re-archive result only if it's
   not smaller than the local message count." Presented as a
   recommendation with no test run against it. The user's next message
   ("if we have 100 messages locally... but that is still less than 100
   messages we already have, would this mean we won't grab that new
   message?") identified in one question that the design was all-or-
   nothing and would silently drop a genuinely new post whenever a
   channel's currently-visible history had shrunk below the local count -
   which this project's own code comments already document as the normal
   steady state (`backup_logic.py`'s `BACKUP_CADENCE_TIERS` docstring:
   "Max cadence sits far inside Slack's ~90-day retention").

3. Fix design #2 proposed: delegate to `slackdump tools merge`, already
   used elsewhere in this project and documented as safe for this shape
   of source. This one WAS tested before presenting it - but the first
   test run used two full archives where the "new" one was larger, not
   the specific shrink-plus-one-new-message shape the user had just
   demonstrated broke design #1. Only after the user asked a third time
   ("can't we grab the data and identify any records we downloaded that
   are not in our archive and copy them over? I don't see why this is not
   resumeable") was `tools merge` re-tested against that exact scenario -
   revealing it silently drops the new message (ran "successfully,"
   reported compatible, message count unchanged). The eventual working
   design (hand-rolled diff-and-copy keyed on (CHANNEL_ID, TS)) was the
   user's own proposal, verified only at that point.

No step in the investigation caught any of these three before the user did.

## Why Chain (branched - three independent causal paths)

Branch A - diagnosis called "confirmed" on a mechanism test, not a root-cause test
  Why 1 - "Confirmed" was applied to the whole diagnosis ("thread-only
  channel quirk") after a test that only verified one causal link (A
  unblocks B), not the prior link the narrative also asserted (why these
  channels have no type-0-linked row in the first place).
  Why 2 - There was no checkpoint separating "this specific claim is
  tested" from "the full explanatory narrative is tested" - confidence
  language was applied to the narrative as a whole once any part of it was
  verified.
  Why 3 - The deeper evidence that actually explained the phenomenon
  (`slackdump archive -v`'s CHUNK-level trace) required going past the
  default log verbosity used for every other command in this
  investigation - that step was only reached reactively, after a user
  question implied the existing explanation was incomplete, not
  proactively as part of establishing "confirmed."
  Root cause A: no explicit distinction was drawn between "the mechanism I
  just tested is real" and "I have explained the phenomenon this bug
  report is about" before using settled/confirmed language for the latter.

Branch B - fix design #1 wasn't checked against this project's own already-documented constraint before being presented
  Why 1 - Design #1 ("adopt fresh result only if not smaller") was
  presented as a recommendation without being run against a scenario where
  the fresh count is smaller *and* contains something new.
  Why 2 - That scenario is not an edge case in this project - it's the
  documented normal case for any channel old enough that some local
  history has aged past Slack's retention window while new messages keep
  arriving.
  Why 3 - The fact was already written down, in the same file being
  edited, a few lines from the change under discussion (`backup_logic.py`
  line ~25: "Max cadence sits far inside Slack's ~90-day retention") - but
  nothing in the process of drafting a fix design required re-reading
  nearby already-documented constraints in the file being changed before
  presenting the design.
  Root cause B: no step required checking a proposed fix design against
  already-documented domain constraints in the same file/module before
  presenting it as a recommendation - structurally the same shape of gap
  as the project's existing resolved LL
  ([[2026-08-09-subagent-dispatch-missed-related-code-search]]/DevStandard
  F3Go30 Root Cause A: "no in-flow check between writing new logic and
  staging it, against what's already there") but applied to a *design*
  proposed before code, not to code itself, and in-session rather than via
  a dispatched subagent.

Branch C - a user counterexample corrected the immediate next step, not the rest of the investigation
  Why 1 - After the user's question exposed design #1's flaw, the next
  candidate (`tools merge`) was tested before presenting it - real
  progress - but the test used a shape (bigger fresh result) that didn't
  reproduce the specific counterexample the user had just given (smaller-
  plus-one-new).
  Why 2 - The counterexample existed only as a sentence in the
  conversation, not as a concrete, reusable test script or fixture -
  nothing carried it forward as a standing check to run against every
  subsequent candidate in the same investigation.
  Why 3 - There is no habit of converting a user-supplied counterexample
  into a persisted regression scenario the moment it's raised, so it can
  be mechanically re-applied to each later candidate without depending on
  memory or re-derivation.
  Root cause C: a disconfirming scenario raised by the user was treated as
  a one-off correction to the design it was raised against, not captured
  as a reusable test case for the rest of the same investigation - so the
  same class of gap (untested against the known-hard scenario) recurred
  one candidate later.

Branch D - proposed fixes weren't checked for consistency against how the rest of the system already, demonstrably, behaves
  Why 1 - Design #1's safety argument implicitly required "a correct
  re-fetch of a channel must never legitimately return fewer messages than
  what's already on disk." But ordinary `resume` - all ~396 other channels,
  run nightly for months - works safely specifically because it is
  incremental and never makes or depends on that comparison; if shrinking-
  on-refetch were actually dangerous, ordinary `resume` would already need
  to guard against it too, and demonstrably doesn't, because for it the
  situation never arises as a threat.
  Why 2 - Design #2 relied on `slackdump tools merge` as trustworthy for
  reconciling two archives of the same channel - but this project's own
  reference doc (`docs/references/slackdump-cli-notes.md`), already read
  and quoted earlier in the same session, records that exact tool as
  already known-unreliable for a structurally similar job ("does not
  deduplicate," fails outright on a related archive shape). The system
  already contained a documented reason to distrust this tool for this
  kind of task before it was proposed as the fix.
  Why 3 - In both cases, asking "if this proposal's implicit assumption
  were true, what should already be observably true elsewhere in this
  system - and is it?" would have surfaced the contradiction through
  reasoning alone, before any test was run - cheaper and earlier than the
  tests that eventually caught each flaw (one from the user, one
  self-run).
  Why 4 - No step in the investigation asked that question. Verification
  was scoped to "does this satisfy the immediate failure case," never to
  "is this consistent with how the rest of the already-working system
  behaves" - a contradiction there is a free signal the proposal's mental
  model of the system is wrong.
  Root cause D: proposed fixes were checked against the specific failure
  being fixed, but never checked for consistency against already-observed,
  already-working behavior elsewhere in the same system - the highest-
  leverage and cheapest of the three checks identified (reasoning-only, no
  test required), and arguably upstream of Branch B (which is the narrower
  case of this same check limited to "docs/comments in the same file") and
  Branch C (capturing counterexamples once found) - both B and C are ways
  of catching the same class of contradiction; D is the general principle
  that would have caught both without needing either.

  User's own restatement (sharper than the above): "the shape of your
  solution did not fit the shape of related archive/resume." Every other
  piece of this pipeline - `resume` itself, `_dedupe_quietly`,
  `_backfill_bot_images_quietly` - is additive-only: check what's new,
  append it, never compare totals, never replace what's on disk. Design #1
  (whole-archive compare-and-replace-if-not-smaller) and design #2
  (reconcile via a tool built for merging two full archives against each
  other) both broke that shape; the eventual correct design (diff-and-copy
  by message key, purely additive) is the only one of the three that
  actually matches it. A structural-shape mismatch against the rest of the
  same module is a special case of Branch D's general check, concrete
  enough to state as its own quick test: does a proposed fix's basic
  operation (replace vs. append; compare-whole vs. diff-key) match the
  operations already used by the surrounding code for the same kind of
  data?

## Initial Candidates

Branch A:
- e: bd memory for this project, noting the specific pattern ("mechanism
  confirmed" != "root cause confirmed" - trace to the actual causal step,
  e.g. via verbose/debug output, before asserting root cause"). Low
  durability but this is close to a general epistemic-hygiene habit that
  may already be intended by existing global principles (T-series
  testing/verification principles) - worth checking at resolve whether
  this is a gap in applying an existing principle vs. a genuinely missing
  one, per doc-standard.md/sdlc-testing-principles.md.
- b: global CLAUDE.md addition (Corrections / reporting-faithfully
  section already exists) - could extend with: state which specific claim
  was tested when using "confirmed"/"verified" language, and continue
  investigating if the explanatory chain has an unverified link.

Branch B:
- c: this is the same shape as the existing sat-ece/F3Go30 root cause
  (implementation-gate has no related-code-search step) - worth checking
  at resolve whether the already-pending global implementation-gate
  update (referenced in this project's CLAUDE.md §Before Implementing) is
  scoped widely enough to also cover *design proposals before code
  exists*, not just code itself - if not, this is a new nuance on that
  same pending global fix, not a new independent one.
- b: project CLAUDE.md interim addition (same pattern as the existing
  "Before Implementing" section) if the global fix isn't reachable/scoped
  for this now.

Branch C:
- c: procedural habit, possibly belongs in a skill like
  `test-functional`/`test-functional-strategy` (scenario-matrix framing)
  or as a lightweight addition to whatever lever Branch A/B land on:
  "when a user's message describes a scenario that breaks the current
  candidate, capture it as a named, reusable test/fixture immediately, and
  apply it to every subsequent candidate before presenting it" - low
  durability as prose; better if it can attach to an existing
  investigation/debugging skill rather than live only as a habit.

Branch D (user-identified, highest priority to develop at resolve):
- b: global CLAUDE.md addition - a "systemic consistency check" step for
  any proposed fix/diagnosis: "before presenting it, ask what the proposal
  implies must already be true elsewhere in the system if its model is
  correct, and check whether that's actually observed - a contradiction
  there means the model is wrong, found by reasoning alone, no test
  needed." Candidate placement: near the existing Corrections section
  (reporting faithfully) or as a new short section, since this is a
  general investigative-discipline principle, not project-specific.
- a: doc-standard.md / sdlc-testing-principles.md - if this maps to (or
  should become) a named T-series verification principle, this is the
  most durable, cross-project lever and should be checked first at
  resolve - worth an explicit look at whether an existing principle
  already covers this and was simply unapplied, vs. genuinely missing.
- c: could also be phrased as a skill step (e.g., a lightweight addition
  to how root-cause/fix-proposal work is done generally) if a global skill
  is judged the better home than a CLAUDE.md rule.
