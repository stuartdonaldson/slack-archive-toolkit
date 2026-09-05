# Validation set

Golden questions for re-running against a matched digest, profile export, cumulative sidecar, and applicable augmentations, per [MIGRATION-PLAN.md Phase 3](MIGRATION-PLAN.md#phase-3--validate-the-pack). Each entry states the **expected evidence type and confidence treatment**, not a fixed factual answer — answers change with the data, but the behavior should not.

Re-run this set before integration ([sat-ejk.4](../..)) and again after any digest/profile/sidecar schema change or query-policy change.

| # | Scenario | Prompt | Expected behavior |
| --- | --- | --- | --- |
| 1 | F3-Nation admin vs. Slack admin confusion | "Who can fix the F3-Nation bot for [region]?" | Answers from `uploads/supplemental/f3-nation-admins.md`, not from Slack workspace `slack_roles`; states the roster's `collected:` date; does not imply Slack admin or Site Q status. |
| 2 | Ambiguous mention-index entry | "Is [display name A] the same person as [display name B]?" where the digest's mention index marks the pair `ambiguous` | Refuses to merge; reports both identities separately; does not use name similarity to override `ambiguous`. |
| 3 | Canvas with empty `modification_history` | "Is [canvas] out of date?" for a canvas whose `modification_history` is empty | Does not conclude staleness from the empty history alone; checks `content_changed_at`; if both are uninformative, states currency is unknown rather than assuming staleness. Cites `modification_history_completeness: "partial"`. |
| 4 | Conflicting `topic`/`purpose` | "What is [channel] for?" where `topic` and `purpose` state different things | Reports both fields; treats `topic` as the higher-priority signal for the operational conclusion; does not discard or silently prefer only one. |
| 5 | Missing extracted content | "What does [canvas/file] say?" for a file reference with `has_content: false` | States that no text was ever extractable for this snapshot; reports `archive_status` as the reason; does not claim the source itself was empty. |
| 6 | Dated augmentation conflict | A question where `uploads/supplemental/f3-nation-admins.md` and a newer dated Slack announcement disagree | Applies the recency/fidelity rule in `uploads/query-policy.md`; labels the answer `Contested`; states both sources and both dates; does not silently pick one. |
| 7 | Digest without matching sidecar record | "What does [canvas] say?" for a `has_content: true` file reference with no sidecar match | Reports the missing match explicitly as a gap (not a normal condition); does not fabricate content. |
| 8 | Sidecar record with no current digest reference | Initial ingestion validation on an upload where the sidecar has entries outside the digest's window | Reports the count as expected steady state, not a warning or a data-quality problem. |
| 9 | Former/current role distinction | "Who is the current [SLT role] for [region]?" where a canvas or message marks a prior holder "former" | Excludes the former holder from the current-role answer; reports them only in a `Former` label if relevant to the question. |
| 10 | Authority scope confusion | "Does [Site Q] have Slack admin rights?" | States the two authorities are independent; does not infer one from the other; reports the answer for each authority separately or as unresolved if neither is established. |
| 11 | Vacant vs. not identified | "Who is the current [required SLT role] for [region]?" where no evidence at all addresses the role | Labels the role `Not identified`, not `Vacant`, unless Slack evidence explicitly states the role is open/unfilled. |
| 12 | Deployment-mode instruction residency | In a ChatGPT Project (not a one-off session), ask a question whose governing rule (e.g. sidecar asymmetry, ambiguous-merge prohibition) is stated only in `query-policy.md` | The Project instruction box (`project-instructions.md`) alone is sufficient to answer correctly, without requiring the knowledge-file retriever to have surfaced `query-policy.md` for that specific question. |

## Running the set

1. Load `project-instructions.md` (Project mode) or `session-preamble.md` plus the context files (one-off mode).
2. Upload a matched digest, profile export, and sidecar; include the augmentations under test.
3. Ask each prompt above (adapted with real channel/region/canvas names from the uploaded data).
4. Record whether the response matches the expected behavior, not whether the specific named answer is correct.
5. Log any mismatch as a Phase 3 remediation item rather than editing the pack ad hoc.
