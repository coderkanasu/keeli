# Task: Add install-hooks command for pipeline gates

**ID:** T-0010
**Status:** Backlog
**Priority:** P1
**Created:** 2026-03-12T03:46:33Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates
**Story:** persona-gate-engine-and-evidence-ledger
**Depends On:** build-persona-gate-pipeline-package
**Context:** None
**Persona:** @developer

## What
Add explicit keeli install-hooks command to install/update pre-commit and pre-push hooks that execute pipeline gate validation and block push on missing persona evidence or unresolved blockers.

## Why
Provide an explicit and reproducible hook installation path for teams and CI images.

## Acceptance
- `keeli install-hooks` installs or updates pre-commit and pre-push hooks.
- Hook scripts call pipeline validation in non-interactive mode.
- Push is blocked when required persona evidence is missing.
- Tests cover install idempotency and failure exit codes.

## Notes
- Keep existing `keeli init` behavior, but make hook lifecycle independently manageable.
