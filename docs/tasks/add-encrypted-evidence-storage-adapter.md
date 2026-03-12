# Task: Add encrypted evidence storage adapter

**ID:** T-0007
**Status:** Backlog
**Priority:** P2
**Created:** 2026-03-12T03:46:23Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates
**Story:** persona-gate-engine-and-evidence-ledger
**Depends On:** build-persona-gate-pipeline-package
**Context:** None
**Persona:** @security

## What
Introduce storage adapter abstraction for sqlite3/sqlcipher backends. Support pysqlcipher3 when available, keep sqlite fallback for local/dev, and store compliance-sensitive evidence fields encrypted at rest in sqlcipher mode.

## Why
Support compliance-sensitive deployments requiring encryption at rest while preserving local developer ergonomics.

## Acceptance
- Storage adapter supports sqlite default and SQLCipher backend when available.
- Runtime can select backend via configuration without code changes.
- Sensitive evidence payload fields are encrypted in SQLCipher mode.
- Tests validate fallback behavior when `pysqlcipher3` is unavailable.

## Evidence
<!-- Link delivery artifacts (PR, commit, docs, screenshots, build logs). -->

## Verification
<!-- Link validation artifacts (tests, checks, commands with outcomes). -->

## Notes
- Avoid hard dependency on SQLCipher for local development environments.
- Deferred by product decision: implement core connector and regression pipeline first, then revisit encrypted storage hardening.
