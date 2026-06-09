# SDLC Field Mapping Matrix (Keeli -> Jira / Azure Boards / GitHub Projects)

## Purpose
Map Keeli Epic/Story/Task records to external tracking systems to maintain one source of truth with minimal duplicate entry.

## Markdown Ownership (Persona -> File)

| File | Primary Owner | Backup Owner | Update Trigger |
|---|---|---|---|
| docs/project.md | @po | @architect | Product scope, goals, or architecture summary changed |
| docs/decision.md | @architect | @po | Any architectural or policy decision is made |
| docs/ai_log.md | @developer | @qa | Material implementation, validation, or transition event occurs |
| docs/skills.md | @architect | @developer | Tech stack/constraint decision changes |
| docs/personas.md | @po | @architect | Persona responsibilities or boundaries change |
| docs/tasks/*.md | Persona in task `**Persona:**` field | @developer | Task state, scope, evidence, or verification changes |
| docs/tasks/archive/*.md | @developer | @qa | Completion/archive metadata changes |
| docs/requirements/*.md | @po | @architect | Requirement baseline, KPI definitions, or governance policy changes |
| .github/prompts/*.prompt.md | Matching persona prompt owner | @architect | Persona operating instructions change |
| .github/copilot-instructions.md | @architect | @po | Guardrails, session hydration, or workflow policy changes |

### Ownership Policy
- Owners should update their files immediately in the same work session whenever a decision or policy change is made.
- If an owner is unavailable, the backup owner updates and logs the reason in docs/ai_log.md.
- Decision-bearing updates must include a corresponding entry in docs/decision.md.
- Requirement-bearing updates must keep links consistent across docs/requirements/ and docs/project.md.

## Entity Mapping

| Keeli Entity | Keeli Field | Jira | Azure Boards | GitHub Projects |
|---|---|---|---|---|
| Epic | ID (E-xxxx) | Issue Key (Epic) | Work Item ID (Epic) | Item ID + custom field |
| Epic | slug | Summary label or custom field | Title suffix / custom field | Title tag or field |
| Epic | Priority (P0/P1/P2) | Priority | Priority | Single select field |
| Story | ID (S-xxxx) | Story issue key | User Story work item ID | Item ID + parent link |
| Story | Epic | Epic Link | Parent | Parent item relation |
| Story | AC / NFR | Description / Acceptance Criteria | Acceptance Criteria | Body / custom text |
| Task | ID (T-xxxx) | Task issue key | Task work item ID | Item ID |
| Task | Story | Parent link | Parent | Parent relation |
| Task | Depends On | Blocks / Is blocked by | Related/Predecessor | Dependency field |
| Task | Persona | Custom field (owner persona) | Custom field | Single select field |
| Task | Evidence | Attachments / links | Hyperlinks / attachments | Link field / notes |
| Task | Verification | QA evidence links | Test evidence links | Checklist + links |

## Lifecycle Status Mapping

| Keeli Status | Jira | Azure Boards | GitHub Projects |
|---|---|---|---|
| Backlog | To Do | New | Todo |
| In Progress | In Progress | Active | In Progress |
| Blocked | Blocked (custom) | Blocked | Blocked (custom field) |
| Review | In Review | Resolved (pending validation) | In Review |
| Completed | Done | Done | Done |
| Archived | Done + archived label | Done + Closed date | Done + archive view |

## Mapping Rules
- Keeli IDs remain immutable; external IDs are mapped as integration metadata.
- Completion in Keeli requires Evidence + Verification references; mirror links in external records.
- Status sync is one-way from Keeli during pilot to avoid dual-control conflicts.
- Dependency mapping must preserve blocking semantics across systems.

## Pilot Integration Notes
- Initial pilot target systems: Jira Cloud, Azure Boards, GitHub Projects.
- Minimum viable sync fields: ID, title, status, priority, parent, links.
- Optional phase: bidirectional sync only after conflict rules are defined.
