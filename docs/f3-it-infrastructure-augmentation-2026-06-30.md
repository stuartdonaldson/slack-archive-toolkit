# F3 IT Infrastructure Augmentation

_Source date: manual extraction as of 2026-06-30_

## How to use this with LLM uploads

Upload the companion JSON file, `f3-it-infrastructure-augmentation-2026-06-30.json`, alongside the normal Slack digest and user profile exports:

1. `f3-digest-2026-06-30.json`
2. `f3-user-profiles-2026-06-30.json`
3. `f3-it-infrastructure-augmentation-2026-06-30.json`

Use the JSON file as a structured augmentation layer for queries about F3 IT infrastructure, F3-Nation Slack bot configuration, regional bot admins, and maintenance ownership.

This Markdown file is the human-readable companion. It explains what the JSON is for and how it should be interpreted. The JSON is the preferred machine-ingestion format.

## Purpose

The Slack digest and user profile exports are strong for visible Slack activity, channel metadata, profile data, and Slack workspace roles. They do **not** contain the F3-Nation app's internal regional admin list.

The companion JSON fills that gap by adding manually extracted F3-Nation app admin data and bot configuration context.

Use it when answering questions about:

- `/f3-nation-settings`
- F3-Nation Slack bot configuration
- regional bot admins
- calendar, AO, event, Q lineup, preblast, and backblast settings
- Welcomebot
- reporting
- achievements
- downrange settings
- custom fields
- Paxminer migration/mapping
- bot-related infrastructure and maintenance responsibility

Do **not** use it as a replacement for the digest or profile exports.

## Critical role distinctions

The same person may appear in more than one role, but the roles are distinct.

| Role | Source | Meaning | Do not confuse with |
|---|---|---|---|
| Slack workspace admin/owner | Slack profile export | Controls Slack workspace administration, permissions, app installation, and workspace governance | F3-Nation app admin, Site Q, regional leadership |
| F3-Nation app / region admin | Manual `/f3-nation-settings` extraction | Can configure F3-Nation app settings for that region | Slack workspace admin, Site Q, regional leadership |
| Site Q | SLT settings, AO/channel metadata, leadership data, or messages | AO-level leadership / workout ownership | Slack admin or F3-Nation app admin |
| Regional leadership | Maintained leadership data, channel descriptions, messages, or qualified profile/title hints | Human regional leadership such as Nantan, Weasel Shaker, 1st F, 2nd F, 3rd F, Comz | Slack admin, F3-Nation app admin, Site Q |

Key rule: **F3-Nation app admin ≠ Slack workspace admin ≠ Site Q.**

## What the F3-Nation Slack bot does

The F3-Nation Slack bot supports:

- `/backblast`
- `/preblast`
- `/f3-calendar`
- `/tag-achievement`
- `/f3-nation-settings`
- `/help`
- HC / un-HC buttons
- Take Q buttons
- edit backblast / preblast flows
- Strava attachment, if enabled
- Q lineup signup
- missing backblast lookup
- emergency info lookup
- downrange region/event lookup
- user profile management
- welcome messages
- Q lineup posts
- backblast/preblast reminders
- achievement notifications
- monthly region/AO reports
- calendar image posts

Most optional or automatic features are controlled per region by F3-Nation app admins through `/f3-nation-settings`.

## Who configures what

Most region-specific bot settings are configured by F3-Nation app admins.

Examples:

- Calendar settings
- Q lineups
- Calendar image posting
- Location/AO/event management
- Region info
- Region admin list
- SLT settings
- Site Q and leadership position assignments
- Preblast settings
- Backblast settings
- Strava toggle
- Editing lock
- Moleskin templates
- Automated preblast timing
- Backblast/preblast reminders
- HC announcement style and targets
- Backblast email settings
- Custom fields
- Welcomebot settings
- Reporting settings
- Downrange settings
- Achievement settings
- Paxminer mapping
- Migration/connect settings

Infrastructure-level items usually belong to F3 Nation dev/ops rather than regional admins:

