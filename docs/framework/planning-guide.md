# From Vision to Execution: Planning with Beads

---

## Core Principle

Enter at whichever stage matches the work's maturity. Skip what doesn't apply.

| If the work is... | Start at | Example |
|---|---|---|
| Clear enough to define acceptance criteria | **Pattern A** — straight into beads | Bug fix, well-understood feature, config change |
| Needs scoping but no major unknowns | **Pattern B** — brief staging, then beads | Multi-task feature, new integration |
| Large, uncertain, or has open questions | **Pattern C** — full funnel | New subsystem, unfamiliar technology, cross-cutting initiative |

Most work is Pattern A. Reach for B or C only when the simpler pattern doesn't fit.

---

## Pattern A: Direct to Beads

For work where the what and how are already clear.

```bash
bd create "Add mute group for choir mics on Wing" -t task -p 2 \
  --acceptance "Single button mutes all choir channels. Does not affect recording bus." --json
```

Done. No documents, no staging. If the task produces a reusable insight, record it:

```bash
bd remember "Wing mute groups are DCA-based, not channel-based — assign channels to DCA first" --key wing-mute-groups
```

---

## Pattern B: Scope, Then Beads

For work that needs brief planning before decomposition. Typically takes one session to scope and enter beads.

### 1. Write a short staging note

A few paragraphs in `docs/staging/` or even inline in a conversation. Cover scope, known dependencies, and initial task breakdown.

### 2. Create the epic and decompose

```bash
bd create "PowerPoint focus-independent control" -t epic -p 1 \
  --description "Control PPT slides without requiring window focus. COM automation on STA thread." --json
# Returns: nl-x1y2

bd create "Implement COM automation wrapper" -t task -p 1 --parent nl-x1y2 \
  --acceptance "Advance/retreat slides without PPT having focus. Works during Zoom screen share." --json

bd create "Add slide position tracking" -t task -p 2 --parent nl-x1y2 \
  --acceptance "System always knows current slide index. Survives PPT restart." --json

bd dep add <tracking-id> <com-wrapper-id>
```

### 3. Archive the staging note

```bash
rm docs/staging/pptx-control.md  # or git mv to docs/archive/
```

---

## Pattern C: Full Funnel

For large initiatives with real unknowns. Uses a SAFe-influenced epic funnel to mature ideas before they enter beads.

### The funnel stages

```
Theme  →  Funnel  →  Review  →  Staging  →  Spikes  →  Beads
(years)   (months)   (weeks)    (days)      (hours)    (execution)
```

| Stage | Location | Gate to advance |
|---|---|---|
| **Theme** | `docs/VISION.md` | Stable goals. Reviewed annually. |
| **Funnel** | `docs/ROADMAP.md` — one-liners | "Aligned with a theme?" |
| **Review** | `docs/ROADMAP.md` — lean business case | "Value justifies effort and risk?" |
| **Staging** | `docs/staging/<n>.md` | "Can I write acceptance criteria?" |
| **Spikes** | beads enabler tasks | Resolve open questions |
| **Execution** | beads epics → features → stories | `bd ready` drives daily work |

### Walkthrough: Live Captioning Pipeline

**Funnel.** One-liner added to roadmap during monthly review.

```markdown
# docs/ROADMAP.md — Funnel
- Automated captioning for worship services
```

**Review.** Promoted with a lean business case.

```markdown
# docs/ROADMAP.md — Reviewing

### Automated captioning for worship services
Real-time captions on projector and Zoom. Accessibility for hearing-impaired
and remote participants. Risk: theological vocabulary accuracy. Effort: medium.
```

**Staging.** Selected for next cycle. Staging document identifies scope, dependencies, and open questions.

```markdown
# docs/staging/live-captioning.md

## Scope
Deepgram streaming STT → caption overlay on projector + Zoom closed captions.

## Open Questions
- Mic direct out vs program mix for STT input?
- Dedicated caption monitor vs projector overlay?
```

**Spikes.** Open questions become timeboxed beads enablers.

```bash
bd create "Spike: mic vs program feed for STT accuracy" \
  -t task -p 1 -l enabler --estimate 120 --json

bd create "Spike: caption display approach" \
  -t task -p 2 -l enabler --estimate 60 --json
```

**Record findings.** Spike results become memories.

```bash
bd close <mic-spike> --reason "Direct out wins — 15% better WER than program mix" --json
bd remember "Caption STT: use Wing direct out from lectern mic, not program mix" --key captioning-audio-source

bd close <display-spike> --reason "Lower-third overlay — simpler for volunteers" --json
bd remember "Caption display: projector overlay, not dedicated monitor" --key captioning-display
```

**Create epic and decompose.** Open questions resolved, decomposition is now possible.

