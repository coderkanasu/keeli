# Task: Add Epics and Milestones

**Status:** Completed
**Priority:** P1
**Created:** 2026-02-23T03:07:53Z
**Completed:** 2026-02-23T03:39:35Z
**Depends On:** None
**Context:** None
**Persona:** @architect

## Objective
Introduce Epics and Milestones to Keeli to allow grouping related tasks together.
- Add `keeli epic <title>` to create an epic file (`docs/tasks/epic-<slug>.md`).
- Add `--epic` flag to `keeli start`, `keeli bug`, and `keeli feature` to associate tasks with an epic.
- Update `keeli list` to optionally filter by epic (`--epic`).
- Update templates to include the `**Epic:**` field.

## Checklist
- [x] Define objective and scope clearly
- [x] Break task into sub-tasks in docs/tasks/
- [x] Record decision in docs/decision.md if applicable
- [x] Assign priority and context
- [ ] @developer review scope before starting
- [ ] Log completion in docs/ai_log.md

## Notes
<!-- @developer: add implementation notes, questions, blockers -->