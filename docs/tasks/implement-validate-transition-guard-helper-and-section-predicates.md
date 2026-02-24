# Task: Implement _validate_transition guard helper and section predicates

**ID:** T-0002
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
Implement the _validate_transition(path, rules) helper and _section_is_filled(header) predicate factory in main.py per the interface defined in T-0001. Add _SEC_NFR and _SEC_TEST_STRATEGY constants. Write failing tests first.
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
