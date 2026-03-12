# Task: Implement pipeline JSON lineage contract

**ID:** T-0008
**Status:** Backlog
**Priority:** P1
**Created:** 2026-03-12T03:46:23Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates
**Story:** json-lineage-contracts-and-compliance-outputs
**Depends On:** build-persona-gate-pipeline-package
**Context:** None
**Persona:** @architect

## What
Define epic_task_context.json schema including task lineage, checksums, affects, gate evidence refs, and compliance report sections. Add validation + checksum verification and deterministic JSON output contract for CLI/MCP consumers.

## Why
Provide a stable machine contract for compliance tooling, AI agents, and external reporting systems.

## Acceptance
- `epic_task_context.json` schema defined and versioned.
- Lineage and checksum fields are validated and reproducible.
- Compliance payload includes gate evidence references and pass/fail summaries.
- Tests cover schema validation and checksum mismatch handling.

## Notes
- Keep output compatible with existing JSON envelope conventions.
