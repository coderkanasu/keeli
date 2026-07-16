---
name: keeli-task-manager
description: Keeli task management toolkit. Use when users mention tasks, backlog, progress, completing work, or ask what to work on next. Provides task creation, status transitions, and context digest tools. Activate automatically when task-related keywords are detected.
---

# Keeli Task Management Skill

## When to use this skill
Use this skill whenever the user wants to:
- Create, start, progress, review, block, unblock, or complete a task
- See the next task to work on
- Get a token-budgeted context digest
- View task history or audit trail

## Tools available (via MCP)
- `keeli_start` — Create task
- `keeli_progress` — Move task to active
- `keeli_complete` — Move task to archive
- `keeli_block` — Block a task with reason
- `keeli_unblock` — Unblock a task
- `keeli_review` — Move task to review
- `keeli_next` — Show next task by priority
- `keeli_list` — List tasks by status
- `keeli_get` — Show task details
- `keeli_digest` — Get token-budgeted context
- `keeli_sync` — Explicitly rebuild the task index
- `keeli_doctor` — Check health of tasks and index

## Workflow steps
1. When the user mentions a task, first call `keeli_digest` to get current context.
2. Use `keeli_next` to identify the next priority task.
3. For task transitions, call the appropriate tool (e.g., `keeli_progress`, `keeli_complete`).
4. After any state change, call `keeli_digest` to refresh context.
5. For questions about a specific task, use `keeli_get <id>`.

## File-based state awareness
Tasks are stored in `docs/tasks/` with directories representing status:
- `docs/tasks/backlog/` — Backlog
- `docs/tasks/active/` — In Progress
- `docs/tasks/review/` — Review
- `docs/tasks/blocked/` — Blocked
- `docs/tasks/archive/` — Completed

The MCP server reads and writes to these files, so state is always git-tracked and human-readable.

## Best practices
- Always confirm with the user before completing a task.
- Use `keeli_digest --budget 1500` to keep context lean.
- When creating a task, ask the user for title, priority, and optional tags.