```bash
bd create "Live captioning pipeline" -t epic -p 1 \
  --description "Deepgram streaming STT. Lectern direct out. Lower-third projector overlay. Zoom caption feed." --json
# Returns: nl-a1b2

# Feature: Audio capture
bd create "Audio capture from Wing to STT" -t feature -p 1 --parent nl-a1b2 --json
# Returns: nl-c3d4

  bd create "Configure Wing direct out for lectern channel" \
    -t task -p 1 --parent nl-c3d4 \
    --acceptance "Clean signal at -18dBFS. No side effects on main mix." --json

  bd create "Implement audio capture service" \
    -t task -p 1 --parent nl-c3d4 \
    --acceptance "Continuous PCM capture, <50ms latency, handles USB reconnection." --json

# Feature: STT integration
bd create "Deepgram streaming integration" -t feature -p 1 --parent nl-a1b2 --json
# Returns: nl-e5f6

  bd create "Implement Deepgram WebSocket client" \
    -t task -p 1 --parent nl-e5f6 \
    --acceptance "Streaming transcription <500ms e2e latency. Auto-reconnect." --json

  bd create "Custom vocabulary for theological terms" \
    -t task -p 2 --parent nl-e5f6 \
    --acceptance "10 common liturgical terms all recognized correctly." --json

# Feature: Display
bd create "Caption rendering and display" -t feature -p 1 --parent nl-a1b2 --json
# Returns: nl-g7h8

  bd create "Build caption overlay window" \
    -t task -p 1 --parent nl-g7h8 \
    --acceptance "Readable from back row. Supports light/dark backgrounds." --json

  bd create "Integrate with projector control" \
    -t task -p 2 --parent nl-g7h8 \
    --acceptance "Captions appear at service start. No interference with PPT slides." --json

# Feature: Zoom
bd create "Zoom closed caption integration" -t feature -p 2 --parent nl-a1b2 --json

  bd create "Send captions to Zoom via API" \
    -t task -p 2 --parent <zoom-feature-id> \
    --acceptance "Remote participants see captions <2s from speech." --json
```

**Wire dependencies.**

```bash
bd dep add nl-e5f6 nl-c3d4          # STT depends on audio capture
bd dep add nl-g7h8 nl-e5f6          # Display depends on STT
bd dep add <zoom-feature> nl-e5f6   # Zoom depends on STT
bd dep add <vocab-task> <ws-task>   # Vocabulary depends on base STT
```

**Verify.**

```bash
bd graph nl-a1b2 --compact
```
```
Layer 0: ○ Configure Wing direct out
         ○ Implement audio capture service
Layer 1: ○ Implement Deepgram WebSocket client
Layer 2: ○ Custom vocabulary
         ○ Build caption overlay window
         ○ Send captions to Zoom
Layer 3: ○ Integrate with projector control
```

**Archive staging, execute normally.**

```bash
git rm docs/staging/live-captioning.md
```

From here, standard session protocol: `bd ready` → claim → work → close → push. Capture learnings with `bd remember` as they emerge. Close the epic when all children complete.

---

## Molecule Formulas (Optional)

Molecules formalize repeatable workflow patterns as versioned, parameterized templates that agents execute step by step. They are valuable when the same multi-step pattern recurs across features or initiatives, when human review gates need to be structurally enforced rather than remembered, and for **cross-cutting concerns** — work that spans multiple epics, modules, or teams where all areas must be addressed before the concern can close (security hardening, observability uplift, compliance review, accessibility audit). A cross-cutting molecule creates parallel task clusters per area, wired to a shared gate that blocks closure until every area is signed off.

Two example formulas are provided in `docs/beads-formulas/`:

| Formula | When to use |
|---------|-------------|
| `initiative-funnel.formula.yaml` | Pattern C — matures an initiative from business case through spikes to an executable epic |
| `feature-delivery.formula.yaml` | Any feature — use-case authoring through implementation, independent agent review, and documentation |

Pour an example formula directly by path:

```bash
bd cook /path/to/DevStandard/docs/beads-formulas/feature-delivery.formula.yaml \
  --var feature="Audio capture service" \
  --var use_case_id="UC-4" \
  --var target_docs="DESIGN.md, OPERATIONS.md"
```

The resulting molecule appears in `bd ready` step by step as dependencies resolve. Human gates pause execution until closed with `bd gate resolve <id>`. Verify the full DAG with `bd graph <epic-id> --compact`.

---

## Review Cadence

| Scope | Frequency | Action |
|-------|-----------|--------|
| Themes | Annually | Revalidate |
| Funnel | Monthly | Add, drop, promote |
| Review | Biweekly–monthly | Evaluate business cases |
| Staging | Weekly | Enter beads or push back (two-week max) |
| Execution | Every session | `bd prime` → `bd ready` → work |

---

## Where Things Live

| Content | Location | In beads? |
|---------|----------|-----------|
| Strategic goals | `docs/VISION.md` | No |
| Speculative ideas | `docs/ROADMAP.md` — Funnel | No |
| Evaluated initiatives | `docs/ROADMAP.md` — Review | No |
| Work being scoped | `docs/staging/<n>.md` | Not yet |
| Enabler spikes | beads tasks, label `enabler` | Yes |
| Features and stories | beads epics/tasks | Yes |
| Formal decisions | `docs/adr/NNNN-*.md` | No |
| Operational knowledge | `bd remember` | Yes |
| Status and progress | `bd status`, `bd ready`, `bd query` | Computed |

---

## Anti-Patterns

**Over-process for simple work.** If you can write acceptance criteria now, skip the funnel. Pattern A exists for a reason.

**Stale staging.** Two-week max. If it can't decompose, push it back to Review.

**Duplicating state in prose.** No PLAN.md that restates beads content. Beads owns operational state.

**Issues as knowledge articles.** Use `bd remember` for operational constraints, ADRs for formal decisions.

**Skipping the memory step.** Unrecorded decisions get rediscovered in future sessions — the most common waste in multi-session AI-assisted work.
