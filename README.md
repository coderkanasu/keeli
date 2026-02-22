# Keeli

A command-line tool to enforce a strict **Four-Persona Architecture** for GitHub Copilot and other AI agents. Designed to help **stateless LLMs regain context fast** and make steady progress across sessions.

This ensures security governance, responsible AI use, and zero hallucination by forcing the AI to act as a team of four distinct personas: `@architect`, `@developer`, `@security`, and `@author`.

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# 1. Scaffold the framework in any project
keeli init

# 2. Create a task (team of personas kicks in)
keeli start "Implement Auth" --context docs/requirements/auth-spec.md -p P0

# 3. Transition task status as work progresses
keeli progress "Implement Auth"   # Backlog → In Progress
keeli block "Implement Auth"      # In Progress → Blocked
keeli complete "Implement Auth"   # → Completed (suggests next task)
keeli reopen "Implement Auth"     # Completed → In Progress (rework needed)

# 4. Found a bug while debugging? Log it as a tracked task
keeli bug "NullPointer in OrderService" -d "Happens when qty is null" --found-during "implement-auth"

# 5. Log an event for audit
keeli log "Unit tests passed for auth module"

# 6. New session? Catch up fast (token-aware!)
keeli resume            # default ~1500 tokens
keeli resume --brief    # minimal ~500 tokens
keeli resume --full     # everything ~3000 tokens

# 7. Upgrade instructions after a Keeli update
keeli update
```

## Commands

| Command | Description |
|---------|-------------|
| `keeli init [-f]` | Scaffold `.github/copilot-instructions.md`, `docs/` structure, `.gitignore` |
| `keeli start <name> [-c file] [-p P0\|P1\|P2] [-d deps] [-f]` | Create a task in `docs/tasks/<slug>.md` with TDD checklist. Use `-d` for dependencies. |
| `keeli bug <title> [-d desc] [-p P0\|P1\|P2] [--found-during task] [-f]` | Log a bug as a tracked task (`docs/tasks/bug-<slug>.md`) |
| `keeli feature <title> [-c file] [-p P0\|P1\|P2] [-f]` | Create a feature request (`docs/tasks/feat-<slug>.md`) with user story + acceptance criteria |
| `keeli progress <name>` | Mark a task as **In Progress** |
| `keeli block <name>` | Mark a task as **Blocked** |
| `keeli complete <name>` | Mark a task as **Completed** and suggest the next task |
| `keeli archive <name>` | Move a **Completed** task to `docs/tasks/archive/` to save context window space |
| `keeli reopen <name>` | Reopen a **Completed** task (back to In Progress) |
| `keeli next [-q] [--json]` | Show the next task to work on (by priority, then age). Use `--json` for agentic parsing. |
| `keeli list [-s status] [--json]` | List all tasks. Use `--json` for agentic parsing. |
| `keeli log <message>` | Append a timestamped entry to `docs/ai_log.md` |
| `keeli resume [--brief\|--full]` | Dump project context sized to your token budget |
| `keeli status` | Health-check all expected Keeli files |
| `keeli clear-log` | Reset `docs/ai_log.md` to its default state |
| `keeli update [-f]` | Update `copilot-instructions.md` to latest template (preserves user files) |
| `keeli --version` | Print the current Keeli Framework version |

## Task Lifecycle

Every task follows this state machine:

```
Backlog → In Progress → Review → Completed → Archived
                ↓                     ↓
             Blocked → (unblocked)   Reopened → In Progress
```

### Priority System

Tasks have a priority level: **P0** (critical), **P1** (default), **P2** (low).

When picking the next task:
1. Resume any **In Progress** task first.
2. Otherwise pick the highest-priority **Backlog** task (P0 > P1 > P2).
3. Break ties by age (oldest first).

### Bug Tracking

Use `keeli bug` to quickly log issues found during debugging:

```bash
keeli bug "Login crash on empty password" -p P0 --found-during "implement-auth"
```

Bug reports are saved as `docs/tasks/bug-<slug>.md` with their own template including reproduction steps, expected/actual behavior, and a regression test checklist. They participate in the same lifecycle and priority queue as regular tasks.

### Feature Requests

Use `keeli feature` to capture product ideas and requirements:

```bash
keeli feature "Dark Mode Support" -p P2
keeli feature "Payment Gateway" -p P0 -c docs/requirements/payment-spec.md
```

Feature files are saved as `docs/tasks/feat-<slug>.md` with a template covering User Story, Acceptance Criteria, Design Notes, and a full checklist (including @architect approval, TDD, @security review, and @author documentation). They participate in the same lifecycle and priority queue as tasks and bugs.

### Auto-Completion Rule

The AI is instructed to mark tasks as completed **itself** — it doesn't wait for you to run `keeli complete`. When the AI finishes work, it:
1. Sets `**Status:** Completed` and adds a timestamp.
2. Checks off all checklist boxes.
3. Logs the completion event.
4. Immediately picks up the next task.

## Agentic AI & Headless Usage

Keeli is designed to be the perfect "disk-based memory bank" for autonomous AI agents (like LangChain, AutoGPT, or custom scripts). Because Keeli maintains perfect state on disk, you can build a headless loop that runs completely autonomously:

1. **Task Dependencies**: Use `keeli start "Task B" --depends-on "task-a"`. The `keeli next` command will automatically skip "Task B" until "Task A" is marked as `Completed`.
2. **JSON Output**: Use `keeli next --json` and `keeli list --json` to programmatically parse the task queue in your Python/Node scripts without scraping ASCII tables.
3. **Archiving**: Use `keeli archive <task>` to move completed tasks to `docs/tasks/archive/`. This keeps the active directory clean and prevents the LLM's context window from blowing up as the project grows.

**Example Agent Loop (Python):**
```python
import json, subprocess

