# Keeli

Keeli is an AI-native state machine for managing complex software projects with six-persona governance. Work naturally in your IDE and Git; Keeli enforces quality gates invisibly.

## Core Vision: Invisible State Management

Code freely. Keeli guards silently.

**What happens:**
1. Developer codes and commits → Git pre-commit hook validates task state
2. Architect designs → Keeli auto-detects persona change, logs decision
3. QA tests → background evidence capture, gate enforcement
4. All state lives in encrypted SQLite (`keeli_state.db`) — single source of truth
5. External platforms (Jira, Trello, Monday) sync in background

**What you don't do:**
- ❌ No manual `keeli handoff` commands
- ❌ No handoff tables to edit
- ❌ No persona sign-off checklists to check
- ❌ No GitHub issues or Markdown task files as state

**Guardrails you hit if out of order:**
- Task state missing? → Keeli creates stub task
- @architect approval needed? → Pre-commit blocks with "Needs design review first"
- PII in code? → Keeli redacts before logging
- Epic incomplete? → Keeli suggests "Run `keeli story` to break it down"

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# 1) Initialize framework — creates keeli_state.db + agent instructions
keeli init --force

# 2) Create planning artifacts (epics, stories still manual for now)
keeli epic "Build encrypted state machine" -p P0

# 3) Code naturally
git add -A
git commit -m "Implement SQLite schema"
# ← Git hook runs: keeli validate-task-state
# ← Keeli logs: "T-0001 moved In Progress → Review (auto-detected)"

# 4) Keeli tracks state automatically
keeli status        # Show current task state from keeli_state.db
keeli next          # What should I work on next?
keeli resume --brief # Full context snapshot
```

## Core Model

**State Machine (no manual transitions):**
```
Backlog → In Progress (auto-detected via git)
	→ Review (auto-detected when tests pass)
	→ Completed (auto-detected when merged to main)
	→ Archived (auto-cleanup after 7 days)
```

**Personas (6-persona governance):**
- @po — requirements, acceptance criteria
- @architect — design decisions, interfaces
- @developer — implementation, TDD
- @qa — test evidence, regression coverage
- @security — threat model, auth, secrets
- @author — user-facing docs, examples

**State Storage:**
- `keeli_state.db` — encrypted SQLite (AES-256-GCM)
- `docs/decision.md` — ADR log (Git-tracked)
- `docs/ai_log.md` — audit trail (Git-tracked)
- `.github/copilot-instructions.md` — agent rules (Git-tracked)

## High-Value Commands

```bash
keeli list          # All tasks with state
keeli next          # Next task to work on
keeli status        # Current task + state
keeli log "msg"     # Manual audit entry
keeli skill add <name> -t lang/framework/domain/infra
```

## Repository Layout

- `src/keeli/` — CLI, state machine, hooks
- `docs/` — decision log, persona definitions, project context
- `.github/copilot-instructions.md` — agent rules
- `tests/` — test suite
- `keeli_state.db` — task state machine (encrypted, not in Git)

## Notes

- State lives in SQLite, not Git — sync happens via hooks
- Handoffs are automatic, logged invisibly
- Each feature iteration: delete `.github docs/`, reinit, test til perfect
- AI learning log maintained separately for recursive improvement
