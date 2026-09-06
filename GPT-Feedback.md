## Goal

Improve `f3-nation-pugetsound.md` for LLM consumption by making important relationships explicit, reducing duplicated reference material, and preventing unsupported inferences.

## Recommended changes

1. **Add a concise purpose/scope statement near the top.**
   State that this file is a current F3 Nation API snapshot for the listed Puget Sound-area regions, including region/AO records, recurring workout configuration, position assignments, and org-level edit authority.

2. **Clarify authentication terminology.**
   Avoid describing `api.f3nation.com` simply as a “public API” when some endpoints require authentication. Prefer wording such as:

   > `api.f3nation.com`, the F3 Nation API used by org.f3nation.com and map.f3nation.com.

3. **Make missing position assignments semantically explicit.**
   Add a document-wide rule:

   > A missing SLT or Site Q assignment means F3 Nation returned no assignment for that position at retrieval time. It does not by itself establish that the operational role is vacant.

   This prevents an LLM from converting “none returned” into “Vacant.”

4. **Explicitly document the AO / Location / Event data model.**
   State that AO, Location, and Event are separate records and may have independent values and status.

   Where source verification supports it, clearly state where their description fields appear in the user-facing applications. The current document clearly supports:

   * Location description → **“Where”** on map.f3nation.com
   * Event description → **“Notes”** on map.f3nation.com

   The exact presentation of the **AO description** should be verified against the source implementation before adding a definitive mapping.

5. **Make active/inactive state consistent and machine-readable.**
   Instead of only warning when something is inactive, consider emitting an explicit status field for AO, Location, and Event records where the API provides it:

   > **Status:** Active
   > **Status:** Inactive

   Also state explicitly that an inactive Location may remain accessible by direct `locationId` URL even though it is excluded from normal search, if that behavior is confirmed by the source.

6. **Include stable record IDs consistently.**
   AO org IDs are already useful. Where available, also emit Location IDs and Event/series IDs in a consistent format. This improves joins, troubleshooting, and resilience to renamed records.

7. **Reduce duplication with `f3-nation-apps.md`.**
   Keep this file focused on the current live snapshot. Move or shorten durable explanations of how org.f3nation.com, map.f3nation.com, PAX Vault, permissions, and edit paths work when those are already maintained in `f3-nation-apps.md`.

   Retain only the interpretation rules necessary to understand this report, with a pointer to the canonical operations reference for the full explanation.

8. **Use a compact structured freshness block.**
   Prefer something like:

   | Field              | Value                                                                     |
   | ------------------ | ------------------------------------------------------------------------- |
   | Retrieved          | 2026-08-18 3:07 PM PDT                                                    |
   | API source         | api.f3nation.com                                                          |
   | Generator          | tools/region_verification_report.py                                       |
   | Generator revision | 2026-08-18                                                                |
   | Regions            | Puget Sound, Kirkland, Tundra, Redmond - WA, Cascades, Seattle, North SEA |

   Pacific time should be primary for consistency with the surrounding knowledge set. UTC may be retained parenthetically for technical diagnostics.

9. **Add a short interpretation-rules section before the region data.**
   Suggested concepts:

   * Positions shown are F3 Nation assignments, not Slack-derived leadership.
   * No assignment returned does not mean the role is vacant.
   * AO, Location, and Event are separate objects.
   * Record status should not be inferred from a related object's status.
   * Directly addressable inactive records may behave differently from searchable records.

## Verification requirement

Do **not** implement any recommendation that depends on behavior not directly established by the generator, API response, application source code, or another authoritative source.

In particular, verify before asserting:

* exactly where the **AO description** appears in org.f3nation.com or map.f3nation.com;
* whether AO, Location, and Event each expose independent active/inactive fields;
* whether Event/series IDs are available and stable enough to publish;
* any anonymous-versus-authenticated access behavior not already confirmed by direct testing or source code;
* any edit-authority behavior that is currently inferred rather than directly enforced by the reviewed authorization code.

Where verification is incomplete, preserve the existing qualified wording rather than converting an inference into a definitive statement.

## Priority

Highest-value changes:

1. distinguish **“no assignment returned”** from **“vacant”**;
2. make the **AO / Location / Event relationship** explicit;
3. clearly map description fields only where verified;
4. reduce duplicated operational documentation;
5. standardize freshness and status metadata.

