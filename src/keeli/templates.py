"""
Keeli v6.0 Markdown and Agent Context Templates.
"""

TASK_TEMPLATE = """# ${task_id}: ${title}

**Status:** ${status}
**Priority:** ${priority}
**Created:** ${timestamp}
**Completed:** ${completed}
**Depends On:** ${depends_on}
**Tags:** ${tags}

## Description
${description}

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Implementation Notes
<!-- Implementation hints, blockers, decisions. -->

## Evidence
<!-- Links to PRs, tests, or screenshots. -->

## Notes
<!-- Any additional context -->
"""

CLAUDE_MD = """# Project Instructions (CLAUDE.md)

Current focus: {focus}

## Build & Test
- Build: {build_command}
- Test: {test_command}

## CRDT Context Protocol (v6.0)
- Tasks live in `.keeli/tasks/` (gitignored, never indexed by LLM tools).
- Source of truth is the SQLite event log (`task_events`), not markdown files.
- Markdown files are materialized views — rebuildable via `keeli sync`.
- No SHA-256 expected_hash locks. Instead, use vector clocks for awareness.
- Field-level independence: editing `status` never conflicts with editing `priority`.
- Always pass `session_id` and `branch` explicitly in MCP tool calls.
- Use `keeli_detect_conflicts(task_id)` to observe concurrent edit history.

## Evidence-First Remediation Protocol (Model-Agnostic)
Use this loop for data integrity, bug fixing, and incident-style remediation whether the agent is Devin, Claude, or GPT.

1. Baseline first
- Start/confirm a session with `keeli_sessions(start)`.
- Save measurable before-state with `keeli_memory(set)`.
- Capture scoped digest with `keeli_context(digest)`.

2. Isolate concrete defects
- Move from aggregate symptoms to specific records/inputs.
- Store defect list and hypotheses in working memory.

3. Apply minimal patch
- Change only required state/logic.
- Checkpoint immediately after mutation with `keeli_sessions(checkpoint)`.

4. Re-verify end-to-end
- Re-run the baseline check and compare before/after.
- Validate downstream consumers, not only local logic.

5. Instrument prevention
- Add anomaly logging or warnings at ingestion and analysis boundaries.
- Save durable lesson with `keeli_knowledge(save)`.
"""
SKILL_TEMPLATE = """---
name: keeli-task-manager
description: Keeli v6.0 task management with field-level CRDTs, isolated workspace, and connection-scoped sessions.
---

# Keeli Task Management Skill (v6.0)

## CRITICAL WORKFLOW: Field-Level Concurrency (No Locks!)
v6.0 replaces v5.1's SHA-256 expected_hash with automatic CRDT merging.

**MANDATORY SEQUENCE:**
1. **Read**: Call `keeli_get(task_id)` to see current state and `VECTOR_CLOCK`.
2. **Edit Freely**: Call `keeli_edit_field`, `keeli_active`, `keeli_complete` without any hash.
3. **Concurrent edits auto-merge**: Agent A changes `status` while Agent B changes `priority` → both succeed, no 409.
4. **Observe**: Call `keeli_detect_conflicts(task_id)` to see if concurrent edits touched the SAME field.

## Tools Available
- `keeli_get(task_id)` → Markdown + `VECTOR_CLOCK` header.
- `keeli_get_state(task_id)` → Structured JSON state with vector clock.
- `keeli_complete(task_id, rationale, actor, branch, session_id)` → Archive with audit trail.
- `keeli_active(task_id, actor, branch, session_id)` → Move to active.
- `keeli_block(task_id, reason, actor, branch, session_id)` → Block with reason.
- `keeli_unblock(task_id, actor, branch, session_id)` → Return to backlog.
- `keeli_edit_field(task_id, field, value, actor, branch, session_id)` → Generic field mutation.
- `keeli_add_tags(task_id, tags, ...)` / `keeli_remove_tags(task_id, tags, ...)` → OR-Set operations.
- `keeli_detect_conflicts(task_id, lookback_seconds)` → Observability for concurrent edits.
- `keeli_digest(tier, budget, session_id, branch)` → Token-budgeted scoped context.
- `keeli_context_set(key, value, scope, scope_id)` / `keeli_context_get(key, session_id, branch)`.
- `keeli_session_start(name, branch, focus_task_id)` → Returns session_id.
- `keeli_session_focus(task_id, session_id)` → Scoped focus (no global flag!).
- `keeli_session_checkpoint(note, session_id, pending_decisions)`.
"""

MCP_TEMPLATE = """{{
  "mcpServers": {{
    "keeli": {{
      "type": "stdio",
      "command": "python3",
      "args": [
        "{mcp_path}"
      ],
      "env": {{
        "PYTHONPATH": "."
      }}
    }}
  }}
}}
"""
