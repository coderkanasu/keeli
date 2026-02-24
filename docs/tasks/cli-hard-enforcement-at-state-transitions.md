# Task: CLI hard enforcement at state transitions

**ID:** T-0001
**Status:** Completed
**Priority:** P1
**Created:** 2026-02-24T19:06:14Z
**Completed:** 2026-02-24T19:15:00Z
**Epic:** None
**Story:** None
**Depends On:** None
**Context:** None
**Persona:** @architect

## Objective
Implement deterministic, testable hard enforcement guards at CLI state-transition
commands so that structural completeness is validated before any state mutation
occurs. See ADR-004 in docs/decision.md for the full rationale and rejected
alternatives.

Guards required (per ADR-004):
- `keeli start` (task linked to story): fail if parent story missing filled
  `## Non-Functional Requirements` or `## Test Strategy` sections
- `keeli progress`: fail if task Objective field is unfilled (`<!-- … -->` placeholder)
- `keeli review`: fail if @developer checklist has unchecked `- [ ]` items
- `keeli complete`: fail if @security checklist has unchecked `- [ ]` items
- `keeli story`: fail if parent epic missing filled `## Non-Functional Requirements`

All guards share a single `_validate_transition(path, rules) -> list[str]` helper.
Each rule is a `(description, predicate)` pair. Errors are collected and printed
together so the agent sees all failures at once, not one at a time.

## Checklist
- [x] STOP: is the tech stack recorded in docs/skills.md? Yes — Python 3.12+, pathlib, argparse, pytest
- [x] STOP: are NFRs defined? This is a CLI tool task — guard logic is CPU-trivial, no latency NFR
- [x] STOP: requirements are unambiguous — see ADR-004
- [x] Define interfaces and contracts first — `_validate_transition(path, rules)` is the seam
- [x] Identify seams: the predicate list is the only thing that changes per command — inject it
- [x] Check: Repository/Adapter/Strategy needed? No — predicates are pure functions, no external I/O
- [x] Verify layering: guard logic stays in main.py dispatch, not in template or MCP server
- [x] Flag hardcoded values: section headers are string constants, not magic strings inline
- [x] Record decision in docs/decision.md — ADR-004 written
- [x] Fill ## Test Strategy in story before handing to @developer (standalone task, no parent story — N/A)
- [x] Scalability: guard runs on a single markdown file read — trivially O(n lines), no issue at 10×
- [x] Break into @developer tasks and hand off — T-0002 (helper + predicates), T-0003 (wire guards)
- [x] Confirm blast radius: keeli start/progress/review/complete/story all affected; MCP handlers call same commands so guards apply there too
- [x] Log completion in docs/ai_log.md

## Notes
### Interfaces (@architect)
```python
# keeli/main.py — add near top of file with other helpers
def _validate_transition(path: Path, rules: list[tuple[str, Callable[[str], bool]]]) -> list[str]:
    """Return a list of human-readable error strings for any failed rule.
    Empty list means all rules passed.
    Each rule: (error_message, predicate(file_text) -> True means PASS).
    """

# Section-presence helper (reusable predicate factory)
def _section_is_filled(section_header: str) -> Callable[[str], bool]:
    """Returns a predicate that passes only if the section exists AND
    contains at least one non-comment, non-empty line after the header."""
```

### Guard injection points
- `cmd_start`: after resolving parent story path, before writing the task file
- `cmd_progress`: after resolving task path, before updating Status
- `cmd_review`: after resolving task path, before updating Status
- `cmd_complete`: after resolving task path, before updating Status and archiving
- `cmd_story`: after resolving parent epic path, before writing the story file

### Section constants (to avoid magic strings)
```python
_SEC_NFR = "## Non-Functional Requirements"
_SEC_TEST_STRATEGY = "## Test Strategy"
```

### Blast radius confirmed
All five commands listed above. MCP `call_tool` handlers delegate to the same
`cmd_*` functions so guards are automatically inherited — no MCP-layer changes needed.
