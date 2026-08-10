# F3-Nation apps and operations

| Field | Value |
| --- | --- |
| `collected:` | 2026-08-10 |
| `source:` | Manual review of `/f3-nation-settings` and F3-Nation Slack bot behavior; org.f3nation.com/map.f3nation.com/pax-vault.f3nation.com entries added from source-code review of the `f3-nation`, `f3-org-map`, and `pax-vault` repos (data-fetch queries, API routers, permission checks) — see `f3-nation-data-model.md` in the reviewer's workspace for the underlying trace; tool details added by the project maintainer |
| `collected_by:` | Project maintainer (manual extraction + code review) |
| `fidelity:` | `hand-compiled` |
| `coverage:` | F3-Nation tool reference (including org.f3nation.com, map.f3nation.com, pax-vault.f3nation.com data sources and edit paths), Slack bot feature list, region-vs-infrastructure-vs-workspace ownership split, diagnostic routing |
| `known_gaps:` | Tool details are a maintainer-populated reference; not a complete enumeration of every `/f3-nation-settings` option; infrastructure-owner list is current only as of the collection date; map.f3nation.com anonymous-access claim is inferred from API source (`protectedProcedure`) and not independently confirmed by an unauthenticated live test; PAX Vault BigQuery ingestion lag/timing not independently confirmed |
| `refresh_trigger:` | A covered F3-Nation tool adds/removes a major feature, or ownership of an infrastructure item changes |
| `refresh_owner:` | Project maintainer |

Apply the `fidelity` value above using the table in [query-policy.md](../query-policy.md#dated-augmentation-evidence): `hand-compiled` supports `Medium` at best, and resolves as `Contested` (both sides stated, neither asserted) against conflicting dated Slack evidence.

## Purpose

The Slack digest and user profile exports are strong for visible Slack activity,
channel metadata, profile data, and Slack workspace roles. They do **not**
describe the F3-Nation tool ecosystem, the app's internal regional admin list,
or the bot-configuration ownership model. This augmentation fills those gaps.

Use it when answering questions about:

- F3-Nation tools and their intended users, access, ownership, and support path
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

## F3-Nation tool reference

This section is the maintainer-owned reference for F3-Nation apps and services.
Add one entry per tool as its details are verified. Keep tool facts separate
from the role and escalation guidance below: a tool entry answers what the tool
is for, while the later sections answer who can configure or repair it.

### Entry template

```markdown
### <Tool name>

- **Purpose:**
- **Primary users:**
- **Access:**
- **Key capabilities:**
- **Source of truth / data maintained:**
- **Regional configuration:**
- **Ownership and support path:**
- **Known limits or dependencies:**
- **Last verified:** YYYY-MM-DD
```

When adding an entry, link to an operator-authored source where available. Keep
unreviewed vendor or third-party material under `sources/`, not in this file.

### Where information appears, and where it actually comes from

Quick-routing table for "where do I see X" / "where do I fix X" questions
across the three public F3-Nation sites. All three ultimately read from the
same underlying F3 Nation database via `api.f3nation.com`, **except**
PAX Vault, which uses a separate analytics store — see its entry below for
why that matters.

| Info | Shows on org.f3nation.com? | Shows on map.f3nation.com? | Shows on pax-vault.f3nation.com? | Where to correct it |
| --- | --- | --- | --- | --- |
| AO/region name, description, logo, website, email, phone, socials | Region/AO name only (in the boundary hover panel) | Yes (AO contact block) | AO name only (as a stats grouping) | admin.f3nation.com → AOs/Locations/Events (matching section), or Slack `/f3-nation-settings` for the same underlying record |
| Location address/lat-lng/description ("Where") | No | Yes | No | admin.f3nation.com → Locations |
| Event day/time/description ("Notes") — the standing **recurring schedule** | No | Yes | Indirectly, via attendance stats | admin.f3nation.com → Events, or Slack Manage Series |
| A specific **dated** calendar event/occurrence (one-off, unscheduled preblast, or a "Special Event" flagged `highlight`) | No | **No** — the map never queries dated event instances, only the recurring schedule | No (attendance only shows once a backblast is logged) | N/A to view outside Slack — see `/preblast` and `/f3-calendar` in the Slack bot; nothing on any of the three public sites lists individual upcoming dated events |
| SLT / Nant'an / ITQ / custom region-level positions | Yes (region level, on hover/click) | No | No | admin.f3nation.com → Positions → Assignments, or Slack `/f3-nation-settings` → SLT config |
| Site Q (AO-level position) | Yes, but **only when viewing that specific AO** — not listed at the region level | **No** — Site Q is not a map data field at all | No | Same as SLT above |
| PAX attendance history, post counts, distinct AOs visited, leaderboard | No | No | Yes | Not directly editable — reflects logged backblasts; a Q can exclude one event's attendance from PAX Vault via the "exclude from PAX Vault" toggle when creating/editing that event/series in Slack |

Live per-region detail matching this table (SLT rosters, Site Q per AO, who
currently holds the editor/admin role to fix each region) is pulled fresh
from `api.f3nation.com` in `f3-nation-pugetsound.md` — treat that file as
the current instance of this table's "where to correct it" column, not this
static reference.

### org.f3nation.com

- **Purpose:** Visualize the F3 org hierarchy (sector → area → region → AO) as map boundary polygons, and show each org's filled leadership positions on hover/click.
- **Primary users:** Any signed-in PAX looking up who holds SLT/Site Q for a region or AO.
- **Access:** Requires being signed in as any PAX (its API, `orgChart.byId`/`.all`, has no anonymous read) — but no admin/editor role is needed just to view.
- **Key capabilities:** Convex-hull boundary polygons per sector/area/region/AO, computed from aggregated location points (not hand-drawn geofences); leadership panel per org — Nant'an/ITQ/custom positions at the region level, **Site Q only when the panel is opened for that specific AO** (Site Q is not part of a region's own roster view).
- **Source of truth / data maintained:** Reads live from the same F3 Nation database as everything else, via `api.f3nation.com`'s `/v1/org-chart` endpoint. Nothing is edited here — read-only viewer.
- **Regional configuration:** None — purely a read-only visualization; nothing region-specific to turn on/off.
- **Ownership and support path:** Separate GitHub repo (`F3-Nation/f3-org-map`, a standalone Vite/TypeScript/Leaflet app — not part of the main `f3-nation` monorepo despite the similar name), maintained by F3 Nation dev/ops.
- **Known limits or dependencies:** No working deep link to an individual AO — you must click through the map. Individual dated events never appear here — it's boundaries and leadership only, no per-event or per-workout display of any kind.
- **Last verified:** 2026-08-10

