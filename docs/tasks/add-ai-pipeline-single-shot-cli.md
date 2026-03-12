# Task: Add ai-pipeline single-shot CLI

**ID:** T-0011
**Status:** Backlog
**Priority:** P1
**Created:** 2026-03-12T03:46:33Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates
**Story:** json-lineage-contracts-and-compliance-outputs
**Depends On:** build-persona-gate-pipeline-package, implement-pipeline-json-lineage-contract
**Context:** None
**Persona:** @developer

## What
Implement keeli ai-pipeline --task-slug <slug> to run persona pipeline once, emit JSON contract output, and support AI prompt payload mode for Copilot/Claude integrations.

## Why
Enable deterministic one-shot orchestration for AI agents and CI automation.

## Acceptance
- `keeli ai-pipeline --task-slug <slug> --json` executes a single pipeline pass.
- Output includes gate decisions, evidence refs, and compliance payload in shared envelope.
- Non-zero exit and machine-readable error on gate blockers.
- CLI and integration tests cover success and blocked paths.

## Notes
- Reuse pipeline runner internals rather than duplicating gate logic in CLI command.
