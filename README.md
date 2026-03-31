# Keeli

Keeli is a Python CLI for teams building software with AI and needing repeatable delivery, auditable decisions, and clean handoffs between personas.

It combines docs-first planning with automation-safe state so humans and agents can work in the same system without losing traceability.

## The Problem Keeli Solves

AI-assisted delivery often breaks down in predictable ways:

- Requirements live in one place, implementation in another, and decisions disappear in chat history.
- Tasks move fast but evidence (tests, security checks, rationale) is hard to prove later.
- Agents and scripts need structured state, but teams still need human-readable docs.

Keeli solves this by giving you both:

- Human-readable markdown artifacts in `docs/`.
- Machine-readable operational state in `keeli_state.db`.
- Consistent lifecycle commands and JSON outputs for automation.
- Audit-friendly event capture through hooks and commit transitions.

## Typical Use Cases

Use Keeli when you want one or more of the following:

- A lightweight SDLC system for epics, stories, and tasks with clear transitions.
- Persona-driven delivery where PO, architecture, security, QA, and implementation each leave evidence.
- CLI-first automation for hooks, scripts, CI jobs, and MCP-based agent workflows.
- Docs-first planning where teams edit markdown directly but still keep structured state in sync.
- Governed AI delivery where you need to answer, "What changed, why, and was it validated?"

## Why Teams Pick Keeli

- Hybrid model: docs stay readable, automation stays deterministic.
- Fast workflow: short CLI commands for creation, transitions, and status.
- Safer automation: shared JSON envelopes for machine consumers.
- Extensible: MCP server tools and prompt templates for custom workflows.

## How To Contribute In 5 Minutes

```bash
# 1) Fork this repo on GitHub, then clone your fork
git clone https://github.com/<your-username>/persona-cli.git
cd persona-cli

# 2) Create a feature branch
git checkout -b feat/my-change

# 3) Install locally
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 4) Run tests
pytest -q

# 5) Commit and push
git add .
git commit -m "feat: describe your change"
git push -u origin feat/my-change
```

Open a Pull Request from your branch to this repository and include:

- What changed and why.
- Test evidence (or why tests were not needed).
- Any docs updates needed for users or contributors.

## Core Model

Keeli uses a hybrid source of truth:

- Markdown files in `docs/tasks/` are the human-facing artifacts.
- `keeli_state.db` is the structured state used for fast queries, audits, and automation.

Standard lifecycle:

```text
Backlog -> In Progress -> Review -> Completed -> Archived
```

Additional states include `Blocked` and reopened work returning to `In Progress`.

Built-in personas:

- `@po` for requirements and acceptance criteria.
- `@architect` for design, interfaces, and decisions.
- `@developer` for implementation.
- `@qa` for test evidence and regression safety.
- `@security` for threat modeling and auth/secrets concerns.
- `@author` for user-facing documentation.

## Quick Start

```bash
# 1) Install locally
pip install -e .

# 2) Initialize (creates docs, templates, and SQLite state)
keeli init --force

# 3) Create planning artifacts
keeli epic "Pipeline compliance gates" -p P0 -o "Introduce deterministic delivery gates"
keeli story "Persona gate engine" --epic pipeline-compliance-gates --role platform-engineer --goal "enforce ordered gates" --reason "prevent unsafe transitions" --ac "Transitions require prior evidence" -p P0

# 4) Create implementation work
keeli start "Build pipeline runner" --epic pipeline-compliance-gates --story persona-gate-engine -k developer -p P0 -o "Implement the first pipeline pass"

# 5) Move through lifecycle
keeli progress build-pipeline-runner
keeli review build-pipeline-runner
keeli complete build-pipeline-runner
```

Use command-driven mode when you want strict transitions and automation. Use docs-first mode when you want lightweight manual control.

## Docs-First Workflow

For planning and architecture-heavy work, you can operate directly in `docs/`:

1. Update scope in `docs/project.md` and `docs/requirements/*.md`.
2. Record key decisions in `docs/decision.md`.
3. Log execution notes in `docs/ai_log.md`.
4. Keep task details in `docs/tasks/*.md`.

No lifecycle command is required for every documentation change.

## Daily Commands