### map.f3nation.com

- **Purpose:** Public interactive map of workout locations nationwide — the default place a prospective PAX finds a workout to attend.
- **Primary users:** Any PAX or visitor looking for a nearby workout; no F3 affiliation required to browse.
- **Access:** The map itself renders without signing in; the marker click-through detail call is a protected endpoint in the API source, so full AO detail on click may require sign-in (flagged as inferred from source, not independently confirmed against a live anonymous session).
- **Key capabilities:** One pin per physical Location; clicking it lists that AO's **recurring weekly schedule** (day/time per Event series) plus the Location's "Where" description and the Event's "Notes" description, and the AO's contact info (email/phone/website/socials).
- **Source of truth / data maintained:** Live query joining Locations to the recurring **Event/series** table via `api.f3nation.com`. It does **not** query dated calendar occurrences (individual scheduled instances, unscheduled/ad-hoc preblasts, or anything flagged as a "highlighted" Special Event) — those are a separate table the map's query never touches. Practically: the map shows the *standing* schedule, never "what's happening this specific Saturday" beyond the recurring pattern.
- **Regional configuration:** None — reflects whatever AO/Location/Event records exist for that org; there is no per-region toggle for what the map shows.
- **Ownership and support path:** `apps/map` inside the main `f3-nation` monorepo; F3 Nation dev/ops.
- **Known limits or dependencies:** Site Q never appears on the map — it isn't a map data field at all, regardless of any setting. A "Special Event" highlight flag (set via Slack `/f3-nation-settings`) has zero effect on map rendering — confirmed the map's query doesn't even select that field. Do not tell a user "mark it as a Special Event and it'll show on the map" — it will not.
- **Last verified:** 2026-08-10

### pax-vault.f3nation.com

