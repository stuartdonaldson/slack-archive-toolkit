# OPERATIONS — <Project Name>

## Deployment

### Model
<How and where this system runs. Environments and deployment mechanism.>

### Development Environment
[If applicable — include when local setup is not obvious from package config alone]
**Setup:**
```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows
pip install -e ".[dev]"
```

**Verify:**
```bash
<command that confirms environment is working>
```

[If applicable] See CONTRIBUTING.md for OS-specific or IDE-specific variations.

### Installation
```bash
<installation commands>
```

### Environment Variables
[If applicable]
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| <VAR_NAME> | Yes/No | <default> | <description> |

---

## Configuration

### Configuration File
[If applicable]
<Location, format, and key options.>
```json
{
  "<key>": "<value — description>"
}
```

### Key Options
[If applicable]
| Option | Values | Default | Effect |
|--------|--------|---------|--------|
| <option> | <values> | <default> | <what it does> |

---

## Running

```bash
<command to run>
```

[If applicable]
**Common flags:**
| Flag | Description |
|------|-------------|
| `<flag>` | <what it does> |

---

## Monitoring
[If applicable]

### Log Location
<Path or destination.>

### Log Format
[If applicable]
<Format description or example.>

### Health Indicators
[If applicable]
- <e.g. No ERROR entries in log = healthy>

### Alerting
<!-- Extended only — omit for Standard unless alerting is in scope -->
[If applicable]
<What triggers alerts, where they go, who responds.>

---

## Failure Modes

| Failure | Symptom | Recovery |
|---------|---------|---------|
| <e.g. Device unreachable> | <e.g. OSC timeout on connect> | <e.g. Verify device power and network> |
[If applicable] | <Failure> | <Symptom> | <Recovery> |

---

## Recovery Procedures
[If applicable — include when recovery requires more than a simple restart]

### <Scenario e.g. Partial Write Failure>
1. <Step>
2. <Step>
3. <Step>

[If applicable]
### <Scenario e.g. Data Corruption Detected>
1. <Step>
2. <Step>

---

## Audit and Compliance
<!-- Extended only — required when regulatory constraints exist -->
[If applicable — required when CONTEXT.md §Regulatory Constraints is populated]

### Audit Log
<What is logged, where, retention period.>

### Compliance Verification
<How compliance is demonstrated. Evidence produced. Review cadence.>
