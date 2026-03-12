# Story: Regression scope and side-effect blocking

**ID:** S-0004
**Status:** Backlog
**Priority:** P0
**Created:** 2026-03-12T03:46:10Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates

## User Story
As a qa engineer, I want derive regression scope from affects and block risky side effects so that I can reduce regressions and enforce safe releases.

## Acceptance Criteria
- [ ] Affects map generates deterministic regression test scope
- [ ] Pipeline blocks progression when side-effect checks fail

## Non-Functional Requirements
- Regression scope selection must be deterministic for identical affects input.
- Blocking reason payloads must be human-readable and machine-parseable.
- Scope derivation should favor conservative inclusion over false negatives.

## Tasks
- derive-regression-scope-from-affects

## Done
- [ ] User story clear
- [ ] Acceptance criteria testable
- [ ] NFRs identified (or explicitly none)
- [ ] All tasks completed

## Notes
- Affects sources: task markdown metadata and lineage JSON context.
- Persist blocker decisions in evidence ledger for auditability.
