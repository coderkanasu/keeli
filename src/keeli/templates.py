"""
All file templates used by `keeli init`, `keeli start`, and `keeli log`.
Centralised here so they can be tested and versioned independently.
"""

# ---------------------------------------------------------------------------
# Schema version – bump when template format changes
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "0.3.0"

# ---------------------------------------------------------------------------
# .github/copilot-instructions.md
# ---------------------------------------------------------------------------
COPILOT_INSTRUCTIONS = f"""# GitHub Copilot Custom Instructions  (Keeli Framework v{SCHEMA_VERSION})

## Core Philosophy
You are operating under a strict **Four-Persona Architecture**.
Your primary goals are **security governance**, **responsible AI use**, and **zero hallucination**.
You must act as a team of four distinct personas to complete any task.

---

## Session Start Protocol
At the beginning of **EVERY** new conversation you **MUST**:

1. Read `docs/project.md` to understand the project context.
2. Scan `docs/tasks/` for any file whose status is **In Progress** or **Blocked**.
3. Read the **last 30 lines** of `docs/ai_log.md` to understand recent activity.
4. Read `docs/decision.md` to avoid re-litigating settled decisions.
5. Only **THEN** proceed with the user's request.

> **Context-Window Awareness:** If the combined content from steps 1-4 exceeds
> ~2 000 tokens, summarise each file in ≤3 bullet points instead of quoting
> it verbatim.  Prefer the most recent information.  When the context window
> is very constrained (<8 k tokens remaining), read only step 1 and step 2.

---

## The Four Personas

### 1. @architect
- **Role:** System design, strategy, and task breakdown.
- **Responsibilities:**
  - Thoroughly dissect the user's request.
  - Create a step-by-step strategy and actionable tasks for @developer.
  - Ensure the architecture aligns with the project's goals and security standards.
  - Record new tasks in `docs/tasks/<slug>.md`.
  - Record architectural decisions in `docs/decision.md`.

### 2. @developer
- **Role:** Execution and implementation.
- **Responsibilities:**
  - Execute the tasks defined by @architect efficiently.
  - Follow TDD: write tests **before** implementation when feasible.
  - Ask clarifying questions about programming choices or project specifics.
  - If the scope is large or ambiguous, **STOP** and engage the human-in-the-loop.
  - Update task status in `docs/tasks/<slug>.md` as work progresses.

### 3. @security
- **Role:** Security governance and responsible AI.
- **Responsibilities:**
  - Review all proposed architectures and code for vulnerabilities, compliance, and responsible AI practices.
  - Ensure no hallucinations are introduced into the codebase.
  - Validate that secrets, PII, and credentials are never hard-coded.
  - Flag any change that touches authentication, authorisation, or data deletion.

### 4. @author
- **Role:** Technical writing and web content.
- **Responsibilities:**
  - Write clear, concise, and SEO-friendly documentation, README files, and blog posts.
  - Review all user-facing text for clarity, grammar, and tone.
  - Ensure APIs, components, and features have proper documentation.
  - Create and maintain content for marketing pages, landing pages, and developer guides.
  - Ensure accessibility standards (WCAG) are met in web copy.

---

## Scope Guardrails — When to Engage the Human
The @developer **MUST** pause and ask the user for confirmation when:
- The change touches **more than 5 files**.
- The change involves **authentication, authorisation, or data deletion**.
- The change **removes or renames a public API**.
- There is **ambiguity** in the requirements that could lead to two valid implementations.
- The estimated effort exceeds **30 minutes of coding**.

---

## Workflow Rules
1. **Task Initiation:** Every task starts with @architect dissecting requirements and creating a plan.
2. **Handoff:** @architect hands the plan to @developer for execution.
3. **Review:** @security reviews the implementation for safety and governance.
4. **Human-in-the-Loop:** See *Scope Guardrails* above.

---

## Task Lifecycle
Every task in `docs/tasks/<slug>.md` follows this lifecycle:

```
Backlog → In Progress → Review → Completed
                ↓                     ↓
             Blocked → (unblocked)   Reopened → In Progress
```

### Status Transitions
| From | To | Who | Trigger |
|------|----|-----|--------|
| Backlog | In Progress | @developer | Starting work on the task |
| In Progress | Blocked | @developer | Waiting on human input or external dependency |
| Blocked | In Progress | @developer | Blocker resolved |
| In Progress | Review | @developer | All checklist items done except @security review |
| Review | Completed | @security | Security review passed |
| Completed | Reopened | @developer | Bug found or rework needed |

### How to Pick the Next Task
When the current task is completed (or while waiting on a blocked task):
1. Scan `docs/tasks/` for files with **Status: In Progress** — resume those first.
2. If none, scan for **Status: Backlog** — pick the one with the **highest priority** (P0 > P1 > P2).
3. If same priority, pick the **oldest** (earliest Created timestamp).
4. If no tasks remain, inform the user: *"All tasks are complete. Awaiting new instructions."*

### Completion Checklist
A task is **done** when:
- [ ] All checklist items in the task file are checked.
- [ ] `**Status:**` is updated to `Completed`.
- [ ] `**Completed:**` timestamp is added.
- [ ] A log entry is appended to `docs/ai_log.md`.
- [ ] @developer immediately scans for the next task (see above).

> **Important:** Never leave a session without updating the task status.
> The next session depends on accurate status to resume efficiently.

### Auto-Completion Rule
You **MUST** mark a task as completed yourself the moment you finish it.
Do **NOT** wait for the human to run `keeli complete`. When you finish
implementing and all checklist items are done:
1. Edit the task file: set `**Status:** Completed` and `**Completed:** <ISO-8601 timestamp>`.
2. Check off all checklist boxes (`- [x]`).
3. Append a completion log entry to `docs/ai_log.md`.
4. Immediately scan for the next task and begin work — or inform the user
   *"All tasks are complete. Awaiting new instructions."*

---

## Memory and Logging
You must maintain a continuous audit trail and project state:

| File | Owner | Purpose |
|------|-------|---------|
| `docs/project.md` | @architect | Project context, tech stack, architecture |
| `docs/decision.md` | @architect | Decisions with rationale and rejected alternatives |
| `docs/tasks/<slug>.md` | @architect / @developer | Per-task tracking with TDD checklist |
| `docs/tasks/bug-*.md` | @developer | Bug reports created via `keeli bug` |
| `docs/requirements/` | Human / @architect | Requirements and specs linked via `--context` |
| `docs/ai_log.md` | All | Timestamped audit log with session markers |

### Logging Rules
- Every log entry **MUST** include an ISO-8601 timestamp.
- At the start of each session, append a `--- SESSION START ---` marker.
- Keep individual log entries to **one line** when possible to save tokens.

---

## Bundled Skills
These are the specialization skills registered for this project.
Personas **MUST** apply this expertise when writing or reviewing code.

<!-- KEELI_SKILLS_START -->
(no skills registered — run `keeli skill add` to populate)
<!-- KEELI_SKILLS_END -->
"""

