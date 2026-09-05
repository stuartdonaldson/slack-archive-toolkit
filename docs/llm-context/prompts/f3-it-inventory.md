# IT-Q asset inventory

Working inventory of accounts, hosting, domains, and repos touched by F3 IT-Q work, plus a
methodology for keeping it current across regions/AOs. Split out from [f3-notes.md](f3-notes.md)
(see its Trello board section for the people/history context this inventory grew out of).

## Kirkland IT-Q inventory (as of 2026-08-18)

Working inventory of accounts, hosting, and repos touched by Kirkland IT-Q work. Ownership/credential/billing columns are open questions to run down, not yet confirmed facts — flag anything below marked TBD.

### Risk register (read this part first)

Continuity risk, not completeness, is what should drive follow-up order. The two highest-risk gaps right now are the ones where **money changes hands or a single inbox is the recovery path for everything else**, and only one (unconfirmed) person can act on them:

| Risk | Why it's high risk | Status |
|---|---|---|
| Who pays for `f3kirkland.com` domain + hosting | If that person's card lapses, leaves F3, or is unreachable, the site/domain can silently expire with no one else able to renew it. | **UNKNOWN — top priority to identify** |
| Who monitors/controls `f3kirkland@gmail.com` | Likely the recovery email / admin contact for the domain and possibly other services. One person as sole holder = single point of failure for regaining access to everything else if they're unreachable. | **UNKNOWN — top priority to identify** |
| `f3go30@gmail.com` credential holder (vs. just "has access") | Multiple people (Little John, Dilfer, Guero) can act inside the account, but it's unconfirmed whether any of them actually hold the recoverable login/password vs. an already-open session. | Partially known — needs verification |
| f3go30 GitHub account owner login | Repo collaborators can manage repos day to day, but only the account owner login can add/remove collaborators or transfer the account. | Unconfirmed who holds it |
| Social media accounts (FB/IG/Twitter) | Believed F3PugetSound-regional, not Kirkland, but no owner/access confirmed either way. | Unconfirmed, low urgency until scope is confirmed |

This table should be kept current at the top of the section — as each row is confirmed, move the detail into the per-asset entry below and downgrade or remove the row here.

### f3go30@gmail.com (Google account)

* **Purpose:** hosts the Go30 tracking spreadsheet and the associated Google Apps Script app.
* **Access:** Little John (Stuart Donaldson), Dilfer, and Guero currently have access. **CREDENTIALS NEEDED** — the actual login/recovery credentials for this account are not yet documented anywhere; access above is by whatever means each person currently has (may not be the same as holding the password/recovery), so this needs to be run down and captured properly.
* **Google Drive contents:** also used to host misc. F3 documents shared with others — notably an "F3 Puget Sound Regional Newsletter" example, an "F3 Slack — FNGs Start Here" document, and static QR-code sign-up images per region. These were parked in a **SlacData** folder as an ad hoc sharing spot.
  * **Action needed:** clean up/relocate the SlacData folder contents — it was a convenience dump, not an intentional home for these docs. Candidate destination: F3PugetSound-owned Drive/repo rather than a personal-feeling `f3go30` account.
* **GitHub Pages (under this account):**
  * Hosts the **Go30 webapp**.
  * Hosts the **ballot tool** used for the active Book Club.
  * **F3Static repo** (`/F3Static/`) — a dedicated static-asset repo, functioning as a poor-man's CDN (images, PDFs). Candidate move: relocate to an `f3pugetsound`-owned GitHub account/org. Link forwarding is believed to preserve existing links/URLs if moved, so this should be low-risk — **needs verification before executing the move**.
* **Ownership/credentials:** TBD — who holds the actual login/recovery for `f3go30@gmail.com`, whether it's on Little John's personal Google account or a shared/region credential, and who else has access.

### f3go30 GitHub account

