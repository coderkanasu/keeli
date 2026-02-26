# Task: keeli chain — sequential command pipeline with slug propagation

**ID:** T-0005
**Status:** Completed
**Priority:** P1
**Created:** 2026-02-25T19:36:31Z
**Completed:** 2026-02-25T20:17:16Z
**Epic:** None
**Story:** None
**Depends On:** None
**Context:** None
**Persona:** @architect

## Objective

**Why:** Every keeli workflow requires running 3-5 commands in a fixed sequence (e.g. start →
analyze → progress, or scan → apply → analyze). Today the user must run each command separately,
copy-paste the slug, and check output between steps. This is friction for both human developers and
agentic AI clients (MCP).

**Goal:** Add `keeli chain` — a pipeline executor that runs an ordered sequence of keeli sub-
commands, passing the *output slug/ID* of each step as implicit context to the next step.

**Design — two usage styles:**

**Style 1: Inline pipeline (human-friendly)**
```bash
keeli chain \
  "start:Implement login endpoint" \
  "analyze:auto"                   \
  "progress:auto"
```
`auto` means "use the slug/ID produced by the previous step".

**Style 2: Chain file (agentic/repeatable)**
```yaml
# .keeli/chains/new-feature.yaml
name: new-feature
steps:
  - cmd: start
    args: ["{{title}}"]
  - cmd: analyze
    args: ["auto"]
  - cmd: progress
    args: ["auto"]
```
```bash
keeli chain run new-feature --var title="Implement login"
```

**Interface contracts (define before implementation):**
- `_run_chain(steps: list[ChainStep], ctx: ChainContext) -> ChainResult`
- `ChainStep`: `cmd: str`, `args: list[str]`, `skip_on_error: bool = False`
- `ChainContext`: `slug: str | None`, `id: str | None`, `vars: dict[str, str]`
- Each step calls the existing `cmd_*` dispatch functions — no duplication of logic.
- `auto` is resolved by inspecting `ChainContext.slug` before calling the step.
- Errors in a step halt the chain (default) unless `skip_on_error=True`.

**Built-in named chains (bundled defaults):**
| Chain name | Steps |
|---|---|
| `new-task` | start → analyze → progress |
| `close-task` | review → complete |
| `onboard` | skill scan --apply → analyze (first backlog task) |

**Acceptance Criteria:**
- [x] `keeli chain "start:My Task" "analyze:auto" "progress:auto"` runs all three steps in
  sequence with the slug from `start` propagated automatically.
- [x] A failed step prints the error and halts the chain by default.
- [x] `--dry-run` prints each step + resolved args without executing.
- [x] `keeli chain list` shows available built-in and project-local chains.
- [x] Chain file support (`keeli chain run <name>`) with `--var` substitution.
- [x] MCP tool `keeli_chain` exposed on the MCP server accepting the same step list.
- [x] All steps individually logged to `docs/ai_log.md`.

**Out of Scope (this task):**
- Parallel step execution (sequential only in v1).
- Conditional branching (`if: condition` in chain files).
- Rollback/undo on failure.

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
