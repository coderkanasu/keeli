"""
Keeli v4.0 Markdown templates.
"""

TASK_TEMPLATE = """# ${task_id}: ${title}

**Status:** ${status}
**Priority:** ${priority}
**Created:** ${timestamp}
**Completed:** —
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

## Conventions
- Follow PEP 8 for Python.
- Use Keeli for task management.
"""

SKILL_TEMPLATE = """---
name: keeli-task-manager
description: Keeli v5.1 task management with optimistic locking. 
---

# Keeli Task Management Skill (v5.1)

## CRITICAL WORKFLOW: Optimistic Locking
All state-changing tools (`keeli_complete`, `keeli_active`, `keeli_block`, `keeli_review`) now require an **expected_hash** to prevent overwriting stale tasks.

**YOU MUST FOLLOW THIS EXACT SEQUENCE:**

1. **Read First**: Always call `keeli_get(task_id)` to fetch the latest task content.
   - The response includes a metadata header: `<!-- VERSION_HASH: sha256-abc123 -->`.
2. **Extract the Hash**: Parse that header to get the `expected_hash` value.
3. **Act with Hash**: Pass the extracted hash to any state-changing tool.
   - Example: `keeli_complete(task_id="T-0001", expected_hash="sha256-abc123", rationale="Fixed the bug")`
4. **Handle Conflicts**: If you receive a `409 CONFLICT` error, it means another agent updated the task. Immediately call `keeli_get` again to fetch the new hash and content, then re-attempt your action with the updated hash.

## Tools Available (v5.1)

- `keeli_get(task_id)` → Returns markdown + **VERSION_HASH** header.
- `keeli_complete(task_id, expected_hash, rationale, session_id)` → Requires hash.
- `keeli_active(task_id, expected_hash, session_id)` → Requires hash.
- `keeli_block(task_id, expected_hash, reason, session_id)` → Requires hash.
- `keeli_digest(session_id, budget)` → Prioritized context (Active > Audit > Backlog).
- `keeli_context_set(key, value, scope)` → Override global context for your session.
- `keeli_session_start(name)` → Initialize a new stateful session.
- `keeli_session_checkpoint(note)` → Save reasoning and state.

## Best Practices
- Never skip the `keeli_get` step before modifying a task.
- Always include a `rationale` or `reason` when completing/blocking—it gets stored in the audit trail.
- Use `keeli_digest` frequently to stay updated on session focus and concurrent changes.
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
