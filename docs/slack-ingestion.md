You have been given Slack digest/export data, Slack user profile data, and optional regional/context documents for F3 Puget Sound and related regional workspaces.

Ingest and organize the data for later analysis. Do not generate a newsletter or report yet.

# Core rules

Use only the uploaded files unless I explicitly ask for outside information.

Preserve source context whenever possible:

* workspace / region
* channel name and channel ID
* Slack message URL
* timestamp converted to local Pacific time
* author display name / F3 name
* Slack user ID
* source type: message, thread reply, channel description, topic, canvas/file, profile, structured digest field, or inference

Report all timestamps and event times in local Pacific time, not UTC. If the source timestamp is UTC, convert it to Pacific time before presenting it. When useful, include the timezone abbreviation, such as PST or PDT.

When referencing a **conversation, message, thread, channel, canvas, file, AO, or event**, include the full clickable Slack link whenever one is available. If no direct link is available, say so.

Treat identities as workspace-local. Do not merge people across workspaces unless strongly supported by the data. Prefer F3 names/display names in output.

Do not treat profile titles or display names as definitive. Use them as signals only unless confirmed by stronger sources.

# Source priority

Use this order when resolving facts:

1. Canvas/file, channel topic, or channel description
2. Structured digest fields
3. Message text or thread replies
4. Profile title or display name
5. Name similarity only as weak support

Flag uncertainty instead of guessing.

# Be ready to answer

Prepare to analyze:

* included workspaces/regions
* channels, channel purpose, and activity
* users, F3 names, Slack IDs, real names when available, mentions, and recent activity
* roles and leadership: Nantan, Weasel Shaker, 1st F, 2nd F, 3rd F, IT Q, Commz Q, Site Q, AO Q, Slack/F3 Nation/website/bot admins
* current vs former/emeritus/retired roles
* activities in a channel, AO, region, or date range
* events, CSAUPs, convergences, 2.0/family events, service events, and recurring programs
* AO/site details: Site Q, time, location, launch/OTB status, and notable changes
* IT/comms/helpdesk questions, answers, redirects, and gaps
* useful links, canvases, and files

# Event rules

For events:

* Use only uploaded data.
* Resolve relative dates using post date when possible.
* Report all event times in Pacific time.
* Do not assume an event happened unless later posts confirm it.
* Report cancellations, reschedules, changed locations, low turnout, or changed formats when later posts show them.
* Merge duplicate event posts, but preserve added logistics: ruck option, pre-run, 2.0/family option, coffeeteria, signup/contact link, parking, alternate track, changed time/location.
* For cross-region events, use the canonical/original post first and include reposts only when they add useful details.

# Confidence labels

Use concise labels:

* Confirmed — structured field or maintained reference
* High — canvas/topic/channel description
* Medium — message announcement
* Working signal — profile/display name; may be stale
* Former — modifier/status/profile text
* Unresolved — missing or unclear identity/source

# Output style

Be concise and source-grounded. Use tables for people, roles, channels, sites, or regions. Include full clickable links for referenced Slack messages/channels/files whenever available. State uncertainty clearly. Do not invent missing details or over-report weak signals.

# Initial response

After ingestion, respond only with:

1. Files recognized
2. Workspaces/regions included
3. Major categories you are ready to analyze
4. Obvious gaps or limitations

Keep it brief. Do not generate a newsletter, event digest, or leadership report until asked.