```bash
keeli list
keeli next
keeli status
keeli history T-0001
keeli digest --budget 1200
keeli log "Captured follow-up architecture notes"
```

## Automation Commands

Most useful for hooks, scripts, and agents:

```bash
keeli validate-task-state
keeli validate-task-state --auto-stub

keeli capture-commit-state --json

keeli transition-from-commit --subject "feat: closes T-0001" --json
keeli transition-from-commit --subject "keeli:complete" --target-id T-0001 --apply

keeli sync --dry-run --json
keeli sync --json

keeli test -q
keeli test --dry-run --json -q
```

Automation-facing commands use a shared JSON envelope:

```json
{
  "ok": true,
  "command": "sync",
  "timestamp": "2026-03-12T03:39:31Z",
  "data": {}
}
```

## What Is Implemented

- Project initialization with generated docs, Copilot instructions, and SQLite state.
- Work item management for epics, stories, tasks, bugs, and features.
- Lifecycle commands for backlog, in-progress, blocked, review, reopen, complete, and archive flows.
- Passive validation and automation hooks via `validate-task-state` and `capture-commit-state`.
- Commit-intent evaluation with `transition-from-commit`.
- SQLite rebuild and dry-run support with `sync`.
- Test-run integration with `keeli test`.
- Machine-readable JSON output for major automation-facing commands.
- MCP server tool coverage for key workflows.
- Custom prompt management, including template rendering with variables.
- Initial persona-gate pipeline primitives with a sandbox proof flow.

## Custom Prompts

Keeli supports project prompts in `docs/prompts/` and renders them through CLI commands.

During `init`, Keeli also generates persona prompts under `.github/prompts/` for slash activation in chat (`/architect`, `/po`, `/developer`, `/qa`, `/security`, `/author`).

```bash
keeli prompt add trello-connector --file ./trello-template.md
keeli prompt list
keeli prompt show trello-connector
keeli prompt apply trello-connector \
  --var board_id=board-123 \
  --var list_architect=list-456 \
  --output .keeli/connectors/trello.json
```

## Pipeline Foundation

The initial pipeline package lives in `src/keeli/pipeline/`:

- `PersonaGate` for deterministic gate ordering.
- `AuditTrail` for persisted gate evidence in SQLite.
- `RegressionScope` for deriving regression scope from `affects` metadata.
- `PipelineRunner` for single-pass gate execution.

Current gate order:

```text
Analyst -> Architect -> Security -> QA -> Regression
```

This is foundation work for experimentation and follow-on CLI integration, not a complete end-user pipeline product yet.

## Sandbox: Test-And-Learn

An isolated sandbox is available at `sandbox/keeli-pipeline-sandbox/`.

It demonstrates:

- Running the pipeline package against a sample task.
- Recording gate evidence in a separate sandbox database.
- Blocking regression when high-risk side effects are unresolved.
- Rendering a Trello-style connector config from a prompt template.

Run:

```bash
cd sandbox/keeli-pipeline-sandbox
keeli init --force
PYTHONPATH=/absolute/path/to/src python run_tnl.py
```

## MCP Support

Keeli exposes an MCP server with tool handlers for common workflows, including:

- `keeli_start`
- `keeli_next`
- `keeli_progress`
- `keeli_complete`
- `keeli_transition_from_commit`
- `keeli_capture_commit_state`

External agents can call these workflow primitives without re-implementing CLI behavior.

## Repository Layout

- `src/keeli/` contains CLI logic, state helpers, MCP server, templates, and pipeline modules.
- `docs/` contains project context, decisions, prompts, tasks, and the AI log.
- `tests/` contains CLI, MCP, and pipeline coverage.
- `sandbox/keeli-pipeline-sandbox/` contains the isolated pipeline experiment.

## Important Behavior

- `keeli init --force` overwrites core docs and instruction files (`docs/project.md`, `docs/decision.md`, `docs/ai_log.md`, `docs/skills.md`, `docs/personas.md`, and `.github/*` templates).
- If the repository is a git project, `keeli init` installs hooks for passive validation and commit capture.

## Notes

- Keeli is hybrid, not DB-only: markdown remains part of the workflow.
- SQLCipher-style encrypted evidence storage is planned work, not finished functionality.
- External connector sync is not yet complete runtime functionality; prompt-driven connector config management is implemented.