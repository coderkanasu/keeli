"""
Lean Keeli templates — only what we actually use.
No hallucinations. Epic → Story → Task workflow.
Handshakes come later.
"""

from keeli.version import get_version

SCHEMA_VERSION = get_version()

# ============================================================================
# EPIC_TEMPLATE — High-level objective and scope
# ============================================================================
EPIC_TEMPLATE = """# Epic: {title}

**ID:** {task_id}
**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —

## Goal
{goal}

## Scope
<!-- In scope:
- Item 1
- Item 2

Out of scope:
- Item 3
- Item 4
-->

## Stories
<!-- Link stories here as they're created
- story-foo (user can create tasks)
- story-bar (user can mark tasks complete)
-->

## Done
- [ ] Goal defined
- [ ] Scope agreed
- [ ] All stories completed

## Notes
<!-- Strategic context, risks, dependencies. -->
"""

# ============================================================================
# STORY_TEMPLATE — User story with acceptance criteria
# ============================================================================
STORY_TEMPLATE = """# Story: {title}

**ID:** {task_id}
**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Epic:** {epic}

## User Story
{user_story}

## Acceptance Criteria
{acceptance_criteria}

## Non-Functional Requirements
{non_functional_requirements}

## Tasks
<!-- Link implementation tasks here as they're created
- task-foo (implement database schema)
- task-bar (write API endpoint)
-->

## Done
- [ ] User story clear
- [ ] Acceptance criteria testable
- [ ] NFRs identified (or explicitly none)
- [ ] All tasks completed

## Notes
<!-- Implementation hints, blockers, decisions. -->
"""

# ============================================================================
# TASK_TEMPLATE — Implementable unit of work
# ============================================================================
TASK_TEMPLATE = """# Task: {title}

**ID:** {task_id}
**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Epic:** {epic}
**Story:** {story}
**Depends On:** {depends_on}
**Context:** {context_note}
**Tags:** {tags}
**Requires Skills:** {requires_skills}
**Affects:** {affects}

## What
{what}

## Why
{why}

## Acceptance
{acceptance}

## Evidence
{evidence}

## Verification
{verification}

## Notes
<!-- Implementation hints, gotchas, decisions. -->
"""

# ============================================================================
# AI_LOG_MD — Audit log template
# ============================================================================
AI_LOG_MD = f"""# AI Audit Log  (Keeli Framework v{SCHEMA_VERSION})

<!-- Timestamped entries appended by the AI and by `keeli log`. -->
<!-- Format: YYYY-MM-DDTHH:MM:SSZ | <ID> | <message> -->
<!-- Example: 2026-03-11T03:25:17Z | E-0001 | Epic created: State Machine architecture -->

"""

# ============================================================================
# PROJECT_MD — Project context template
# ============================================================================
PROJECT_MD = f"""# Project Documentation  (Keeli Framework v{SCHEMA_VERSION})

## Overview
<!-- Purpose, users, high-level goals. -->

## Tech Stack
See [skills.md](skills.md) for registered technologies.

### Languages & Frameworks
<!-- Primary languages, frameworks, runtime versions. -->

### Infrastructure
<!-- Databases, hosting, deployment, monitoring. -->

## Architecture
<!-- High-level system design, key modules, data flow. -->

## Key Decisions
See [decision.md](decision.md) for ADRs and past decisions.

## Workflow
1. **Create Epic:** `keeli epic "<title>" -p P0/P1/P2`
2. **Create Stories:** `keeli story "<title>" --epic <slug>`
3. **Create Tasks:** `keeli start "<title>" --story <slug>`
4. **Mark In Progress:** `keeli progress "<title>"`
5. **Mark Complete:** `keeli complete "<title>"`

See `keeli --help` for all commands.
"""

