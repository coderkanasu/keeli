# Task: API error handling strategy

**Status:** Backlog
**Priority:** P0
**Created:** 2026-02-23T20:51:00Z
**Completed:** —
**Epic:** None
**Story:** None
**Depends On:** None
**Context:** None
**Persona:** @architect

## Objective
Should implement RFC 7807 Problem JSON format.
Handle: 400 (validation), 401 (auth), 403 (forbidden), 404 (not found), 500 (server).
Log all errors >= 500 to stderr for alerting.
<!-- @architect: describe what needs to be done and why -->

## Checklist
- [ ] STOP: is the tech stack recorded in docs/skills.md? If not, ask before designing anything
- [ ] Define the interfaces and contracts first — no implementation decisions yet
- [ ] Identify every seam: what could change? wrap those behind an abstraction
- [ ] Check: is there a Repository, Adapter, or Strategy pattern needed here?
- [ ] Verify layering: domain / service / repository / controller boundaries respected
- [ ] Flag any hardcoded value, magic number, or config that belongs in environment/config
- [ ] Record the design decision and rejected alternatives in docs/decision.md
- [ ] Break into stories (keeli story) and tasks — hand off to @developer, do not implement
- [ ] Confirm blast radius: what else breaks if this interface changes?
- [ ] Log completion in docs/ai_log.md

## Notes
<!-- @developer: add implementation notes, questions, blockers -->
