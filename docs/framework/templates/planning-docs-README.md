<!-- Planning and Documentation Framework section — managed by the framework.
     On framework upgrade, replace this entire section (from the h2 heading to the
     closing horizontal rule) with the updated version. All other content in this
     file is project-specific and must not be modified during upgrade. -->

## Planning and Documentation Framework

**Framework Version:** `<version>` | **Tier:** `<Minimal | Standard | Extended>` | **Applied:** `<YYYY-MM-DD>`

This project follows the [DevStandard documentation framework](docs/framework/README.md).
Framework files are in `/docs/framework/` — read-only reference copies updated from the
central tooling location.

---

### Document Structure

**Minimal tier** (all content in `README.md`):
- `README.md §CONTEXT` — goals, constraints, capabilities, use cases
- `README.md §DESIGN` — architecture, building blocks
- `README.md §OPERATIONS` — deployment, configuration, failure modes

**Standard / Extended tier** — separate documents in `/docs/`:

| Document | Purpose | Tier |
|----------|---------|------|
| `docs/CONTEXT.md` | Goals, constraints, use cases, glossary | Standard + Extended |
| `docs/DESIGN.md` | Architecture, building blocks, runtime view | Standard + Extended |
| `docs/OPERATIONS.md` | Deployment, configuration, failure modes | Standard + Extended |
| `docs/QUALITY.md` | Quality scenarios, risks, technical debt | Extended only |
| `docs/adr/` | Architecture decision records | All tiers |

Architecture decision records are immutable once Accepted. See `docs/framework/doc-standard.md §ADR Format`.

---

### Issue Tracking

[If applicable — when bd is in use]

This project uses **bd (beads)** for issue tracking.

```bash
bd prime    # session context and ready work
bd ready    # available work (unblocked, prioritized)
bd show <id>          # issue detail
bd update <id> --claim  # claim work
bd close <id>         # mark complete
```

[If bd is not in use]

Review `PLAN.md` for current state and in-flight work. Review `BACKLOG.md` for queued work.

---

### Session Start

```
review project state before we start
```

This triggers a check of document sizes, open decisions, and graduation candidates before
beginning work.

---

### Document Templates

Templates for creating new framework documents are in `/docs/framework/templates/`. Use the
corresponding template when adding a new document type to this project.

---

### Framework Updates

To update the framework in this project:

1. Copy updated framework files from the central tooling location into `/docs/framework/`
2. Replace the "Planning and Documentation Framework" section in this file with the updated
   `templates/planning-docs-README.md`, filled in with this project's tier and applied date
3. Review the reconciliation report for any new or changed sections in project documents
4. Do not remove project-specific content during the update

---