# ============================================================================
# DECISION_MD — ADR template
# ============================================================================
DECISION_MD = f"""# Decision Log  (Keeli Framework v{SCHEMA_VERSION})

Format: Record significant decisions with rationale and alternatives.

---

## TEMPLATE

**Date:** YYYY-MM-DD  
**Decision:** What was decided  
**Context:** Why this decision was needed  
**Alternatives Considered:**
- Option A — rejected because ...
- Option B — rejected because ...

**Consequences:** What this means going forward.

---

<!-- Add decisions above this line -->
"""

# ============================================================================
# SKILLS_MD — Skills registry
# ============================================================================
SKILLS_MD = f"""# Keeli Skills Registry  (Keeli Framework v{SCHEMA_VERSION})

Managed by `keeli skill` and `keeli stack`. Track project-specific tech decisions.

| Type | Skill | Persona | Constraint |
|------|-------|---------|------------|
<!-- Example row: domain | Repository Pattern | @architect | Every external data source behind an interface -->
"""

# ============================================================================
# .gitignore
# ============================================================================
GITIGNORE_CONTENT = """# Keeli
*.pyc
__pycache__/
.env
venv/
env/
.venv/
.eggs/
*.egg-info/
build/
dist/
"""

# ============================================================================
# Copilot Instructions
# ============================================================================
COPILOT_INSTRUCTIONS = f"""# GitHub Copilot Custom Instructions (Keeli Framework v{SCHEMA_VERSION})

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
- Do not invoke Keeli CLI unless the user explicitly asks to run a CLI command.
```

See docs/project.md for full workflow.
"""

# ============================================================================
# BUG_TEMPLATE — Bug report template
# ============================================================================
BUG_TEMPLATE = """# Bug: {title}

**ID:** {task_id}
**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Epic:** {epic}
**Found During:** {found_during}

## Reproduction
{description}

## Actual Behavior
<!-- What actually happened. Include error messages, screenshots. -->

## Expected Behavior
<!-- What should have happened. -->

## Environment
<!-- OS, version, relevant config that might affect reproduction. -->

## Acceptance
<!-- How to verify the fix.
- [ ] Reproduction steps no longer trigger bug
- [ ] No regression in related flows
- [ ] Error handling improved
-->

## Notes
<!-- Workarounds, severity assessment, related issues. -->
"""

# ============================================================================
# FEATURE_TEMPLATE — Feature request template
# ============================================================================
FEATURE_TEMPLATE = """# Feature: {title}

**ID:** {task_id}
**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Epic:** {epic}
**Context:** {context_note}

## User Story
{user_story}

## Why
<!-- User/business value. -->

## Acceptance
<!-- How to verify the feature works.
- [ ] User can perform [action]
- [ ] Result is [expected outcome]
-->

## Notes
<!-- Design notes, dependencies, open questions. -->
"""

# ============================================================================
# TASK_CHECKLISTS — Persona-specific checklists (optional, not enforced yet)
# ============================================================================
TASK_CHECKLISTS = {
    "po": "",  # Placeholder — will define when persona gates are implemented
    "architect": "",
    "developer": "",
    "qa": "",
    "security": "",
    "author": "",
}

# ============================================================================
# STACK_PRESETS — Technology stacks (simplified for now)
# ============================================================================
STACK_PRESETS = {
    "python": [
        ("lang", "Python", "developer", "3.12+"),
    ],
    "node": [
        ("lang", "Node.js", "developer", "20+ LTS"),
    ],
    "java": [
        ("lang", "Java", "developer", "21+"),
    ],
}

STACK_PRESET_ALIASES = {
    "py": "python",
    "js": "node",
}

# ============================================================================
# get_flavor_instructions — Return flavoured instructions
# ============================================================================
def get_flavor_instructions(flavor: str = "copilot") -> str:
    """Return instruction flavour.
    Flavours: 'copilot', 'claude', 'cursor', 'codex'
    For now, return copilot instructions for all.
    """
    return COPILOT_INSTRUCTIONS