- **Purpose:** Participation/engagement analytics — attendance history, activity stats, and leaderboards derived from logged backblasts.
- **Primary users:** A PAX checking their own (or another PAX's) post history/stats; regional leadership reviewing AO/region activity levels.
- **Access:** Requires signing in with an F3 email (Firebase auth). Individual stats pages are linked as `pax-vault.f3nation.com/stats/pax/{id}`; region stats as `.../stats/region/{orgId}`.
- **Key capabilities:** First/most-recent post date, total post count, distinct AOs visited, top "besties," AO-level activity stats, and a most-AOs-visited leaderboard.
- **Source of truth / data maintained:** A **separate Google BigQuery analytics store**, not the same Postgres database backing admin.f3nation.com/map.f3nation.com/org.f3nation.com. It ingests from logged backblast/attendance data and is read-only by design — no scorekeeping edits happen inside PAX Vault itself.
- **Regional configuration:** A Q can set "exclude from PAX Vault" when creating/editing an event or series in Slack (stored as a flag inside that event/series' metadata, not a standalone database column) to keep a specific event's attendance out of PAX Vault stats.
- **Ownership and support path:** Separate repo (`pax-vault`) with its own stack (Next.js + BigQuery + Firebase auth) — distinct from the main monorepo; F3 Nation dev/ops maintained.
- **Known limits or dependencies:** Read-only — there is no PAX Vault screen to correct bad data; a wrong stat traces back to the underlying backblast, which must be corrected via Slack's edit-backblast flow instead. BigQuery ingestion lag after a backblast posts is not independently confirmed.
- **Last verified:** 2026-08-10

## Slack bot and regional configuration

## Roles and ownership boundaries

The same person may appear in more than one role, but the roles are distinct — see [query-policy.md §Authority boundaries](../query-policy.md#authority-boundaries).

| Role | Source | Meaning | Do not confuse with |
|---|---|---|---|
| Slack workspace admin/owner | Slack profile export | Controls Slack workspace administration, permissions, app installation, and workspace governance | F3-Nation app admin, Site Q, regional leadership |
| F3-Nation app / region admin | Live `api.f3nation.com` role read (see [f3-nation-pugetsound.md](f3-nation-pugetsound.md)) | Can configure F3-Nation app settings for that region | Slack workspace admin, Site Q, regional leadership |
| Site Q | Two independent sources — SLT config in Slack `/f3-nation-settings` (same data as the Positions → Assignments tab on admin.f3nation.com), **or** AO channel metadata (topic/purpose) and messages in Slack | AO-level leadership / workout ownership | Slack admin or F3-Nation app admin |
| Regional leadership | Two independent sources — SLT config in Slack `/f3-nation-settings`, **or** channel descriptions, messages, and qualified profile/title hints in Slack | Human regional leadership such as Nantan, Weasel Shaker, 1st F, 2nd F, 3rd F, Comz | Slack admin, F3-Nation app admin, Site Q |

For Site Q and regional leadership, the `/f3-nation-settings` record and the
Slack-visible version (channel topic/purpose, pinned messages, casual
mentions) are **not the same data and are not kept in sync automatically** —
one is admin/database-maintained, the other is community-maintained, and
either can be stale. Report both when they disagree rather than picking one;
see [f3-augmentation-index.md §Deliberate dual-sourcing](f3-augmentation-index.md#deliberate-dual-sourcing-f3-nation-app-data-vs-slack)
and [query-policy.md](../query-policy.md#dated-augmentation-evidence) for how
to rank and present the conflict.

Key rule: **F3-Nation app admin ≠ Slack workspace admin ≠ Site Q.**

### What the F3-Nation Slack bot does

The F3-Nation Slack bot supports:

- `/backblast` — log a completed workout (AO, Q/co-Q, PAX attendance, FNG count, moleskin notes)
- `/preblast` — announce an upcoming workout; also supports an "unscheduled event" option for one-offs not on the calendar
- `/f3-calendar` — browse/search upcoming scheduled events
- `/tag-achievement` — award an achievement badge to a PAX
- `/f3-nation-settings` — region admin configuration menu; see "Who configures what" below
- `/help`
- HC / un-HC and Take Q buttons — inline on calendar and preblast posts
- edit backblast / preblast flows
- Strava attachment, if enabled
- Q lineup signup — claim an open Q slot on the calendar
- missing backblast lookup — admin view listing AOs with a scheduled event but no backblast posted
- emergency info lookup — pulls a PAX's stored emergency contact info
- downrange region/event lookup — find workouts in other F3 regions (e.g. while traveling)
- user profile management
- welcome messages — automated greeting sent to new members (Welcomebot)
- Q lineup posts — scheduled reminder listing upcoming Q assignments
- backblast/preblast reminders
- achievement notifications
- monthly region/AO reports
- calendar image posts — auto-generated calendar graphic posted on a schedule

Most optional or automatic features are controlled per region by F3-Nation app admins through `/f3-nation-settings`.

### Who configures what

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

## Diagnostic and routing guidance

When asked **who can fix or configure the F3-Nation bot**, use the F3-Nation app admin/editor list for the relevant region/AO in [f3-nation-pugetsound.md](f3-nation-pugetsound.md) ("who can correct this" line — note it does not distinguish admin from editor role, only that either can make the change).

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
