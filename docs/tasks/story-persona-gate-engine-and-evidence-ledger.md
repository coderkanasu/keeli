# Story: Persona gate engine and evidence ledger

**ID:** S-0002
**Status:** Backlog
**Priority:** P0
**Created:** 2026-03-12T03:46:10Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates

## User Story
As a platform engineer, I want enforce ordered persona gates with persisted evidence so that I can prevent unsafe transitions and provide audit-grade traceability.

## Acceptance Criteria
- [ ] Transitions blocked unless prior gate evidence exists
- [ ] Evidence rows persisted per gate with timestamps and actor metadata

## Non-Functional Requirements
- Deterministic gate ordering and validation decisions for identical inputs.
- Evidence records must be immutable after insertion (append-only ledger behavior).
- Query performance target: gate/evidence lookup under 100ms for common task scopes.

## Tasks
- build-persona-gate-pipeline-package
- add-encrypted-evidence-storage-adapter
- add-install-hooks-command-for-pipeline-gates

## Done
- [ ] User story clear
- [ ] Acceptance criteria testable
- [ ] NFRs identified (or explicitly none)
- [ ] All tasks completed

## Notes
- Reference architecture: docs/requirements/pipeline-orchestration-architecture.md
- Gate order baseline: Analyst -> Architect -> Security -> QA -> Regression
