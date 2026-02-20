# Persona CLI

A command-line tool to enforce a strict **Three-Persona Architecture** for GitHub Copilot and other AI agents. Designed to help **stateless LLMs regain context fast** and make steady progress across sessions.

This ensures security governance, responsible AI use, and zero hallucination by forcing the AI to act as a team of three distinct personas: `@architect`, `@developer`, and `@security`.

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# 1. Scaffold the framework in any project
persona init

# 2. Create a task (team of personas kicks in)
persona start "Implement Auth" --context docs/requirements/auth-spec.md -p P0

# 3. Transition task status as work progresses
persona progress "Implement Auth"   # Backlog → In Progress
persona block "Implement Auth"      # In Progress → Blocked
persona complete "Implement Auth"   # → Completed (suggests next task)

# 4. Log an event for audit
persona log "Unit tests passed for auth module"

# 5. New session? Catch up fast (token-aware!)
persona resume            # default ~1500 tokens
persona resume --brief    # minimal ~500 tokens
persona resume --full     # everything ~3000 tokens

# 6. Upgrade instructions after a Persona CLI update
persona update
```

## Commands

| Command | Description |
|---------|-------------|
| `persona init [-f]` | Scaffold `.github/copilot-instructions.md`, `docs/` structure, `.gitignore` |
| `persona start <name> [-c file] [-p P0\|P1\|P2] [-f]` | Create a task in `docs/tasks/<slug>.md` with TDD checklist |
| `persona progress <name>` | Mark a task as **In Progress** |
| `persona block <name>` | Mark a task as **Blocked** |
| `persona complete <name>` | Mark a task as **Completed** and suggest the next task |
| `persona next [-q]` | Show the next task to work on (by priority, then age) |
| `persona log <message>` | Append a timestamped entry to `docs/ai_log.md` |
| `persona resume [--brief\|--full]` | Dump project context sized to your token budget |
| `persona status` | Health-check all expected Persona files |
| `persona clear-log` | Reset `docs/ai_log.md` to its default state |
| `persona update [-f]` | Update `copilot-instructions.md` to latest template (preserves user files) |
| `persona --version` | Print the current Persona Framework version |

## Task Lifecycle

Every task follows this state machine:

```
Backlog → In Progress → Review → Completed
                ↓
             Blocked → (unblocked) → In Progress
```

### Priority System

Tasks have a priority level: **P0** (critical), **P1** (default), **P2** (low).

When picking the next task:
1. Resume any **In Progress** task first.
2. Otherwise pick the highest-priority **Backlog** task (P0 > P1 > P2).
3. Break ties by age (oldest first).

### Auto-Completion Rule

The AI is instructed to mark tasks as completed **itself** — it doesn't wait for you to run `persona complete`. When the AI finishes work, it:
1. Sets `**Status:** Completed` and adds a timestamp.
2. Checks off all checklist boxes.
3. Logs the completion event.
4. Immediately picks up the next task.

## What `persona init` Creates

```
.github/
  copilot-instructions.md   # Three-Persona rules + Session Start Protocol
docs/
  project.md                # Project context, tech stack, architecture
  decision.md               # Decision log with rationale + rejected alternatives
  ai_log.md                 # Timestamped audit log with session markers
  tasks/                    # Per-task files with TDD checklists
    .gitkeep
  requirements/             # Requirements & specs linked via --context
    .gitkeep
.gitignore                  # Ignores ai_log.md + Python build artifacts
```

## The Three Personas

1. **`@architect`**: Dissects tasks, creates strategy, records decisions in `docs/decision.md`, and breaks work into `docs/tasks/`.
2. **`@developer`**: Executes tasks with TDD, asks clarifying questions, and engages the human-in-the-loop if scope is large or ambiguous.
3. **`@security`**: Reviews all architecture and code for vulnerabilities, compliance, PII leaks, and responsible AI practices.

## Scope Guardrails

The AI must pause and ask for confirmation when:
- The change touches **more than 5 files**.
- The change involves **authentication, authorisation, or data deletion**.
- The change **removes or renames a public API**.
- There is **ambiguity** that could lead to two valid implementations.
- The estimated effort exceeds **30 minutes of coding**.

## Context-Window Awareness

Since LLMs are stateless with limited context windows, the framework is designed to **expand or shrink** based on available tokens:

- **`persona resume --brief`** (~500 tokens): Project overview + active task names only.
- **`persona resume`** (~1500 tokens): Above + recent log entries + decision summary.
- **`persona resume --full`** (~3000 tokens): Everything including full decision log.

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

The framework embeds a version number (`v0.2.0`) in all generated files. When you upgrade the CLI, run:

```bash
persona update
```

This regenerates `copilot-instructions.md` with the latest template while preserving your `project.md`, `decision.md`, tasks, and logs.

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```