# Task: Derive regression scope from affects

**ID:** T-0009
**Status:** Backlog
**Priority:** P0
**Created:** 2026-03-12T03:46:24Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates
**Story:** regression-scope-and-side-effect-blocking
**Depends On:** build-persona-gate-pipeline-package
**Context:** None
**Persona:** @qa

## What
Add affects parser and scope resolver that computes impacted modules/tests. Block gate progression when unresolved side effects or failing scoped regression checks are detected. Persist regression decisions and blockers in evidence ledger.

## Why
Reduce production risk by requiring targeted regression evidence before advancing high-impact tasks.

## Acceptance
- `affects` parser derives deterministic impacted test/module scope.
- Side-effect flags produce explicit blockers with machine-readable reasons.
- Gate advancement is blocked when scoped regression checks fail.
- Evidence ledger stores scope derivation and blocker decisions.

## Evidence
<!-- Link delivery artifacts (PR, commit, docs, screenshots, build logs). -->

## Verification
<!-- Link validation artifacts (tests, checks, commands with outcomes). -->

## Notes
- Prefer conservative scope expansion when affected areas are ambiguous.
