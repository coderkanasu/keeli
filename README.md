# Keeli

Keeli is a Python CLI for running AI-assisted software delivery with structured project artifacts, a SQLite-backed state model, audit logging, and automation hooks.

It gives you a file-first workflow for humans and a machine-readable workflow for tooling:

- Markdown in `docs/` stays readable and editable.
- `keeli_state.db` gives fast structured state for CLI automation and MCP tools.
- Git hooks and commit/test helpers reduce manual status updates.
- JSON envelopes make command output stable for agents and scripts.

## What Is Implemented

Keeli currently provides:

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
- Initial persona-gate pipeline primitives and an isolated sandbox proving the flow.

## Core Model

Keeli uses a hybrid model:

- Markdown files in `docs/tasks/` are the human-facing work artifacts.
- `keeli_state.db` is the structured operational state used for fast queries, audit correlations, and automation.

The standard lifecycle is:

```text
Backlog -> In Progress -> Review -> Completed -> Archived
```

Additional operational states include `Blocked` and reopened work returning to `In Progress`.

The built-in personas are:

- `@po` for requirements and acceptance criteria.
- `@architect` for design, interfaces, and decisions.
- `@developer` for implementation.
- `@qa` for test evidence and regression safety.
- `@security` for threat modeling and secrets/auth concerns.
- `@author` for user-facing documentation.

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# 1) Initialize a Keeli project
keeli init --force

# 2) Create planning artifacts
keeli epic "Pipeline compliance gates" -p P0 -o "Introduce deterministic delivery gates"
keeli story "Persona gate engine" --epic pipeline-compliance-gates --role platform-engineer --goal "enforce ordered gates" --reason "prevent unsafe transitions" --ac "Transitions require prior evidence" -p P0

# 3) Create implementation work
keeli start "Build pipeline runner" --epic pipeline-compliance-gates --story persona-gate-engine -k developer -p P0 -o "Implement the first pipeline pass"

# 4) Move the task through the lifecycle
keeli progress build-pipeline-runner
keeli review build-pipeline-runner
keeli complete build-pipeline-runner
```

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

These are the commands most useful for hooks, scripts, and agents:

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

Most automation-facing commands now use a shared JSON envelope shaped like:

```json
{
  "ok": true,
  "command": "sync",
  "timestamp": "2026-03-12T03:39:31Z",
  "data": {}
}
```

That envelope is implemented across commit automation, lifecycle transitions, discovery/read flows, and context helpers such as `history` and `digest`.

## Custom Prompts

Keeli supports project prompts stored in `docs/prompts/` and rendered through the CLI.

```bash
keeli prompt add trello-connector --file ./trello-template.md
keeli prompt list
keeli prompt show trello-connector
keeli prompt apply trello-connector \
  --var board_id=board-123 \
  --var list_architect=list-456 \
  --output .keeli/connectors/trello.json
```

This is currently used to manage connector configuration templates without hardcoding provider-specific values into the CLI.

## Pipeline Foundation

Keeli now includes an initial pipeline package in `src/keeli/pipeline/`:

- `PersonaGate` for deterministic gate ordering.
- `AuditTrail` for persisted gate evidence in SQLite.
- `RegressionScope` for deriving a regression scope from `affects` metadata.
- `PipelineRunner` for single-pass gate execution.

The current gate order is:

```text
Analyst -> Architect -> Security -> QA -> Regression
```

This is foundation work, not a complete end-user pipeline product yet. The implemented pieces are intended for experimentation, tests, and follow-on CLI integration.

## Sandbox And Test-And-Learn

The repository includes an isolated sandbox at `sandbox/keeli-pipeline-sandbox/`.

It demonstrates:

- Running the pipeline package against a sample task.
- Recording gate evidence in a separate sandbox database.
- Blocking regression when high-risk side effects are unresolved.
- Rendering a Trello-style connector config from a prompt template.

Run it with:

```bash
cd sandbox/keeli-pipeline-sandbox
keeli init --force
PYTHONPATH=/absolute/path/to/src python run_tnl.py
```

## MCP Support

Keeli exposes a matching MCP server with tool handlers for common workflows, including:

- `keeli_start`
- `keeli_next`
- `keeli_progress`
- `keeli_complete`
- `keeli_transition_from_commit`
- `keeli_capture_commit_state`

This lets external agents call the same workflow primitives without re-implementing CLI behavior.

## Repository Layout

- `src/keeli/` contains the CLI, state helpers, MCP server, templates, and pipeline package.
- `docs/` contains project context, decisions, prompts, tasks, and the audit log.
- `tests/` contains CLI, MCP, and pipeline coverage.
- `sandbox/keeli-pipeline-sandbox/` contains the isolated pipeline experiment.

## Recent Accomplishments

The current repository state includes the following delivered work:

- Shared JSON envelope across core CLI automation commands.
- JSON support for lifecycle and discovery commands such as `progress`, `complete`, `next`, `list`, `find`, `history`, and `digest`.
- Deterministic commit transition evaluation and apply flows.
- Commit capture with correlated audit event IDs.
- Dry-run support for `sync`, `test`, and commit transition application.
- Prompt application with variable substitution and file output.
- Architecture and backlog formalization for persona-routing pipeline work.
- Initial persona-gate pipeline modules and tests.
- Sandbox validation of blocked and passing regression gate behavior.

## Notes

- Keeli is currently hybrid, not DB-only. Markdown remains part of the workflow.
- SQLCipher-style encrypted evidence storage is planned work, not finished functionality.
- External connector sync is not yet implemented as a complete runtime feature; prompt-driven connector config management is implemented.
- If you are using a git repository, `keeli init` installs hook scripts to support passive validation and commit capture.