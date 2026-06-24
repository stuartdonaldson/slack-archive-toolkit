## Recommended source JSON improvements

### 1. Make the export one valid JSON document

Current issue: the file appears to contain multiple consecutive JSON objects rather than one top-level object or array. That is parseable with custom logic, but less convenient.

Preferred structure:

```json
{
  "schema_version": "slack-newsletter-export-v1",
  "generated_at": "2026-06-22T22:34:45Z",
  "export_scope": {
    "from": "2026-06-01",
    "to": "2026-06-30",
    "time_zone": "America/Los_Angeles"
  },
  "workspaces": [],
  "channels": [],
  "messages": [],
  "reference_data": {}
}
```

This makes ingestion straightforward and avoids ambiguity.

---

### 2. Include stable workspace, region, and channel metadata on every message

For newsletter generation, every message should carry enough context to stand alone.

Add these fields to every message:

```json
{
  "workspace_id": "T...",
  "workspace_name": "f3pugetsound",
  "region_name": "F3 Puget Sound",
  "channel_id": "C...",
  "channel_name": "all-f3-puget-sound",
  "channel_type": "regional_announcement",
  "message_url": "https://f3pugetsound.slack.com/archives/C.../p..."
}
```

Most important improvement: **include `message_url` directly**. Do not require the LLM to construct it from timestamp and channel ID.

---

### 3. Preserve both UTC time and local display time

For events and newsletter copy, local time matters.

Add:

```json
{
  "posted_at_utc": "2026-06-17T15:12:00Z",
  "posted_at_local": "2026-06-17T08:12:00-07:00",
  "posted_date_local": "2026-06-17",
  "posted_time_local": "8:12 AM"
}
```

For events, also add extracted event time fields when known:

```json
{
  "event": {
    "title": "SEA-SAUP",
    "start_date": "2026-06-27",
    "start_time": "4:00 AM",
    "timezone": "America/Los_Angeles",
    "location": "Discovery Park, Magnolia",
    "duration": "about 5 hours"
  }
}
```

If the exporter cannot reliably infer event time, leave fields null rather than guessing.

---

### 4. Add a lightweight message classification layer

The LLM can classify, but the exporter can help by preserving signals.

Suggested `message_kind` values:

```json
"message_kind": "announcement | event | preblast | backblast | reply | chatter | admin | leadership | classified | unknown"
```

Suggested `newsletter_relevance`:

```json
"newsletter_relevance": "high | medium | low | exclude"
```

Suggested `topic_tags`:

```json
"topic_tags": [
  "CSAUP",
  "convergence",
  "2nd-F",
  "fundraising",
  "leadership",
  "challenge",
  "AO",
  "onboarding"
]
```

Do not summarize in the export. Just provide metadata and raw content.

---

### 5. Add thread structure explicitly

For aggregation, thread context matters. A post and its replies should be clearly connected.

```json
{
  "message_id": "1772097945.210359",
  "thread_id": "1772097945.210359",
  "is_thread_parent": true,
  "reply_count": 8,
  "replies": [
    {
      "message_id": "1772098010.123456",
      "thread_id": "1772097945.210359",
      "is_thread_parent": false
    }
  ]
}
```

Even better: flatten all messages into one `messages` array, but include `thread_id`, `parent_message_id`, and `message_url` for each.

---

### 6. Include author profile metadata

For citing posters and leadership roles, display names alone are not enough.

```json
{
  "author": {
    "user_id": "U...",
    "display_name": "Columbia",
    "real_name": "Optional if allowed",
    "f3_name": "Columbia",
    "workspace_admin": false,
    "known_roles": [
      {
        "role": "Nantan",
        "region": "F3 Cascades",
        "source_url": "https://..."
      }
    ]
  }
}
```

If roles are not known, keep `known_roles: []`.

---

### 7. Add maintained regional reference data

Leadership was the hardest part because it should not be inferred from casual posts.

Add a `reference_data.regions` section:

```json
{
  "reference_data": {
    "regions": [
      {
        "region_name": "F3 Puget Sound",
        "workspace_name": "f3pugetsound",
        "leadership_reference_url": "https://...",
        "leadership_last_verified": "2026-06-01",
        "leadership_team": [
          {
            "position": "Nantan",
            "f3_name": "Example",
            "slack_user_id": "U...",
            "source_url": "https://..."
          },
          {
            "position": "Weasel Shaker",
            "f3_name": "Example",
            "slack_user_id": "U...",
            "source_url": "https://..."
          }
        ]
      }
    ]
  }
}
```

If unknown:

```json
{
  "region_name": "F3 Puget Sound",
  "leadership_reference_url": null,
  "leadership_team": [],
  "missing_reference_note": "Need authoritative maintained leadership roster."
}
```

This prevents the newsletter from overclaiming.

---

### 8. Add AO/event reference data

For F3 newsletters, AOs and recurring workouts matter.

```json
{
  "aos": [
    {
      "ao_name": "Thunderdome",
      "region_name": "F3 Kirkland",
      "usual_day": "Tuesday",
      "usual_time": "5:30 AM",
      "location": "Known location",
      "map_url": "https://...",
      "slack_channel": "ao-thunderdome"
    }
  ]
}
```

Then when a post says “VQ at Thunderdome,” the newsletter can say what/where it is without guessing.

---

### 9. Preserve external and internal links separately

Right now links are embedded in text and may need parsing.

Add:

```json
{
  "links": [
    {
      "url": "https://f3pugetsound.slack.com/archives/...",
      "label": "King/Kind of the Climb",
      "link_type": "slack_message"
    },
    {
      "url": "https://strava.app.link/...",
      "label": "30-mile challenge",
      "link_type": "external"
    }
  ]
}
```

This improves source-linking and makes the final Markdown cleaner.

---

### 10. Add deduplication hints

Many posts are reminders or follow-ups for the same event. Add optional fields:

```json
{
  "canonical_event_key": "f3pugetsound-2026-06-27-sea-saup",
  "related_message_ids": [
    "177...",
    "177..."
  ],
  "is_primary_announcement": true
}
```

If the exporter cannot infer this, leave it out. But even simple matching by event title/date would help.

---

## Recommended organizational improvements

### 1. Maintain one regional leadership roster

Create one authoritative leadership reference per region, ideally in Slack Canvas, Google Doc, website page, or GitHub-style YAML/JSON.

Minimum fields:

| Field                | Example                    |
| -------------------- | -------------------------- |
| Region               | F3 Puget Sound             |
| Position             | Nantan                     |
| F3 Name              | Example                    |
| Slack handle/user ID | `U...`                     |
| Term/status          | Current                    |
| Last verified        | 2026-06-01                 |
| Maintainer           | Weasel Shaker / Comz / SLT |

The export should include this reference or a link to it.

---

### 2. Use consistent announcement channels

For newsletter processing, it helps if each region has a known announcement channel, for example:

* `all-f3-pugetsound`
* `all-f3-cascades`
* `all-f3-kirkland`
* `newsletter-submissions`
* `events`
* `csaup`
* `2nd-f`

Then the tool can prioritize those over general mumblechatter.

---

### 3. Encourage event posts to use a simple template

Suggested Slack template:

```markdown
EVENT:
Title:
Date:
Time:
Location:
Region:
AO:
Who should attend:
What to bring:
Signup / HC link:
Contact:
```

This would dramatically improve event extraction.

---

### 4. Separate “announcement,” “discussion,” and “classifieds” content

Newsletter content becomes cleaner if posts are categorized at the source:

* Announcements/events
* Backblasts
* Challenges
* 2nd-F / service
* Classifieds
* General chatter

Even if the exporter only tags by channel, that helps.

---

### 5. Keep original text, but add derived metadata

Do not replace raw Slack content with summaries. Keep the original post and add structured fields beside it. That gives the LLM evidence while still making processing easier.

---

## Highest-value schema changes

If you only change five things, do these:

1. Export as **one valid JSON object**.
2. Include **actual `message_url`** on every message.
3. Include **workspace, region, channel ID, and channel name** on every message.
4. Add **event fields**: title, date, time, location, signup/contact if known.
5. Add **maintained leadership reference data** per region.