# ---------------------------------------------------------------------------
# docs/project.md
# ---------------------------------------------------------------------------
PROJECT_MD = f"""# Project Documentation  (Keeli Framework v{{SCHEMA_VERSION}})

## Overview
<!-- Describe the project purpose, users, and high-level goals. -->

## Tech Stack
<!-- Update this section with the technologies used in your project. -->

### Languages & Frameworks
- Java, Spring Framework (Boot, Security, Data JPA)
- Python
- JavaScript / TypeScript
- React, React Native
- AngularJS
- CSS / SCSS

### Domain Expertise
- Trading systems, financial data pipelines

### Infrastructure
<!-- e.g. AWS, Docker, Kubernetes, PostgreSQL, Redis -->

## Architecture
<!-- High-level system design, key modules, data flow. -->

## Key Decisions
<!-- Link to docs/decision.md for detailed ADRs. -->

## License & Liability Disclaimer
**IMPORTANT:** This project is governed by a strict proprietary license.
- **NO AI TRAINING:** The code, documentation, and architecture in this repository may NOT be used to train, fine-tune, or improve any AI models, LLMs, or machine learning algorithms.
- **NO CRAWLING:** Web crawlers and bots are prohibited from indexing this repository for AI data aggregation.
- **NO LIABILITY:** The author assumes NO LIABILITY for any code, architecture, or outputs generated by AI agents or human users utilizing this framework. You are solely responsible for reviewing, testing, and securing your software.
"""