- F3 Nation REST API
- Deployment credentials
- Slack bot token refresh
- Strava OAuth app credentials
- AWS S3
- SendGrid
- GCP Cloud Run
- Scheduled job runner
- Secret/password-gated admin menu actions

Slack workspace-level issues belong to Slack workspace owners/admins, not necessarily F3-Nation app admins.

Examples:

- Slack app installation permissions
- Slack workspace governance
- Workspace invite controls
- Slack channel administration
- Slack owner/admin roles

## F3-Nation app admins by region

These were manually extracted as of 2026-06-30. They may become stale.

| Region | Workspace | F3-Nation app admins | Notes |
|---|---|---|---|
| Puget Sound | `f3pugetsound` | CornFed; Voltaire; Sherpa; Columbia - Cascades Region Nantan; Schedule 1 | Bot/org admins, not necessarily Slack admins |
| Cascades | `f3cascades` | Radar; Columbia; Bunt; Flexo; Bunny | Bunt appeared twice in the supplied list and was de-duplicated |
| Kirkland | `f3kirkland` | Amadeus; Falsetto; Thimble; Crashdummy; Speedo; Sunflower; Retread; Montoya; skynet; Papercut; Voltaire; Indy; Pegleg (Seattle); Pogo; Needles; Tardy - Kirkland 3rd F | Bot/org admins, not necessarily Slack admins |
| Tundra | `f3tundra` | Moa; RBI; DreamWeaver; beltway; Snips; Jalapeño Tundra Nan’tan; Voltaire; Tinker Toy; Brexit; Moneypuck; LumberMack; Greywater; Pegleg (Seattle); MooseJaw; Salsa; schedule 1; cartwheel; Bugle; Hamm's | Lowercase `schedule 1` preserved from manual extraction; do not auto-merge with `Schedule 1` without confirmation |
| Seattle | `f3seattle` | Manual; Voltaire; Priceline; Doggy Paddle; Boo-Boo; Daisy Dukes; Oodles; Chum; Sea Level; Tap Out; Preroll; OldeEnglish; The Tank; Keystone; Bombadil; Turndown; WalkOn; Silicone; Palinka; Alimony; PumpNDump; Picante; Mr. Hand; Zima; Watson; Pylon; Pegleg; Cheese Coyote; Ipanema | Manual appeared twice in the supplied list and was de-duplicated |
| North Sea | `f3northsea` | Heeere’s Johnny; Voltaire; Bueller - Weaselshaker; sharkweek; Silo Nan'tan; Peekaboo | Bot/org admins, not necessarily Slack admins |
| Redmond | `f3redmond` | Not provided | Do not infer Redmond F3-Nation app admins from Slack admins, Puget Sound admins, leadership titles, or activity patterns |

## Query guidance

When asked **who can fix or configure the F3-Nation bot**, use the F3-Nation app admin list for the relevant region.

When asked **who controls the Slack workspace**, use the Slack owner/admin data from the profile export.

When asked **who runs an AO**, use Site Q / SLT / AO channel descriptions / maintained leadership data. Do not infer AO ownership from the F3-Nation app admin list.

When asked **why a feature is missing or not working**, check:

1. Is the feature controlled by a regional F3-Nation app setting?
2. Is the region connected/migrated in the bot?
3. Is the destination channel configured?
4. Is the user a PAX, F3-Nation app admin, Slack workspace admin, or Site Q?
5. Is it actually a Slack workspace permission/app installation issue?
6. Is it a deployment/core integration issue requiring F3 Nation dev/ops?
7. Is the relevant context missing because of DMs, private channels, missing channels, or stale manual extraction?

## Confidence and limitations

- The F3-Nation app admin list was manually extracted on 2026-06-30.
- It may become stale.
- It is not currently available through the Slack API/profile export workflow used here.
- Names are display/F3 names as manually extracted and may not map cleanly to Slack user IDs without additional matching.
- Do not merge workspace-local people solely by similar names unless the digest/profile data strongly supports the match.
- Visible Slack activity does not prove who handled issues in DMs, private channels, in-person conversations, or channels missing from the export.
- Redmond F3-Nation app admin data was not supplied.
