# Task: Wire transition guards into cmd_start, cmd_story, cmd_progress, cmd_review, cmd_complete

**ID:** T-0003
**Status:** Backlog
**Priority:** P1
**Created:** 2026-02-24T19:06:56Z
**Completed:** —
**Epic:** None
**Story:** None
**Depends On:** None
**Context:** None
**Persona:** @developer

## Objective
Inject _validate_transition calls into the five CLI commands per ADR-004. Each command uses the appropriate predicate list. Fail with collected errors before any state mutation. TDD: missing-field test and passes-when-filled test per guard.
<!-- @architect: describe what needs to be done and why -->

## Checklist
- [ ] Confirm the interface / contract from @architect exists before writing a line
- [ ] Write the failing test first (red), then implement (green), then refactor
- [ ] Implement against the defined interface — no architecture shortcuts
- [ ] No business logic in controllers, no persistence logic in services
- [ ] No hardcoded values — use config/env
- [ ] No commented-out code, TODO markers, or debug prints in commits
- [ ] All tests pass locally
- [ ] Request @security review (`keeli review`)
- [ ] Update docs/project.md if a public API or data model changed
- [ ] Log completion in docs/ai_log.md

## Notes
<!-- @developer: add implementation notes, questions, blockers -->
