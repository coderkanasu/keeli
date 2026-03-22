# Hallucination Rework Benchmark Protocol

## Purpose
Define a repeatable method to measure rework attributable to AI hallucinations during delivery.

This protocol is used to populate:
- Requirement-change rework hours
- Hallucination-attributed rework hours
- Hallucination rework rate

## Scope
- Applies to all active Task, Bug, and Feature items during the pilot.
- Applies when AI assistance was used in planning, implementation, testing, or documentation.
- Excludes pure typo fixes with no behavior, interface, or requirement impact.

## Operational Definitions
### Hallucination Event
An AI-generated statement or artifact that is not supported by project context, codebase reality, or validated external source, and causes corrective work.

### Rework Window
Time spent to detect, correct, and re-verify outcomes caused by a hallucination event.

### Attributed Rework Hours
Engineer hours assigned to a hallucination event using this protocol's attribution rubric.

## Attribution Rubric (Required)
Each rework event must be tagged with one primary cause:
- `H1-Context-Miss`: Existing local context was available but not used correctly.
- `H2-Requirement-Fabrication`: AI invented requirement details not present in artifacts.
- `H3-Interface-Fabrication`: AI referenced non-existent API/module/field.
- `H4-Policy-Fabrication`: AI asserted false governance/compliance behavior.
- `H5-External-Fact-Error`: AI introduced unsupported external claim.

Severity score:
- `S1` Low: contained to one file, no downstream impact.
- `S2` Medium: cross-file correction or test churn.
- `S3` High: release risk, incident risk, or external rollback.

Confidence score:
- `C1` Low confidence attribution (limited evidence).
- `C2` Medium confidence attribution.
- `C3` High confidence attribution (direct evidence trail).

## Required Evidence Per Event
Every attributed event must include:
1. Task ID and slug.
2. Detection timestamp (UTC ISO-8601).
3. Rework hours (decimal, 0.25-hour increments).
4. Rubric tag (`H1`..`H5`) and severity (`S1`..`S3`).
5. Link to artifact showing incorrect output (commit, diff, log, or prompt trace).
6. Link to corrective artifact (fix commit, test evidence, or updated requirement).
7. Reviewer sign-off persona (`@qa` or `@architect`).

## Data Capture Format
Use this row format in weekly snapshot notes or task evidence sections:

`YYYY-MM-DD | T-XXXX | Hx | Sx | Cx | <hours> | <incorrect-artifact-link> | <corrective-artifact-link> | <reviewer>`

Example:

`2026-03-14 | T-0042 | H3 | S2 | C3 | 1.50 | commit:abc123 | commit:def456 + pytest log | @qa`

## Weekly Benchmark Calculations
For each week ending date:
- `hallucination_attributed_rework_hours = sum(hours for all valid H1..H5 rows)`
- `total_rework_hours = requirement_change_rework_hours + hallucination_attributed_rework_hours`
- `hallucination_rework_rate = hallucination_attributed_rework_hours / max(total_rework_hours, 0.01)`
- `high_severity_event_count = count(rows where severity == S3)`

## Baseline And Targets (Pilot)
### Baseline Window (first 2 weeks)
- Establish initial median for attributed rework hours and event count.
- No pass/fail gate during baseline; only quality of capture is scored.

### 30 Day Target
- >= 90% of rework events include complete evidence fields.
- <= 3 unresolved `S2+` events in rolling window.

### 60 Day Target
- Hallucination rework rate <= 0.25 of total rework hours.
- `S3` event count <= 1 per two-week window.

### 90 Day Target
- Hallucination rework rate <= 0.15 of total rework hours.
- Zero repeated `H2` or `H3` events on the same story after corrective action.

## Quality Gates
- A rework entry without both incorrect and corrective artifact links is invalid.
- A rework entry without reviewer sign-off is excluded from KPI rollups.
- If invalid entry rate > 20% in a week, open a governance task and mark KPI status `At Risk`.

## Review Cadence
- Weekly: @po + @qa validate entries and roll-up metrics.
- Monthly: @architect reviews patterns and proposes guardrail updates.
- Decision deltas captured in `docs/decision.md` when threshold changes are approved.
