# Task: Build persona gate pipeline package

**ID:** T-0006
**Status:** Completed
**Priority:** P0
**Created:** 2026-03-12T03:46:23Z
**Completed:** 2026-03-12T13:11:49Z
**Epic:** pipeline-persona-routing-and-compliance-gates
**Story:** persona-gate-engine-and-evidence-ledger
**Depends On:** None
**Context:** None
**Persona:** @architect

## What
Create src/keeli/pipeline modules (PersonaGate, AuditTrail, RegressionScope, PipelineRunner). Add ordered gate graph Analyst→Architect→Security→QA→Regression and persist gate evidence into keeli_state.db with deterministic status transitions.

## Why
Create a deterministic, testable orchestration core that enforces persona order and evidence integrity.

## Acceptance
- `src/keeli/pipeline/` package created with PersonaGate, AuditTrail, RegressionScope, and PipelineRunner modules.
- Ordered gate graph enforcement implemented (Analyst -> Architect -> Security -> QA -> Regression).
- Evidence write path persists gate decisions/events in `keeli_state.db`.
- Unit tests cover valid transition, blocked transition, and evidence persistence paths.

## Notes
- Keep interfaces narrow so CLI/MCP/hook callers share the same runner implementation.