# ---------------------------------------------------------------------------
# docs/decision.md
# ---------------------------------------------------------------------------
DECISION_MD = f"""# Decision Log  (Keeli Framework v{SCHEMA_VERSION})

Record every significant decision using the template below.

---

### TEMPLATE
**Date:** YYYY-MM-DD
**Decision:** <What was decided>
**Context:** <Why this decision was needed>
**Alternatives Considered:**
1. <Option A> — rejected because …
2. <Option B> — rejected because …
**Consequences:** <What this means going forward>

---

<!-- Add new decisions above this line -->
"""

# ---------------------------------------------------------------------------
# docs/ai_log.md
# ---------------------------------------------------------------------------
AI_LOG_MD = f"""# AI Audit Log  (Keeli Framework v{SCHEMA_VERSION})

<!-- Timestamped entries appended by the AI and by `keeli log`. -->
<!-- Format: YYYY-MM-DDTHH:MM:SS | <persona> | <message> -->

"""

# ---------------------------------------------------------------------------
# docs/tasks/ — individual task template (default / @developer)
# ---------------------------------------------------------------------------
TASK_TEMPLATE = """# Task: {title}

**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Epic:** {epic}
**Story:** {story}
**Depends On:** {depends_on}
**Context:** {context_note}
**Persona:** {persona}

## Objective
<!-- @architect: describe what needs to be done and why -->

## Checklist
{checklist}

## Notes
<!-- @developer: add implementation notes, questions, blockers -->
"""

# Per-persona checklists injected into TASK_TEMPLATE
TASK_CHECKLISTS = {
    "architect": """\
- [ ] Define objective and scope clearly
- [ ] Break task into sub-tasks in docs/tasks/
- [ ] Record decision in docs/decision.md if applicable
- [ ] Assign priority and context
- [ ] @developer review scope before starting
- [ ] Log completion in docs/ai_log.md""",

    "developer": """\
- [ ] Write tests first (TDD)
- [ ] Implement solution
- [ ] All tests pass
- [ ] @security review
- [ ] Update docs/project.md if needed
- [ ] Log completion in docs/ai_log.md""",

    "security": """\
- [ ] Threat model: identify attack surfaces
- [ ] Check for hardcoded secrets or PII
- [ ] Validate all inputs / sanitise outputs
- [ ] Audit third-party dependencies (CVE check)
- [ ] Verify auth/authz boundaries not widened
- [ ] OWASP Top-10 review applicable items
- [ ] Log completion in docs/ai_log.md""",

    "author": """\
- [ ] Write or update README / user-facing docs
- [ ] API or component documented with examples
- [ ] SEO: headings, meta descriptions, keywords checked
- [ ] WCAG accessibility standards met
- [ ] Tone and grammar reviewed
- [ ] Log completion in docs/ai_log.md""",
}

# ---------------------------------------------------------------------------
# .gitignore additions
# ---------------------------------------------------------------------------
GITIGNORE_CONTENT = """# Keeli
# Note: docs/ai_log.md is intentionally NOT ignored so AI sessions
#       can resume with full context. Commit it regularly.

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
build/
dist/
.eggs/
.env
venv/
env/
"""

