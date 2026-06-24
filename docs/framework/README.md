---
framework-version: "2.2.1"
released: "2026-03-27"
---
# Documentation Framework — Operator Guide

This folder contains the documentation framework. Use this guide when applying the framework
to a target project for the first time, or when upgrading an existing framework installation.

---

## Framework Files

| File | Copied to Project | Purpose |
|------|-------------------|---------|
| `doc-standard.md` | Yes | Authoritative standards — formats, rules, placement |
| `doc-bootstrap.md` | No — run from here | Bootstrap and upgrade prompt |
| `templates/` | Yes | Document scaffolding for creating new documents |
| `planning-guide.md` | Only if planning funnel adopted | Planning funnel workflow |
| `README.md` | Yes | This operator guide |

---

## Use Case 1: Bootstrap an Unstructured Project

**When to use:** The target project has no documentation framework, or has ad-hoc documents
that need to be migrated into the standard structure.

**Before starting:**
- Identify the target repository
- Determine the likely tier (Minimal / Standard / Extended) based on project scale
- Ensure you have write access to the target repository

**Process:** Run `doc-bootstrap.md` as a prompt against the target repository. Work through
each phase in order. Do not skip phases or generate content before confirmation gates.

**Phase 1 — Discovery**
Read all existing documentation. Produce an inventory, gap analysis, tier recommendation,
ADR candidates, and list of orphaned content. Present findings and confirm tier with operator
before continuing.

**Phase 1.5 — Disposition Planning**
Convert every gap, orphan, and structural risk into an explicit recommended action (Extract,
Author, ADR, Discard, etc.). Operator reviews and approves each item. No files are created
in this phase.

**Phase 2 — Scaffold Creation**
Copy the framework folder into the target project's `/docs/framework/`. Create document
scaffolds with section headers. Merge `templates/planning-docs-README.md` into the target
project's `/docs/README.md` as the "Planning and Documentation Framework" section, filling
in tier, version, and applied date. Confirm scaffold with operator before continuing.

**Phase 3 — Migration**
Execute the approved disposition plan. Extract, author, and migrate content into framework
documents. Renamed source files with `-OLD` suffix until all content is extracted. Operator
approves migration plan before any existing file is modified.

**Output:** Framework folder installed, document scaffolds created, planning-docs section
present in `/docs/README.md`, content migrated, no orphaned content without a documented
disposition.

---

## Use Case 2: Upgrade an Existing Framework Project

**When to use:** The target project already has the framework applied and a newer version
is available from this central tooling location.

**Assessment — before any files are touched:**

Read the project's actual state and record:
1. Tier — read from CLAUDE.md header (Minimal / Standard / Extended)
2. Framework files present in `/docs/framework/` — note any absent or unexpected files
3. Project documents that have template counterparts — scope for Step 3
4. Any sections in CLAUDE.md or project documents that appear customised beyond the template

If `/docs/framework/README.md` is absent, the prior upgrade was incomplete or the framework
was partially removed — proceed; Step 1 will repopulate it. Record the current version as
unknown.

If the tier is Minimal, note that Standard+ document counterparts do not exist — Step 3
scope is CLAUDE.md only.

**Process:**

**Step 1 — Replace framework files**
Copy all framework files from this folder into the target project's `/docs/framework/`,
replacing existing files. Framework files contain no project-specific content — replacement
is safe. Exclude `doc-bootstrap.md` (it is never copied).

**Step 2 — Replace the planning-docs section**
In the target project's `/docs/README.md`, locate the "Planning and Documentation Framework"
section and replace it with updated content from `templates/planning-docs-README.md`, filled
in with the project's tier, version, and updated applied date. All content outside this
section is untouched.

**Step 3 — Reconcile project documents**
Compare each project document against the corresponding updated template in
`/docs/framework/templates/`. Apply the following rules:

| Change type | Action |
|-------------|--------|
| New section in template, absent from project | Add stub section to project document |
| Changed section in template | Present old and new side-by-side; operator reconciles |
| Section removed from template | Leave project content in place — do not delete |
| Unchanged section | No action |

Produce a reconciliation report listing every change found and the action taken or
recommended. Operator reviews before any project document is modified.

_Minimal tier: CLAUDE.md is the only document with a template counterpart. Skip
DESIGN.md, CONTEXT.md, OPERATIONS.md, QUALITY.md, and BACKLOG.md — they do not exist
at this tier._

**Step 4 — Update metadata**
Update the Applied date in the project's `/docs/README.md` planning-docs section and
in CLAUDE.md.

**Rule:** Never remove content from a project document during an upgrade. The framework
is additive on upgrade — new structure is offered, existing content is preserved.

---

*Thursday, March 26, 2026*
