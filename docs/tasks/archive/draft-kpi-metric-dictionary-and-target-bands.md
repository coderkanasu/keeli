# Task: Draft KPI metric dictionary and target bands

**ID:** T-0015
**Status:** Completed
**Priority:** P0
**Created:** 2026-03-12T18:17:41Z
**Completed:** 2026-03-12T18:48:06Z
**Epic:** operationalize-ai-governance-and-delivery-reliability
**Story:** define-30-60-90-governance-kpi-framework
**Depends On:** None
**Context:** None
**Persona:** @po

## What
Define baseline and target values for backlog churn, rework hours, cycle time, and defect escape rate.

## Why
<!-- Explain the user or business impact. -->

## Acceptance
<!-- Add verification steps or test evidence here. -->

## Evidence
- Docs: docs/requirements/governance-kpi-framework-30-60-90.md
- Docs: docs/requirements/weekly-governance-snapshot-template.md
- Docs: docs/requirements/weekly-governance-snapshot-sample-2026-03-12.md
- Docs: docs/requirements/sdlc-field-mapping-matrix.md
- Docs: docs/requirements/pilot-sdlc-traceability-workflow.md
- Code: src/keeli/templates.py
- Code: src/keeli/main.py

## Verification
- Test: /Users/spatil/Documents/persona-cli/.venv/bin/python -m pytest tests/test_commands.py tests/test_mcp_server.py tests/test_init.py
- Result: 69 passed
- Command: /Users/spatil/Documents/persona-cli/.venv/bin/python -m keeli.main list

## Notes
<!-- Implementation hints, gotchas, decisions. -->