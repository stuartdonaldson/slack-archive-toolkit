# Query policy

Canonical home for: evidence precedence, conflict resolution, confidence labels, authority boundaries, question routing, and standard report tables. This is the **only** canonical source for general evidence and reporting rules — do not restate or vary this ranking elsewhere.

Use this guide when answering questions from uploaded Slack digest exports, profile rosters, file-content sidecars, and dated manual augmentations. It defines where to look for common F3 leadership and AO/site questions, how to resolve conflicting signals, and how to present results. Read [ingestion-contract.md](ingestion-contract.md) first for schema and sidecar mechanics.

## Shared reporting rules

Start every report with a brief methodology note that states:

* the exact Slack-data date range covered by the supplied digest files;
* the supplied source types used (messages, thread replies, channel topics or purposes, canvases/files, structured digest fields, profile fields, and any dated augmentation); and
* that all reported dates and times are Pacific time.

Use only the supplied data. Prefer F3 names. Include a direct clickable Slack link for each material claim whenever one is available. Do not expose Slack user IDs unless they are necessary to explain an unresolved identity.

Current maintained references and explicit announcements take priority over profile-derived signals. Profile titles and display names may be stale: label a conclusion that relies only on either as `Working signal — profile/display name; may be stale`.

## Evidence order

Use the newest, strongest evidence that establishes the fact, in this order:

1. Current extracted content of a maintained canvas or document from the matching sidecar
2. Current channel `topic` or `purpose` (check both — see [ingestion-contract.md](ingestion-contract.md#channel-context-fields))
3. Direct announcement from the responsible person, organizer, role holder, or system owner
4. Structured digest fields
5. Message text or thread replies
6. File metadata without extracted content
7. User profile title or display name
8. Inference or name similarity

Multiple reposts do not increase authority. A newer direct announcement may override an older maintained reference when it clearly records a change. When a newer, weaker source merely repeats an older source, cite the stronger source.

Do not report former, emeritus, retired, replaced, temporary, or event-specific roles as current. Distinguish:

* current role
* former, emeritus, or retired role
* temporary or event-specific role
* informal leadership
* inferred role

### Dated augmentation evidence

A dated manual augmentation (see `augmentations/`) is conditional evidence, not a fixed rank:

* It is the **primary** source for a fact the Slack exports structurally cannot express, such as the F3-Nation regional administrator roster.
* When the Slack exports *can* express the same fact, treat the augmentation immediately below rank 5 (message/thread evidence) and apply recency and source strength rather than silently overriding the Slack record.
* Never present an augmentation-derived fact without its collection date.
* On conflict with dated Slack evidence, compare dates: weigh the augmentation's `collected:` date against the competing evidence's own date (a message's post date, a canvas's currency per the currency ranking, or a profile's last-observed date). Take the more recent as the working answer, report the losing source alongside it, and reflect the conflict in the confidence label.

Augmentation `fidelity` is recommended guidance, not a mandatory schema field. When present, use it to bound the best ordinary confidence the augmentation can support:

| `fidelity` | Meaning | Maximum ordinary confidence |
| --- | --- | --- |
| `system-extracted` | Transcribed directly from a system screen or maintained system record. | `High` for its collection date. |
| `hand-compiled` | Assembled manually from several sources. | `Medium`. |
| `recalled` | Based on memory or an informal report. | `Working signal`. |

## Confidence labels

Use concise confidence labels where uncertainty matters — do not attach them mechanically to every sentence.

| Label | Use when |
| --- | --- |
| `Confirmed` | A maintained reference or explicit fact directly establishes the answer. |
| `High` | A current canvas, file, channel topic/purpose, or authoritative announcement supports the answer. |
| `Medium` | A direct message announcement or well-supported thread establishes the answer. |
| `Working signal` | Only a profile title or display name supports the answer; it may be stale. |
| `Former` | The source explicitly marks the role as former, emeritus, retired, or replaced. Do not list it as current. |
| `Contested` | Sources materially disagree but a working answer is still possible. State the selected answer (the more recent/stronger source), the conflicting source, and both dates. |
| `Unresolved` | Evidence is missing, ambiguous, conflicting, or insufficient to support even a contested answer. |

When materially conflicting sources still permit a working answer, use `Contested`. Use `Unresolved` only when the conflict cannot support an answer at all. Never resolve a conflict silently.

## Authority boundaries

Do not treat these roles as equivalent or as evidence for one another:

* **Slack workspace admin/owner** — controls Slack workspace governance, permissions, and app installation. Source: workspace-local user-profile `slack_roles`.
* **F3-Nation app/region admin** — configures F3-Nation app settings for that region via `/f3-nation-settings`. Source: a maintained/manual F3-Nation app-admin reference for that region (see `augmentations/f3-nation-admins.md`).
* **Regional SLT roles** (Nantan, Weasel Shaker, 1st F, 2nd F, 3rd F, and similar) — lead the region. Regional in scope.
* **Site Q / AO Q / OIC** — scoped to a specific AO or site, not the whole region.

One role is not evidence of another. Current maintained Slack evidence outranks a dated manual augmentation when they conflict — see [Dated augmentation evidence](#dated-augmentation-evidence).

## Question routing

Before reporting, identify the requested authority and scope: regional leadership, AO ownership, Slack administration, F3-Nation administration, or channel context. Search the appropriate maintained sources first, then validate recency and transitions in messages.

| Question | Look first | Do not infer from |
| --- | --- | --- |
| Who holds a current regional SLT role? | Maintained regional leadership canvas/file, regional channel topic/purpose, a direct transition announcement, then `leadership.by_region` or message evidence | Generic Q activity, membership, Slack admin status, or AO/Site Q status |
| Who runs an AO or site? | The AO channel's topic/purpose/description, maintained AO/Site Q reference, then an explicit Site Q transition or message | F3-Nation app admin list, Slack workspace admin list, generic regional leadership, or attendance/activity |
| What is the AO's schedule and location? | AO channel topic/purpose, maintained canvas/file, canonical schedule post, then a recent explicit update | A recurring pattern inferred from backblasts, old announcements, or an unstated location |
| Who controls Slack workspace administration? | Workspace-local user-profile `slack_roles` | F3-Nation app admin status, Site Q status, or regional SLT role |
| Who can configure the F3-Nation bot? | Maintained/manual F3-Nation app-admin reference for that region | Slack workspace admin status, Site Q status, or ordinary regional leadership |
| What does a channel exist for? | Its current topic and purpose, considered independently, then an explicit channel-maintainer explanation | Channel name alone or activity patterns |

Regional roles such as Nantan, Weasel Shaker, 1st F, 2nd F, 3rd F, Comz Q, and IT Q apply to a region. Site Q, AO Q, and OIC are AO-scoped: associate them with the specific AO/channel, not the whole region.

## Current regional SLT report

When asked for a current Senior Leadership Team report, include every region represented in the supplied data and list the Puget Sound super-region separately when present. Include the required positions in this order: Nantan, Weasel Shaker, 1st F, 2nd F, and 3rd F. Add other regional leadership roles only when the supplied data identifies them, such as Comms/Comz Q, IT Q, Slack Comms Q, Social Media Q, or Expansion Q.

Use this table:

| Region | Position | F3 Name | Provenance / Confidence |
| --- | --- | --- | --- |

For each named role, link the strongest available provenance in the final column. Mark a required role `Vacant` only when Slack explicitly says it is open or unfilled. Otherwise mark it `Not identified` when current evidence is insufficient. Do not add empty rows for optional roles or treat a generic admin, Q, Site Q, or active participant as part of the regional SLT.

After the table, include only a short `Qualifications` section for material uncertainties, recent transitions, vacancies, profile-only assignments, or source conflicts.

## AO and site report

When asked about AOs, report each AO in the region/workspace where its channel appears. Preserve the channel's topic and purpose separately; `description` can be a convenience merge and may omit one of them. If the topic and purpose conflict, prefer the topic for the operational conclusion while reporting the purpose when it adds material context.

Use this table:

| Region | AO / Slack channel | Site Q | Slack topic | Slack purpose | When they meet | Where | Provenance / Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |

Include a row when the AO/site itself is identifiable; leave an unsupported operational field as `Not identified` rather than guessing. Do not require that every AO have a Site Q, time, or location before reporting it. Use a canonical schedule or location source when available, and identify a recent cancellation, reschedule, or location change rather than silently blending old and new information.

For an AO-only answer, omit regional SLT rows. For a combined regional briefing, present the SLT table first and the AO table second, then one short `Qualifications` section covering both.

## Answering the query

Before reporting, identify the requested authority and scope: regional leadership, AO ownership, Slack administration, F3-Nation administration, or channel context. Search the appropriate maintained sources first, then validate recency and transitions in messages. Keep conclusions source-grounded: distinguish a confirmed current assignment from a profile-only working signal, an explicit vacancy, a contested conflict, and an unanswered question.
