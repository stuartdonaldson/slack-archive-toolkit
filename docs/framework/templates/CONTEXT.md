# CONTEXT — <Project Name>

## Introduction & Goals

### Purpose
<Two to three sentences describing what this system does and why it exists.>

### Quality Goals
<!-- Extended: required; Standard: [If applicable] — include top 3–5 quality attributes -->
| Priority | Quality Goal | Scenario |
|----------|-------------|----------|
| 1 | <e.g. Safety> | <e.g. No write completes without prior read and post-write verification> |
| 2 | <e.g. Operability> | <e.g. A non-technical volunteer operates without training or support> |
| 3 | <e.g. Reliability> | <e.g. System recovers from connection loss without data corruption> |

### Stakeholders
<!-- Standard: two-column; Extended: three-column with Role -->
<!-- Standard version: -->
[If applicable]
| Stakeholder | Expectation |
|-------------|-------------|
| <e.g. Developer> | <e.g. Fast context reload, clear module boundaries> |
| <e.g. Operator> | <e.g. Clear error messages, documented recovery steps> |

<!-- Extended version (replace table above):
| Stakeholder | Role | Key Expectation |
|-------------|------|----------------|
| <e.g. Developer> | <Builder and maintainer> | <Fast context reload, clear boundaries> |
| <e.g. Operator> | <Non-technical runtime user> | <Clear errors, documented recovery> |
| <e.g. Compliance Officer> | <Regulatory oversight> | <Audit trail, documented decisions> |
-->

---

## Constraints

### Technical Constraints
[If applicable]
- <e.g. Python 3.11+ required>
- <e.g. Must operate without internet access>
- <e.g. Target hardware: Raspberry Pi 4>

### Organizational Constraints
[If applicable]
- <e.g. Single developer, no external service dependencies>
- <e.g. Open source — no proprietary dependencies>

### Regulatory Constraints
[If applicable]
- <e.g. Must comply with GDPR for any user data stored>
- <e.g. Accessibility requirements per WCAG 2.1 AA>
- <e.g. Audit log required for all configuration changes>

---

## Core Capabilities
<Durable, implementation-neutral statements of what the system does.>
- <Capability>
- <Capability>
[If applicable] - <Capability>

---

## Use Cases
<!-- Use standard UC format from doc-standard.md -->

### UC-1: <Short Name>

Actor: <Primary actor>

Preconditions:
- <Condition>

Primary Flow:
1. <Step>
2. <Step>
3. <Step>

Alternate Flows:
[If applicable] A1: <Condition> → <Outcome>

Postconditions:
- <Resulting system state>

Constraints:
- <Invariant or rule that must hold>

---

## Non-Goals
- <What this system explicitly does not do>
[If applicable] - <Additional non-goal>

---

## Glossary
<!-- Standard: [If applicable]; Extended: required -->
[If applicable]
| Term | Definition |
|------|------------|
| <Term> | <Definition> |
