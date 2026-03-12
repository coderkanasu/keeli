# Pilot SDLC Traceability Workflow Example

## Objective
Demonstrate end-to-end traceability from Keeli Epic -> Story -> Task into external SDLC systems without duplicating planning decisions.

## Workflow
1. Create planning hierarchy in Keeli.
2. Assign immutable Keeli IDs (E/S/T) and baseline priorities.
3. Export/mirror key fields to Jira, Azure Boards, and GitHub Projects.
4. Execute work in Keeli with evidence-linked transitions.
5. Publish weekly governance snapshot using Keeli artifacts and mirrored status.

## Example Trace
- Epic: E-0004 (operationalize-ai-governance-and-delivery-reliability)
- Story: S-0006 (enforce-evidence-linked-task-completion)
- Task: T-0016 (update-task-template-to-require-acceptance-evidence)

## External Mirror (Example)

| System | External Record | Linked Keeli IDs | Notes |
|---|---|---|---|
| Jira | GOV-42 | E-0004, S-0006, T-0016 | Parent/child links match hierarchy |
| Azure Boards | 9102 | E-0004, S-0006, T-0016 | State driven from Keeli status |
| GitHub Projects | Item 188 | E-0004, S-0006, T-0016 | Evidence links added on completion |

## Verification Checklist
- [ ] Keeli hierarchy exists and is valid.
- [ ] External records include Keeli IDs in dedicated fields.
- [ ] Status transitions match mapping matrix.
- [ ] Completion includes Evidence and Verification references.
- [ ] Weekly snapshot cites both Keeli and external references.

## Escalation Rules
- If status diverges between Keeli and external board: Keeli is source of truth during pilot.
- If a required field is missing externally: block automated sync and log a governance risk.
- If evidence links are absent at completion: do not move to Completed.
