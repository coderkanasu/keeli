# GitHub Copilot Custom Instructions (Keeli Framework v4.0.1)

## Core Principle
Keeli provides lightweight guardrails for planning and delivery. Source of truth is the filesystem (`docs/tasks/`).

## Operating Mode
- If the repository contains a Keeli project (`keeli_state.db` and `docs/tasks/`), prefer Keeli CLI commands/MCP tools for local task validation and grounding before editing code.
- Recommended sequence: `keeli digest`, `keeli next`, `keeli active <task-id>`.

## Context Budget
- Use `keeli digest --budget 2000` to hydrate core context once per session.

## Task Status Workflow
- `backlog`: Not started.
- `active`: In progress.
- `review`: Ready for review.
- `blocked`: Waiting on external factors.
- `archive`: Completed.

## Tools (CLI or MCP)
- `keeli start "Title"`: Create task.
- `keeli active <id>`: Start working.
- `keeli complete <id>`: Finish task.
- `keeli next`: Recommend next priority.
- `keeli digest`: Context snapshot.
