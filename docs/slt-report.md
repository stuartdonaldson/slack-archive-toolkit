Using only the uploaded Slack digests, Slack user-profile data, and supporting context files, produce a current Senior Leadership Team report for each included F3 region.

Begin with a brief methodology note that states:

* The exact Slack-data date range covered.
* The report is derived from Slack messages, thread replies, channel descriptions or topics, canvases/files, structured digest fields, and Slack user-profile fields such as display name and title.
* Explicit Slack announcements and maintained references take priority over profile-derived role signals.
* Profile titles and display names may be stale and are treated as supporting evidence unless confirmed elsewhere.

Create one table with these columns:

| Region | Position | F3 Name | Provenance / Confidence |

Requirements:

* Include every region represented in the uploaded data.
* Include the Puget Sound super-region separately.
* For each region, always include rows for:

  * Nantan
  * Weasel Shaker
  * 1st F
  * 2nd F
  * 3rd F
* Add rows for other regional leadership roles only when identified in the uploaded data, such as:

  * Comms Q
  * Comz Q
  * IT Q
  * Slack Comms Q
  * Social Media Q
  * Expansion Q
  * Other explicitly identified SLT roles
* Do not create empty rows for optional roles.
* Use F3 names rather than real names.
* For every named role, provide a direct clickable Slack link to the strongest available provenance.
* Prefer evidence in this order:

  1. Canvas/file, channel topic, or channel description
  2. Explicit leadership announcement or transition post
  3. Structured digest field
  4. Message or thread reply
  5. Slack profile title
  6. Slack display name
* Use the most recent evidence when roles changed during the covered period.
* Do not list former, emeritus, retired, or replaced leaders as current.
* Mark a required role as `Vacant` only when Slack explicitly says it is open or unfilled.
* Mark a required role as `Not identified` when the uploaded data does not provide sufficient current evidence.
* Do not infer that a generic admin, Q, Site Q, or active participant is part of the regional SLT.
* When evidence conflicts, report the latest stronger source and briefly note the conflict.
* If a role relies only on a profile title or display name, label it `Profile signal; may be stale`.
* Do not expose Slack user IDs unless needed to explain an unresolved identity.
* Report dates and times in Pacific time.
* Keep the report concise, consistent, and source-grounded.

After the table, include only a short `Qualifications` section covering material uncertainties, recent transitions, vacancies, or profile-only role assignments.

