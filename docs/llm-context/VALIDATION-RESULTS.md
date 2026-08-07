# Validation results — 2026-08-07

Run of [validation-set.md](validation-set.md) per [MIGRATION-PLAN.md Phase 3](MIGRATION-PLAN.md#phase-3--validate-the-pack), tracked as [sat-ejk.3](../..).

## Method and data used

This run was performed in a headless session with no access to a live ChatGPT
session or to an uploaded matched digest/profile/sidecar set (no
`slack-llm-digest-v4`, `slack-llm-files-v1`, or `slack-user-profiles-v1`
artifact was reachable from this session's working directories). A live
upload-and-ask run through an actual ChatGPT session/Project — the scenario
the pack is written for — remains outstanding and should be done opportunistically
the next time a real digest/profile/sidecar/augmentation set is assembled for
upload.

In place of that, each scenario below was validated by construction: a small
representative evidence fragment was built matching the real schemas
(`docs/DESIGN-export.md`, `docs/llm-context/ingestion-contract.md`) and the
real, already-committed `augmentations/*.md` content, then traced against the
literal rule text in `ingestion-contract.md`, `query-policy.md`,
`project-instructions.md`, and `session-preamble.md` to confirm the pack
states the expected behavior for that scenario and, for scenario 12,
whether the governing rule is actually resident in
`project-instructions.md` rather than depending on knowledge-file retrieval.
This validates the pack's instructions, not a specific model's compliance
with them — it is the applicable check for the parts of Phase 3 this session
could perform.

## Results

| # | Scenario | Verdict | Governing text |
| --- | --- | --- | --- |
| 1 | F3-Nation admin vs. Slack admin | Pass | `augmentations/f3-nation-admins.md` roster + `collected:` header; `f3-nation-operations.md` §Critical role distinctions; `query-policy.md` §Authority boundaries; resident in `project-instructions.md` ("Authority is not transferable") |
| 2 | Ambiguous mention-index entry | Pass | `ingestion-contract.md` §Identity rules ("Never merge an `ambiguous` entry"); resident in `project-instructions.md` ("Identity") |
| 3 | Canvas with empty `modification_history` | Pass | `ingestion-contract.md` §Canvas/file currency ranking (critical-asymmetry paragraph); resident in `project-instructions.md` ("Canvas/file currency") |
| 4 | Conflicting `topic`/`purpose` | Pass | `ingestion-contract.md` §Channel context fields; resident in `project-instructions.md` ("Channel fields") |
| 5 | Missing extracted content (`has_content: false`) | Pass in one-off mode; **gap in Project mode** | `ingestion-contract.md` §Digest and file sidecar (`archive_status` values). Not restated in `project-instructions.md` — see Finding F1. |
| 6 | Dated augmentation conflict | Pass | `query-policy.md` §Dated augmentation evidence + `Contested` label; resident in `project-instructions.md` ("Dated augmentations", "Confidence labels") |
| 7 | Digest reference without matching sidecar record | Pass | `ingestion-contract.md` §Sidecar asymmetry ("gap. Report it explicitly."); resident in `project-instructions.md` ("Sidecar asymmetry") |
| 8 | Sidecar record without current digest reference | Pass | `ingestion-contract.md` §Sidecar asymmetry ("expected steady state... report as a count"); resident in `project-instructions.md` ("Sidecar asymmetry") |
| 9 | Former/current role distinction | Pass | `query-policy.md` §Evidence order ("Do not report former... as current") + `Former` label; resident in `project-instructions.md` ("Confidence labels") |
| 10 | Authority scope confusion (Site Q vs. Slack admin) | Pass | `query-policy.md` §Authority boundaries + §Question routing; resident in `project-instructions.md` ("Authority is not transferable") |
| 11 | Vacant vs. Not identified | Pass in one-off mode; **gap in Project mode** | `query-policy.md` §Current regional SLT report ("Mark a required role `Vacant` only when Slack explicitly says it is open or unfilled. Otherwise mark it `Not identified`"). Not restated in `project-instructions.md` — see Finding F2. |
| 12 | Deployment-mode instruction residency (sidecar asymmetry / ambiguous-merge) | Pass | `project-instructions.md` states both rules directly ("Sidecar asymmetry", "Identity"); a Project session answers correctly for these two without the retriever surfacing `query-policy.md`/`ingestion-contract.md` |

10 of 12 scenarios pass outright. Scenarios 5 and 11 pass for the one-off
session mode (`session-preamble.md` + full uploaded context, where every
document is in context) but expose a genuine residency gap in Project mode,
the same failure class flagged by `REVIEW-2026-08-06.md` P1-5: a rule that
must apply to every answer but lives only in a knowledge file is only
available when the retriever happens to surface that file for that specific
question.

## Findings (Phase 3 remediation, not applied ad hoc per validation-set.md §Running the set step 5)

### F1 — `archive_status` semantics are not resident in `project-instructions.md`

`ingestion-contract.md` §Digest and file sidecar defines `has_content: false`
as "no text was ever extractable... inspect `archive_status` for why" and
enumerates the four `archive_status` values. `project-instructions.md`
mentions the sidecar join key and the cumulative-sidecar asymmetry but never
mentions `has_content` or `archive_status`. In a ChatGPT Project, if the
knowledge-file retriever does not surface `ingestion-contract.md` for a
"what does this file say" question, the model has no resident basis to
distinguish "never extractable, check why" from "the source itself was
empty" — the exact wrong conclusion scenario 5 exists to prevent.

**Recommendation:** add one short bullet to `project-instructions.md`
(e.g. under "Sidecar asymmetry" or as its own line): `has_content: false`
means text was never extractable for this file, not that the source was
empty — check `archive_status` (`content_extracted`, `unsupported_type`,
`no_blob`, `tombstone`) for why. Track as a bd issue rather than editing the
pack in this session.

### F2 — The `Vacant`/`Not identified` distinction is not resident in `project-instructions.md`

`query-policy.md` §Current regional SLT report states the rule precisely:
mark a required role `Vacant` only when Slack explicitly says it is open or
unfilled, otherwise `Not identified`. This is not a confidence label (it is
absent from `project-instructions.md`'s "Confidence labels" bullet, which
correctly only lists `Confirmed`/`High`/`Medium`/`Working signal`/`Former`/
`Contested`/`Unresolved`) and is not restated anywhere else in
`project-instructions.md`. In Project mode, if `query-policy.md` is not
retrieved for a leadership-vacancy question, the model has no resident rule
against defaulting to `Vacant` for a role with no evidence — precisely
scenario 11's failure mode.

**Recommendation:** add one short line to `project-instructions.md`, e.g.
under "Question routing" or as a new short bullet: a role with no evidence
addressing it is `Not identified`, not `Vacant` — use `Vacant` only when
Slack evidence explicitly states the role is open or unfilled. Track as a bd
issue rather than editing the pack in this session.

## Outcome

Per `MIGRATION-PLAN.md` Phase 3 exit criteria: the validation set does not
pass cleanly — two scenarios (5, 11) surface recorded remediation work
rather than a clean pass, which the exit criteria explicitly allow ("passes
or creates recorded remediation work"). No pack document was edited and no
legacy document was retired in this session. A live upload-and-ask
validation run (real digest/profile/sidecar/augmentation set, actual
ChatGPT session and Project) remains outstanding and should be performed
before or shortly after [sat-ejk.4](../..) integration, and re-run after any
schema or query-policy change per `validation-set.md`.