# 1. Get the next task programmatically
output = subprocess.run(["keeli", "next", "--json"], capture_output=True, text=True)
task_data = json.loads(output.stdout)

if task_data.get("task"):
    task_slug = task_data["task"]
    
    # 2. Mark task as In Progress
    subprocess.run(["keeli", "progress", task_slug])
    
    # 3. Read project context
    context = subprocess.run(["keeli", "resume", "--brief"], capture_output=True, text=True)
    
    # 4. Pass context and task to your LLM (LangChain, OpenAI API, etc.)
    # ... LLM writes code and tests ...
    
    # 5. Mark task as completed and archive it
    subprocess.run(["keeli", "complete", task_slug])
    subprocess.run(["keeli", "archive", task_slug])
```

## What `keeli init` Creates

```
.github/
  copilot-instructions.md   # Four-Persona rules + Session Start Protocol
docs/
  project.md                # Project context, tech stack, skills, architecture
  decision.md               # Decision log with rationale + rejected alternatives
  ai_log.md                 # Timestamped audit log with session markers
  tasks/                    # Per-task files with TDD checklists
    .gitkeep
  requirements/             # Requirements & specs linked via --context
    .gitkeep
.gitignore                  # Ignores ai_log.md + Python build artifacts
```

## The Four Personas

1. **`@architect`**: Dissects tasks, creates strategy, records decisions in `docs/decision.md`, and breaks work into `docs/tasks/`.
2. **`@developer`**: Executes tasks with TDD, asks clarifying questions, and engages the human-in-the-loop if scope is large or ambiguous.
3. **`@security`**: Reviews all architecture and code for vulnerabilities, compliance, PII leaks, and responsible AI practices.
4. **`@author`**: Writes clear, SEO-friendly documentation, README files, blog posts, and web copy. Ensures accessibility (WCAG) and proper API/component docs.

## Bundled Skills

The generated `docs/project.md` comes pre-populated with your tech stack:

- **Languages & Frameworks**: Java, Spring Framework (Boot, Security, Data JPA), Python, JavaScript/TypeScript, React, React Native, AngularJS, CSS/SCSS
- **Domain Expertise**: Trading systems, financial data pipelines

## Scope Guardrails

The AI must pause and ask for confirmation when:
- The change touches **more than 5 files**.
- The change involves **authentication, authorisation, or data deletion**.
- The change **removes or renames a public API**.
- There is **ambiguity** that could lead to two valid implementations.
- The estimated effort exceeds **30 minutes of coding**.

## Context-Window Awareness

Since LLMs are stateless with limited context windows, the framework is designed to **expand or shrink** based on available tokens:

- **`keeli resume --brief`** (~500 tokens): Project overview + active task names only.
- **`keeli resume`** (~1500 tokens): Above + recent log entries + decision summary.
- **`keeli resume --full`** (~3000 tokens): Everything including full decision log.

Each invocation prints an approximate token estimate so you can verify the output fits your context window.

The `copilot-instructions.md` also tells the AI to **summarise instead of quoting** when context is constrained, and to **skip non-essential reads** when the window is very small (<8k tokens remaining).

## Session Start Protocol

Every new AI session is instructed to:
1. Read `docs/project.md`
2. Scan `docs/tasks/` for active/blocked tasks
3. Read the last 30 lines of `docs/ai_log.md`
4. Read `docs/decision.md` to avoid re-litigating settled decisions
5. Only then proceed with the user's request

## Schema Versioning

The framework embeds a version number (`v0.3.0`) in all generated files. When you upgrade the CLI, run:

```bash
keeli update
```

This regenerates `copilot-instructions.md` with the latest template while preserving your `project.md`, `decision.md`, tasks, and logs.

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```