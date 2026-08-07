# F3-Nation operations

| Field | Value |
| --- | --- |
| `collected:` | 2026-06-30 |
| `source:` | Manual review of `/f3-nation-settings` and F3-Nation Slack bot behavior |
| `collected_by:` | Project maintainer (manual extraction) |
| `fidelity:` | `hand-compiled` |
| `coverage:` | Bot feature list, region-vs-infrastructure-vs-workspace ownership split, diagnostic routing |
| `known_gaps:` | Not a complete enumeration of every `/f3-nation-settings` option; infrastructure-owner list is current only as of the collection date |
| `refresh_trigger:` | F3-Nation app adds/removes a major bot feature, or ownership of an infrastructure item changes |
| `refresh_owner:` | Project maintainer |

Apply the `fidelity` value above using the table in [query-policy.md](../query-policy.md#dated-augmentation-evidence): `hand-compiled` supports `Medium` at best, and resolves as `Contested` (both sides stated, neither asserted) against conflicting dated Slack evidence.

## Purpose

The Slack digest and user profile exports are strong for visible Slack activity, channel metadata, profile data, and Slack workspace roles. They do **not** contain the F3-Nation app's internal regional admin list or bot-configuration ownership model. This augmentation fills that gap.

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

Do **not** use it as a replacement for the digest or profile exports — see [query-policy.md](../query-policy.md) for how it ranks against Slack evidence.

## Critical role distinctions

The same person may appear in more than one role, but the roles are distinct — see [query-policy.md §Authority boundaries](../query-policy.md#authority-boundaries).

| Role | Source | Meaning | Do not confuse with |
|---|---|---|---|
| Slack workspace admin/owner | Slack profile export | Controls Slack workspace administration, permissions, app installation, and workspace governance | F3-Nation app admin, Site Q, regional leadership |
| F3-Nation app / region admin | Manual `/f3-nation-settings` extraction (see [f3-nation-admins.md](f3-nation-admins.md)) | Can configure F3-Nation app settings for that region | Slack workspace admin, Site Q, regional leadership |
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

## Query guidance

When asked **who can fix or configure the F3-Nation bot**, use the F3-Nation app admin list for the relevant region in [f3-nation-admins.md](f3-nation-admins.md).

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
