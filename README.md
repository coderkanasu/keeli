# Keeli

Keeli is a Python CLI that scaffolds and enforces a persona-driven software delivery workflow for AI-assisted teams.

## What You Get After `keeli init`

- Project governance docs in `docs/`
- Agent instructions in `.github/copilot-instructions.md`
- Task tracking with lifecycle states and persona handoffs
- Audit logging in `docs/ai_log.md`

## Core Model

Keeli uses a structured lifecycle:

Backlog -> In Progress -> Review -> Completed

Personas collaborate through explicit handoff sign-offs in task files.

Default personas:

- @po
- @architect
- @developer
- @qa
- @security
- @author

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# 1) Initialize framework files
keeli init --force

# 2) Create planning artifacts
keeli epic "First Product Goal" -p P1 -o "Define business outcome"
keeli story "User can do X" --epic first-product-goal --role user --goal "do X" --reason "get value" -p P1

# 3) Create an implementation task
keeli start "Implement X" --epic first-product-goal --story user-can-do-x -k developer -p P1 -o "Ship feature with tests"

# 4) Move task through lifecycle with handoffs
keeli handoff implement-x -p po -m "Scope approved"
keeli handoff implement-x -p architect -m "Design approved"
keeli progress implement-x
keeli tick implement-x
keeli review implement-x
keeli handoff implement-x -p developer -m "Implementation complete"
keeli handoff implement-x -p qa -m "Quality checks passed"
keeli handoff implement-x -p security -m "Security checks passed"
keeli handoff implement-x -p author -m "Docs reviewed"
keeli complete implement-x
```

## High-Value Commands

```bash
keeli next
keeli list
keeli note <task> "message"
keeli log "session update"
keeli resume --brief
keeli analyze <task-slug>
keeli persona list
keeli skill list
```

## Add A Custom Persona

```bash
keeli persona add <slug>
keeli persona list
```

## Repository Layout

- `src/keeli/`: CLI implementation and templates
- `docs/`: generated governance state and task artifacts
- `.github/copilot-instructions.md`: generated Copilot instructions
- `tests/`: test suite

## Notes

- `keeli complete` auto-archives completed task files.
- `keeli tick` only checks mechanical checklist items; persona gate sign-offs still require explicit handoff.
