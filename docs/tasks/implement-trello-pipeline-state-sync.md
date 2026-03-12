# Task: Implement Trello pipeline state sync

**ID:** T-0012
**Status:** Backlog
**Priority:** P2
**Created:** 2026-03-12T03:46:33Z
**Completed:** —
**Epic:** pipeline-persona-routing-and-compliance-gates
**Story:** json-lineage-contracts-and-compliance-outputs
**Depends On:** build-external-connector-framework
**Context:** None
**Persona:** @developer

## What
Implement a Trello connector adapter on top of the shared connector framework: map internal gate states to Trello lists, push external_id updates at gate transitions, and record sync receipts/failures in audit evidence.

## Why
Keep provider-specific behavior isolated so pipeline core supports any number of connectors without hardcoded integrations.

## Acceptance
- Trello adapter implements the shared connector interface.
- Connector registry can enable/disable Trello without code changes in pipeline core.
- Transition publish and external_id reconciliation events are audited in evidence ledger.

## Evidence
<!-- Link delivery artifacts (PR, commit, docs, screenshots, build logs). -->

## Verification
<!-- Link validation artifacts (tests, checks, commands with outcomes). -->

## Notes
- Trello is the first connector, not the architecture baseline.
