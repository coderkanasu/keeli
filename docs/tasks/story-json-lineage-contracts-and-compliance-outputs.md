# Story: JSON lineage contracts and compliance outputs

**ID:** S-0003
**Status:** Backlog
**Priority:** P1
**Created:** 2026-03-12T03:46:10Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates

## User Story
As a ai automation engineer, I want emit and consume deterministic pipeline JSON with checksums and lineage so that I can support compliance reporting and reproducible automation.

## Acceptance Criteria
- [ ] epic_task_context.json contains lineage, checksum, and gate evidence pointers
- [ ] CLI emits compliance report JSON with deterministic schema

## Non-Functional Requirements
- JSON schema must be deterministic and versioned for automation clients.
- Checksum generation must be stable across runs for identical payloads.
- Compliance report generation should complete under 300ms for typical task context.

## Tasks
- build-external-connector-framework
- implement-pipeline-json-lineage-contract
- add-ai-pipeline-single-shot-cli
- implement-trello-pipeline-state-sync

## Done
- [ ] User story clear
- [ ] Acceptance criteria testable
- [ ] NFRs identified (or explicitly none)
- [ ] All tasks completed

## Notes
- Primary contract artifact: epic_task_context.json
- Keep compatibility with existing CLI JSON envelope (`ok`, `command`, `timestamp`, `data`)
- External integrations must be implemented as connectors via a shared interface/registry.