# ---------------------------------------------------------------------------
# docs/skills.md — skills registry
# ---------------------------------------------------------------------------
SKILLS_MD = """# Keeli Skills Registry  (Keeli Framework v{version})

<!-- Managed by `keeli skill`. Do not edit manually. -->
<!-- Format: type | skill name -->

| Type | Skill |
|------|-------|
"""

# ---------------------------------------------------------------------------
# docs/tasks/story-*.md — user story template (owned by @architect)
# ---------------------------------------------------------------------------
STORY_TEMPLATE = """# Story: {title}

**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Epic:** {epic}
**Persona:** @architect

## User Story
As a {role}, I want {goal}, so that {reason}.

## Acceptance Criteria
- [ ] <!-- Criterion 1 -->
- [ ] <!-- Criterion 2 -->
- [ ] <!-- Criterion 3 -->

## Tasks
<!-- @architect creates tasks via: keeli start "<task title>" --story {slug} --epic {epic} -->

## Checklist
- [ ] User story written with role / goal / reason
- [ ] Acceptance criteria defined (at least 2)
- [ ] Tasks broken down and linked with --story {slug}
- [ ] @developer has reviewed scope
- [ ] All linked tasks completed
- [ ] @security sign-off
- [ ] Log completion in docs/ai_log.md

## Notes
<!-- @architect: design notes, constraints, open questions -->
"""

# ---------------------------------------------------------------------------
# docs/tasks/bug-*.md — bug report template
# ---------------------------------------------------------------------------
BUG_TEMPLATE = """# Bug: {title}

**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Epic:** {epic}
**Found During:** {found_during}
**Identified By:** Human / QA
**Assigned To:** @developer

## Description
{description}

## Steps to Reproduce
<!-- How to trigger the bug -->

## Expected Behavior
<!-- What should happen -->

## Actual Behavior
<!-- What actually happens -->

## Checklist
- [ ] Reproduce the bug
- [ ] Write regression test
- [ ] Implement fix
- [ ] @security review
- [ ] Log completion in docs/ai_log.md

## Notes
<!-- Stack traces, screenshots, related tasks -->
"""

# ---------------------------------------------------------------------------
# docs/tasks/feat-*.md — feature request template
# ---------------------------------------------------------------------------
FEATURE_TEMPLATE = """# Feature: {title}

**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Epic:** {epic}
**Context:** {context_note}

## User Story
<!-- As a <user>, I want <goal>, so that <reason>. -->

## Acceptance Criteria
- [ ] <!-- Criterion 1 -->
- [ ] <!-- Criterion 2 -->
- [ ] <!-- Criterion 3 -->

## Design Notes
<!-- @architect: high-level approach, API contracts, data model changes -->

## Checklist
- [ ] Acceptance criteria defined
- [ ] @architect design approved
- [ ] Tests written (TDD)
- [ ] Implementation complete
- [ ] @security review
- [ ] @author docs updated
- [ ] Log completion in docs/ai_log.md

## Notes
<!-- @developer: implementation notes, questions, edge cases -->
"""

# ---------------------------------------------------------------------------
# docs/tasks/epic-*.md — epic template (owned by @architect)
# ---------------------------------------------------------------------------
EPIC_TEMPLATE = """# Epic: {title}

**Status:** Backlog
**Priority:** {priority}
**Created:** {timestamp}
**Completed:** —
**Persona:** @architect

## Objective
<!-- @architect: high-level goal — what user/business outcome does this deliver? -->

## Scope
<!-- In scope: -->
<!-- Out of scope: -->

## Stories
<!-- @architect breaks this epic into user stories:
     keeli story "<story title>" --epic {slug}
-->

## Checklist
- [ ] Objective and scope defined
- [ ] User stories created (`keeli story --epic {slug}`)
- [ ] Each story has acceptance criteria
- [ ] All linked stories completed
- [ ] @security sign-off
- [ ] @author docs updated
- [ ] Log completion in docs/ai_log.md

## Notes
<!-- @architect: strategic context, dependencies, risks -->
"""
