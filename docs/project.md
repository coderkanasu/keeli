# Project Documentation  (Keeli Framework v0.4.0)

## Overview
Keeli is a Python CLI tool that enforces a **Five-Persona Architecture** ([@po, @architect,
@developer, @security, @author]) for AI-assisted software development. It provides a
structured governance layer — task tracking, skill/stack registry, decision logs, and
context injection — so that LLM agents operate within a disciplined project workflow
rather than hallucinating unconstrained solutions.

**Primary users:** Developers and teams using GitHub Copilot or other LLM assistants
who want reproducible, auditable, persona-driven AI workflows.

## Goals
- Enforce task lifecycle: Backlog → In Progress → Review → Completed
- Record architectural decisions (ADRs) and prevent re-litigation
- Maintain a skills/stack registry with project-specific constraints (not generic labels)
- Auto-inject relevant context (skills, ADRs) into tasks via TF-IDF analysis
- Expose all commands via a Model Context Protocol (MCP) server for agentic AI use
- Stay framework-agnostic: no mandatory runtime dependencies beyond stdlib

## Tech Stack
- Python 3.12+
- MCP SDK — stdio + SSE transports for agentic AI integration
- FastAPI / Starlette + Uvicorn — SSE server mode
- scikit-learn (optional) — richer TF-IDF for `keeli analyze`; falls back to pure Python
- pytest — TDD test harness (64 tests)
- `argparse` — CLI parser (zero framework overhead)

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   keeli CLI                         │
│  main.py  (all commands, TF-IDF engine, dispatch)   │
│  templates.py  (COPILOT_INSTRUCTIONS, SKILLS_MD …)  │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│              MCP Server  (mcp_server.py)             │
│  keeli_next  keeli_start  keeli_complete             │
│  keeli_log   keeli_analyze                           │
│  Resources: project.md, decision.md, tasks/*        │
└─────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│         docs/  (all persistent state)               │
│  project.md   decision.md   ai_log.md               │
│  skills.md    personas.md   tasks/<slug>.md         │
└─────────────────────────────────────────────────────┘
```

## Key Commands

| Command | Description |
|---------|-------------|
| `keeli init` | Scaffold all docs/ files and `.github/copilot-instructions.md` |
| `keeli update` | Upgrade an existing project to the latest template version |
| `keeli start <title>` | Create a new task file |
| `keeli next` | Show highest-priority task + inline AI context hints |
| `keeli complete <slug>` | Mark task done; auto-show next |
| `keeli analyze <slug>` | Score task vs. corpus; inject `## AI Context Hints` block |
| `keeli stack apply <preset>` | Apply opinionated skill constraints from a preset |
| `keeli skill add/list/show` | Manage individual skills with persona + constraint |
| `keeli epic / story` | Group tasks into epics and user stories |
| `keeli mcp [--sse --port N]` | Start MCP server (stdio or SSE) |

## Key Decisions
See [docs/decision.md](decision.md) for all ADRs.
