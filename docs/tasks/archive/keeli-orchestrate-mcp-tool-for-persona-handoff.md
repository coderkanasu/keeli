# Task: keeli_orchestrate MCP tool for persona handoff

**ID:** T-0007
**Status:** Completed
**Priority:** P1
**Created:** 2026-02-26T03:24:38Z
**Completed:** 2026-02-26T03:28:45Z
**Epic:** None
**Story:** None
**Depends On:** None
**Context:** None
**Persona:** @architect

## Objective
Expose keeli_orchestrate(task_slug) on the MCP server. Returns structured persona handoff: task_id, required_persona, system_prompt_hint (pulled from personas.md), context_snapshot, suggested_next_tool+args, blocking_reason. Read-only — mutates no state.
<!-- @architect: describe what needs to be done and why -->

## Checklist
- [ ] STOP: is the tech stack recorded in docs/skills.md? If not, ask before designing anything
- [ ] STOP: are NFRs defined in the story/epic? If not, ask @po before designing interfaces
- [ ] STOP: if any requirement is ambiguous, raise it with @po or the human before proceeding
- [ ] Define the interfaces and contracts first — no implementation decisions yet
- [ ] Identify every seam: what could change? wrap those behind an abstraction
- [ ] Check: is there a Repository, Adapter, or Strategy pattern needed here?
- [ ] Verify layering: domain / service / repository / controller boundaries respected
- [ ] Flag any hardcoded value, magic number, or config that belongs in environment/config
- [ ] Record the design decision and rejected alternatives in docs/decision.md
- [ ] Fill ## Test Strategy in the story before handing any tasks to @developer
- [ ] Scalability check: does the interface hold at 10× current load? If not, record an ADR
- [ ] Break into stories (keeli story) and tasks — hand off to @developer, do not implement
- [ ] Confirm blast radius: what else breaks if this interface changes?
- [ ] Log completion in docs/ai_log.md

## Notes
<!-- @developer: add implementation notes, questions, blockers -->