# Task: Build external connector framework

**ID:** T-0013
**Status:** Backlog
**Priority:** P1
**Created:** 2026-03-12T03:50:21Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates
**Story:** json-lineage-contracts-and-compliance-outputs
**Depends On:** None
**Context:** None
**Persona:** @architect

## What
Define connector interface for pipeline state propagation (validate_config, publish_transition, reconcile_external_id, fetch_status). Add connector registry and runtime selection via config so any number of connectors can be installed without core code changes.

## Why
Prevent provider lock-in and avoid hardcoded external integration logic inside pipeline core.

## Acceptance
- Shared connector interface defined and documented.
- Connector registry supports multiple enabled connectors from config.
- Pipeline runner emits transition events through registry without provider-specific branching.
- Unit tests verify registry dispatch and connector failure isolation.

## Evidence
<!-- Link delivery artifacts (PR, commit, docs, screenshots, build logs). -->

## Verification
<!-- Link validation artifacts (tests, checks, commands with outcomes). -->

## Notes
- Keep Trello implementation in a dedicated adapter module that consumes this interface.