* **Owner:** the account itself is owned/authenticated via `f3go30@gmail.com` (i.e. GitHub account login is tied to that Gmail address).
* **Hosts:** the repos under GitHub Pages listed above (Go30 webapp, Book Club ballot tool, F3Static).
* **Collaborator model:** other people can be added as collaborators on individual repositories for easier day-to-day management, without needing the account owner's own login — this is the intended way to spread out maintenance access rather than sharing the Gmail/GitHub password itself.
* **CREDENTIALS NEEDED** — need to document who currently holds the GitHub account login (vs. who's just a repo collaborator) and who currently has collaborator access on each repo.

### f3kirkland@gmail.com (Google account)

* **Purpose:** TBD — separate from `f3go30@gmail.com`; what this account is specifically used for (e.g. domain registration, site admin, other services) needs to be captured.
* **Access:** TBD — need to enumerate who currently has access.
* **CREDENTIALS NEEDED** — login/recovery credentials for this account are not yet documented.

### f3kirkland.com domain

* **Registrar / DNS / hosting provider:** TBD.
* **Owner of record:** TBD.
* **Who pays for it:** TBD.
* **Credentials / access list:** TBD — need to enumerate who currently holds login or admin access to the registrar and hosting panel.
* **CREDENTIALS NEEDED.**

### Social media (Facebook, Instagram, Twitter)

* **Believed scope:** these are **F3PugetSound regional accounts, not Kirkland-specific** — included here for inventory completeness while sorting out regional vs. AO-level ownership, not because they belong to Kirkland IT-Q. Should probably live in a regional (F3PugetSound) inventory rather than this Kirkland-focused note long-term.
* **Facebook, Instagram, Twitter:** account handles, owner, and access list — all TBD.
* **CREDENTIALS NEEDED** — no login/access info captured yet for any of the three.

### Follow-up items

* Enumerate and document actual credentials/owners for `f3go30@gmail.com`, the `f3go30` GitHub account, `f3kirkland@gmail.com`, and `f3kirkland.com` hosting — this note only captures what's hosted where and who has some form of access, not who holds the underlying credentials. Every account above is flagged **CREDENTIALS NEEDED** until that's done.
* Decide and execute (or explicitly defer) the SlacData folder cleanup — move newsletter/FNG docs/QR images to a durable, region-owned location.
* Decide and execute (or explicitly defer) the F3Static repo move from the f3go30 GitHub account to an f3pugetsound-owned account, after confirming link forwarding behavior.
* Clarify the purpose and relationship between `f3go30@gmail.com` and `f3kirkland@gmail.com` — confirm whether they're intentionally separate accounts for separate purposes or overlapping/redundant.
* Confirm the Facebook/Instagram/Twitter accounts are indeed F3PugetSound-regional (not Kirkland) and, if so, decide whether they should be moved out of this Kirkland IT-Q note into a regional inventory; capture handles, owner, and access list either way.

## Maintaining an IT asset inventory (methodology — applies beyond Kirkland)

Kirkland is unlikely to be the only AO/region with this problem: an ad hoc pile of shared accounts, no single owner, and no record of who could recover access if the one person who set it up disappeared. Worth handling this the same way across regions rather than reinventing it per-AO. Recommended approach:

1. **This markdown is an index, never a vault.** Never put an actual password/recovery code in this file or any Slack-derived doc — per [[docs/adr/0009]] Slack content is treated as untrusted/exported data, and this doc lives alongside it. The real credentials belong in a **shared password manager** (e.g. a Bitwarden or 1Password shared vault/org) with 2+ named IT-Qs as vault admins, so no single person is a recovery bottleneck. This doc's job is to say *what exists, who can act on it today, where the credential actually lives, and what's still missing* — not to hold the secret itself.

2. **One row per asset, same shape every time.** Standardize columns so entries are comparable and a gap is visually obvious rather than buried in prose:

   | Field | Meaning |
   |---|---|
   | Asset | domain, hosting account, email, social handle, GitHub org, etc. |
   | Type | domain / hosting / email / social / code-hosting / SaaS |
   | Region/AO | which region owns it |
   | Purpose | what it's actually used for |
   | Owner of record / who pays | the billing-responsible party — the highest-risk field to leave blank |
   | Credential holder(s) | who can actually recover/reset access (not just "is logged in") |
   | Other access holders | delegated/collaborator access (e.g. repo collaborators, Drive shares) |
   | Where credential lives | pointer into the shared vault, not the credential itself |
   | Risk level | High/Medium/Low — driven by "what breaks and how fast if this person disappears" |
   | Last verified | date someone actually confirmed the row, not just wrote it down |
   | Status | Confirmed / Partial / **CREDENTIALS NEEDED** |

3. **Lead with a risk register, not an alphabetical list.** As done above: pull rows where money is paid or where one inbox gates recovery of everything else to the top, sorted by risk — that's the actionable part. The detailed per-asset write-ups stay below as reference.

4. **Review on a cadence, not just when something breaks.** Re-verify each row at IT-Q handoff and at least once a quarter; treat any row with a `Last verified` date older than ~2 quarters as stale and re-confirm it rather than trusting it.

5. **Reuse the same template across regions.** The schema in #2 is the reusable part. When another AO/region wants to do this, copy the shape (risk register + per-asset rows + follow-up list) into their own notes file rather than re-deriving the format — that keeps inventories comparable if/when they ever need to be rolled up regionally (e.g. F3PugetSound-wide social accounts, shared domains).
