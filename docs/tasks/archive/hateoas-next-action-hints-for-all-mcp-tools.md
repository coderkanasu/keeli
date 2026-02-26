# Task: HATEOAS next-action hints for all MCP tools

**ID:** T-0006
**Status:** Completed
**Priority:** P1
**Created:** 2026-02-26T03:13:14Z
**Completed:** 2026-02-26T03:13:21Z
**Epic:** None
**Story:** None
**Depends On:** None
**Context:** None
**Persona:** @architect

## Objective

**Why:** After adding `keeli_chain` and `keeli_skill_scan` to the MCP server, every tool's success
response was opaque — an LLM agent had no signal about what to call next, forcing unnecessary
round-trips.

**Goal:** Implement `_with_next()` + `_NEXT_ACTIONS` so every MCP tool's success response appends
a `## ⛓ Suggested Next Actions` block with a JSON array + bullet list of next tool calls.

**Implemented:** Wired into all 13 success `return [TextContent(...)]` paths in `call_tool()`.
145/145 tests pass. Completed 2026-02-25T22:43:34Z.

## Checklist
- [x] STOP: is the tech stack recorded in docs/skills.md? If not, ask before designing anything
- [x] STOP: are NFRs defined in the story/epic? If not, ask @po before designing interfaces
- [x] STOP: if any requirement is ambiguous, raise it with @po or the human before proceeding
- [x] Define the interfaces and contracts first — no implementation decisions yet
- [x] Identify every seam: what could change? wrap those behind an abstraction
- [x] Check: is there a Repository, Adapter, or Strategy pattern needed here?
- [x] Verify layering: domain / service / repository / controller boundaries respected
- [x] Flag any hardcoded value, magic number, or config that belongs in environment/config
- [x] Record the design decision and rejected alternatives in docs/decision.md
- [x] Fill ## Test Strategy in the story before handing any tasks to @developer
- [x] Scalability check: does the interface hold at 10× current load? If not, record an ADR
- [x] Break into stories (keeli story) and tasks — hand off to @developer, do not implement
- [x] Confirm blast radius: what else breaks if this interface changes?
- [x] Log completion in docs/ai_log.md

## Notes
<!-- @developer: add implementation notes, questions, blockers -->
