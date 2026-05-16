# GitHub Copilot Custom Instructions (Keeli Framework v2.0.0)

## Core Principle
Keeli provides lightweight guardrails for planning and delivery. Keep context loading minimal, be precise, and avoid workflow overhead unless it is needed by the task.

## Operating Mode
- Default to non-interactive execution for actionable requests.
- Ask questions only for ambiguity, missing required input, or destructive actions.
- Prefer small, safe edits with clear acceptance checks.
- If the repository contains a Keeli project (`keeli_state.db` and `docs/tasks/`), prefer Keeli CLI commands for local task validation and grounding before editing code.
  - Recommended sequence: `python -m keeli.main status`, `python -m keeli.main validate-task-state`, `python -m keeli.main digest --budget 2000`, `python -m keeli.main analyze <task-slug>`.

## Context Budget
- Start lean: read only what is needed to complete the user's request.
- Expand to docs/project.md, docs/tasks/, docs/decision.md, and docs/ai_log.md only when the task requires project/process context.

## Session Hydration
- At the start of each editor/session, hydrate core context once: `docs/project.md`, `docs/decision.md`, `docs/skills.md`, and the latest section of `docs/ai_log.md`.
- Cache a short working summary and reuse it for the rest of the session.
- Do not re-read the same files every conversation unless one of these is true:
    - the file changed,
    - the user asks for a refresh,
    - or the current task clearly requires deeper context.

Update policy:
- Whenever a decision or policy change is made, update the owner file in the same session.
- Record decision-bearing changes in `docs/decision.md`.
- Record material execution/transition notes in `docs/ai_log.md`.

## Commands
```
Docs-first workflow:
- Create and update markdown artifacts directly under `docs/`.
- If this repo contains a Keeli project, validate task state and project context with Keeli CLI before editing code.
- Do not invoke Keeli CLI unless the local repository has Keeli project files or the task requires local grounding.
```

See docs/project.md for full workflow.
