# Task: Fix secret-scan false positive on regex patterns

**ID:** T-0023
**Status:** Completed
**Priority:** P2
**Created:** 2026-03-16T23:29:36Z
**Completed:** 2026-03-17T19:27:03Z
**Epic:** None
**Story:** None
**Depends On:** None
**Context:** None
**Persona:** @architect

## What
Tune PII scan to avoid false positives from source-file regex definitions while preserving real secret detection

## Why
<!-- Explain the user or business impact. -->

## Acceptance
<!-- Add verification steps or test evidence here. -->

## Evidence
- Delivery artifact: docs/ai_log.md
- Commit: <git-sha>
## Verification
- Test command: pytest -q
- Validation report: tests/<file>.py
## Notes
<!-- Implementation hints, gotchas, decisions. -->