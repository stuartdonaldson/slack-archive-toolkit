Generate an F3 Puget Sound regional newsletter from the attached Slack digest export.

Use only information present in the export. Do not invent details. The digest may include messages, channels, direct Slack message URLs, and leadership information inferred from visible Slack display names.

Write for the F3 Puget Sound region. Lead with the F3 Puget Sound workspace/region first, then include related updates from other regional workspaces such as Cascades, Kirkland, Redmond, Tundra, or others when they are relevant to Puget Sound PAX.

Mention only briefly that the newsletter was built from Slack postings. Do not describe the ingestion, parsing, or analysis process.

Output a concise Markdown newsletter.

# Requirements

## General style

* Write in an engaging, practical, community-oriented newsletter style.
* Do not write a data report.
* Avoid duplicate reports. Merge repeated posts, reminders, replies, and follow-ups into one coherent update per event/topic.
* Prefer useful regional awareness over exhaustive coverage.
* Use F3 names/display names as shown in the export.
* Use direct Slack message links from `message_url` when available.
* When referencing a Slack post or channel, embed the actual Slack message link using Markdown syntax, for example: `[1st-f](https://...)`.
* Cite the F3 name/display name of the person who posted the source item.
* If source details are unknown or a link is unavailable, say so briefly.

## Regional structure

* Start with `## F3 Puget Sound`.
* Then create a separate `## F3 [Region]` section for every regional workspace that has meaningful newsletter-worthy content.
* Do not collapse Redmond, Tundra, or other regions into “Other regional notes” when they have enough content for their own section.
* A region deserves its own section if it has leadership data, event channels, cross-region events, major announcements, or multiple newsletter-worthy posts.
* Order regions by relevance to Puget Sound PAX, not alphabetically.
* Use an `## Other regional notes` section only for small one-off items that do not justify a full region section.

## Events

* Infer event title, date, time, location, signup/contact link, and relevant channel from the Slack post text when available.
* Do not require structured event fields; they may not exist.
* If an event’s date, time, location, or contact is not clear, say what is missing rather than guessing.
* For every event, include date, time, location, and signup/contact link when available.
* Convert timestamps to Pacific time if needed for readable newsletter copy.
* Be careful with relative dates like “tomorrow,” “next week,” or “this Friday.” Resolve them using the post date when possible. If not possible, leave the detail uncertain.
* For cross-region events, identify the canonical/original event post when possible.
* If other regions reference the same event, merge those references into one event item and cite the canonical source first.
* Include the event under the host/canonical region. Also mention it in a short “Cross-region events to know” section if it is broadly relevant to Puget Sound PAX.
* Do not lose event details from the canonical source just because another region’s repost or reference is less complete.

## Leadership Team Snapshot

* Include a “Leadership Team Snapshot” section for each regional section.
* Use the digest’s leadership section when present.
* Leadership may be inferred from Slack display names. Treat visible display-name roles as practical working signals because they are public and likely to be self-correcting.
* If `leadership.by_region` exists, use that first.
* If only raw leadership matches exist, aggregate by `possible_region + possible_f3_name + position`.
* Do not list duplicate workspace-local accounts separately.
* Include role, person/F3 name, and basis when useful.
* Do not overstate confidence. Use wording such as “inferred from display name” when the role comes from profile/display-name data.  Stating inferred is sufficient we do not need to ask for confirmation or repeat the source display name.
* If no leadership information is available for a region, write: “Need a maintained regional leadership reference or role-bearing Slack profiles.”

## Identity handling

* People profiles are not unified across regions/workspaces.
* Do not merge people across workspaces unless the export strongly supports the match through matching F3 name, role, or derived leadership fields.
* Prefer F3 name/display name over real name in newsletter copy.
* Exclude bots from leadership and author attribution unless the bot post is the only available source for an item.

# Suggested structure

# F3 Puget Sound Regional Newsletter — [Month Year]

*Built from Slack postings.*

## F3 Puget Sound

### What’s been happening

### What’s coming up

### Leadership Team Snapshot

## F3 [Region Name]

Create one section like this for each additional regional workspace with meaningful newsletter-worthy content.

### What’s been happening

### What’s coming up

### Leadership Team Snapshot

## Cross-region events to know

Use this section for events that are relevant across multiple regions. Cite the canonical/original event source first, then mention other regional references only if helpful.

## Other regional notes

Use only for minor one-off items from regions that do not justify a full section.

## Items needing clarification

List only important missing details, such as:

* Event date/time/location not clear
* Missing signup/contact link
* Leadership role inferred but not confirmed
* Region has no usable leadership data
* Source post lacks a usable Slack message link
