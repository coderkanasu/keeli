# Keeli

**Keeli is a host-local MCP tool and grounding framework for disciplined AI-assisted development workflows.**

Keeli is a Python CLI that provides lightweight, queryable state and explicit grounding for AI agents and humans working together. It combines docs-first planning with local cache namespaces, structured JSON state, and strict prompt/gating contracts.

Think of it as a structured local knowledge hub for development workflows: auditable, cache-grounded, and designed to keep model-driven changes aligned with repository context.

## What You'll Usually Do

Typical workflow:

- `keeli init` creates templates and SQLite state (schema v2 with tags, skills, versioning).
- `keeli epic` and `keeli story` define scope and priorities.
- `keeli start` creates a task with auto-inferred tags and required skills.
- Move through `keeli progress` and `keeli complete`.
- Query with MCP tools: `keeli_get`, `keeli_search`, `keeli_find` for fast lookups.
- Use `keeli_digest` for a local context snapshot before making changes.
- Agents and CI can use `keeli capture-commit-state` and `keeli transition-from-commit` to automate lifecycle transitions.

## The Problem Keeli Solves

**AI-assisted delivery at scale needs grounded state, explicit tooling, and local containment.**

When multiple agents or AI-assisted workflows operate on the same codebase, you need:

- **Fast local queries:** Read-heavy operations for agent decision-making without cloud roundtrips
- **Grounded context:** Structured local caches, provenance, and integrity hashes keep AI reasoning aligned with source artifacts
- **Flexible categorization:** Tags instead of rigid personas (security:auth, type:bugfix, urgent, etc.)
- **Audit trail:** Every state change logged for compliance and debugging
- **Batch operations:** Update many tasks with deterministic automation and concurrency safety

Keeli provides:

- Human-readable markdown artifacts in generated project scaffolding
- Machine-readable SQLite state with schema versioning (currently v2)
- A host-local MCP tool surface for grounded tool-driven workflows
- Tag-based categorization with optional auto-inference from content
- Optimistic locking via version column for concurrency control
- Task updates and tag management operations

## Typical Use Cases

Use Keeli when you want one or more of the following:

- **Grounded state management:** Fast local queries and tool-driven consistency for AI-assisted workflows
- **Tag-based categorization:** Flexible classification (security:auth, type:bugfix, urgent, performance:optimization)
- **Audit compliance:** Every state change logged with actor, timestamp, and details
- **Batch operations:** Update 10+ tasks in a single transaction
- **Concurrent safety:** Optimistic locking prevents race conditions with multiple agents
- **CLI-first automation:** For hooks, scripts, CI jobs, and MCP-based agent workflows
- **Docs-first planning:** Teams edit markdown, state stays in sync via `keeli sync`

## Why Teams Pick Keeli

- **Fast queries:** <10ms for most operations, optimized for read-heavy workloads
- **Concurrent-safe:** Version column + optimistic locking prevents conflicts
- **Flexible tagging:** Auto-inferred from content (e.g., "fix auth bug" → security:auth, type:bugfix)
- **12 MCP tools:** streamlined task lifecycle, search, history, and context digest operations
- **Hybrid model:** Docs stay readable, automation stays deterministic
- **Extensible:** Custom tags, skills, and MCP tool patterns

## Schema v2 Features (Current)

Keeli uses schema versioning with automatic migrations:

- **Tags** (JSON array): Flexible categorization (security:auth, type:implementation, urgent)
- **Requires Skills** (JSON array): Skills needed for review (security, testing, architecture)
- **Affects** (JSON array): Components impacted (api, database, frontend)
- **Version** (integer): Optimistic locking counter for concurrent updates
- **Audit Events**: Every state change logged with actor and timestamp

**Migration:** Existing databases auto-migrate from v1 → v2 on first run.

## How To Contribute In 5 Minutes

Help design better AI-engineer workflows, add new skills, or integrate with popular tools.

```bash
# 1) Fork this repo on GitHub, then clone your fork
git clone https://github.com/<your-username>/keeli.git
cd keeli

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

**Standard lifecycle:**

```text
Backlog -> In Progress -> Done
```

Additional states include `Blocked` and reopened work returning to `In Progress`.

**Tag-Based Categorization (Schema v2):**

Tags provide flexible, multi-dimensional classification:

- **Type tags:** `type:implementation`, `type:bugfix`, `type:design`, `type:test`, `type:doc`
- **Security tags:** `security:auth`, `security:payment`, `security:pii`, `security:secrets`
- **Risk tags:** `risk:critical`, `risk:high`, `urgent`, `breaking`
- **Performance tags:** `performance:optimization`, `performance:scaling`
- **Component tags:** `api-change`, `database`, `frontend`, `backend`

**Auto-Inference:**

Keeli automatically infers tags from task titles and descriptions:

```bash
keeli start "Fix authentication bug in login endpoint"
# Auto-tagged: type:bugfix, security:auth, api-change
# Auto-suggests skills: security, architecture
```

**Legacy Personas (Deprecated in v2):**

A legacy persona field is preserved only for backward compatibility and is auto-converted to tags:

- `@po` → `type:requirements` + `skill:product`
- `@architect` → `type:design` + `skill:architecture`
- `@developer` → `type:implementation` + `skill:backend`
- `@qa` → `type:test` + `skill:testing`
- `@security` → `security:review` + `skill:security`
- `@author` → `type:doc` + `skill:documentation`

## Quick Start

```bash
# 1) Install locally
pip install -e .

# 2) Initialize (creates docs, templates, and SQLite state with schema v2)
keeli init --force

# 3) Create planning artifacts
keeli epic "Pipeline compliance gates" -p P0
keeli story "Persona gate engine" --epic pipeline-compliance-gates

# 4) Create tasks with explicit tags
keeli start "Implement OAuth flow" \
  --tags "security:auth,type:implementation,urgent" \
  --requires-skills "security,backend" \
  --affects "api,database" \
  -p P0

# 5) Or let Keeli auto-infer tags from content
keeli start "Fix authentication bug in login endpoint"
# Auto-tagged: type:bugfix, security:auth, api-change
# Auto-suggested skills: security, architecture

# 6) Move through lifecycle
keeli progress fix-authentication-bug-in-login-endpoint
keeli complete fix-authentication-bug-in-login-endpoint

# 7) Query tasks with MCP tools (or Python API)
python -c "
from keeli import query as kquery
# Get tasks with security:auth tag
tasks = kquery.query_tasks(tags=['security:auth'], limit=10)
for t in tasks:
    print(f\"{t['item_id']}: {t['title']}\")
"

# 8) Batch operations
python -c "
from keeli import query as kquery
# Mark multiple tasks as blocked
result = kquery.batch_update_status(
    ['T-0001', 'T-0002', 'T-0003'],
    'Blocked',
    actor='triage-agent'
)
print(f\"Updated {result['success']} tasks\")
"
```

Use command-driven mode for strict transitions and automation. Use docs-first mode for lightweight manual control.

## Using Keeli in an existing project
When working inside a project repository, run Keeli from the project root so the tool can resolve `keeli_state.db`, `docs/tasks/`, and project metadata.

1. Verify the project is healthy:
   - `python -m keeli.main status`
2. Validate task guardrails:
   - `python -m keeli.main validate-task-state`
   - `python -m keeli.main validate-task-state --auto-stub` if you want a temporary active task stub for validation
3. Capture the current project context:
   - `python -m keeli.main digest --budget 2000`
4. Analyze a specific task for grounding and hints:
   - `python -m keeli.main analyze <task-slug>`

**Important:** there is no `keeli learning` command in this repo. Use `keeli analyze` for the task grounding/learning step.

If you use VS Code Copilot or an agent, a project-local hook in `.github/copilot-instructions.md` is a good idea. The hook should remind the agent to prefer Keeli commands for task validation, task analysis, and context summary before generating code changes.

## Requirements-First Workflow

For planning and architecture-heavy work, keep requirements documents under `requirements/`.

1. Update project scope in `requirements/*.md`.
2. Record key decisions in `README.md` or dedicated requirement documents.
3. Log execution notes directly in the repository README or issue tracker.
4. Keep task details in generated task artifacts after running `keeli init`.

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

**Core State Management (Schema v2):**
- SQLite database with schema versioning and automatic migrations (v1 → v2)
- Tag-based categorization with auto-inference from content
- Optimistic locking via version column (prevents concurrent conflicts)
- Audit trail with actor, timestamp, and details for every state change
- Flexible task metadata: tags, requires_skills, affects arrays

**Query Layer (Fast Read Operations):**
- `query_task_by_id()` / `query_task_by_slug()`: Single task lookup (<1ms)
- `query_tasks()`: Filter by status, priority, tags, skills, epic, story (<10ms)
- `search_tasks()`: Full-text search across titles and context (<10ms)
- `count_tasks()`: Dashboard stats without fetching records (<2ms)

**Current Keeli Runtime Tools:**
- `keeli_next`: Get the next task to work on.
- `keeli_complete`: Mark a task completed and archive it.
- `keeli_progress`: Mark a task as In Progress.
- `keeli_start`: Create a new task file and state row.
- `keeli_analyze`: Analyze a task and inject AI context hints.
- `keeli_log`: Append messages to the audit log.
- `keeli_find`: Search by task ID or keyword.
- `keeli_get`: Get a full task record by ID or slug.
- `keeli_search`: Full-text search across task titles and content.
- `keeli_history`: Show log entries for a task ID or keyword.
- `keeli_digest`: Build a token-budgeted project context snapshot.
- `keeli_archive_task`: Move a completed task to `docs/tasks/archive/`.

**CLI Commands:**
- Project initialization with generated docs, Copilot instructions, and SQLite state
- Work item management for epics, stories, tasks, bugs, and features
- Lifecycle commands: backlog, in-progress, blocked, complete, archive flows
- Tag management: `--tags`, `--requires-skills`, `--affects` flags
- Passive validation and automation hooks via `validate-task-state` and `capture-commit-state`
- Commit-intent evaluation with `transition-from-commit`
- SQLite rebuild and dry-run support with `sync`
- Test-run integration with `keeli test`
- Machine-readable JSON output for automation-facing commands
- Custom prompt management with template rendering

**Performance Characteristics:**
- Read operations: <10ms for most queries
- Batch update (10 tasks): ~15ms (10x faster than serial)
- Tag operations: ~2-3ms per task
- Concurrent conflict rate: <1% with 5 agents
- Scales to 10k+ tasks without FTS5 (LIKE queries sufficient)

## Custom Prompts

Keeli supports project prompts in `docs/prompts/` and renders them through CLI commands.


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

Note: pipeline modules are for experimentation and learning. They are not yet a production-ready pipeline product, but they demonstrate how to extend Keeli with deterministic gates.

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

Note: the sandbox is intentionally experimental and learning-oriented. It demonstrates extension patterns for deterministic gates and evidence capture rather than production deployment defaults.

## MCP Support

Keeli exposes an MCP server with a lean tool surface for local task-state grounding and agent workflows.

Current runtime tools focus on:

- task lifecycle transitions: `keeli_start`, `keeli_progress`, `keeli_complete`, `keeli_archive_task`
- task access and search: `keeli_get`, `keeli_find`, `keeli_search`, `keeli_history`
- local grounding and context: `keeli_digest`, `keeli_analyze`
- audit/log operations: `keeli_log`
- next-task workflow: `keeli_next`

This tool surface is intentionally small so agents can use a consistent set of local commands instead of exploring stale or deprecated options.

**Key Features:**
- **Concurrent-safe:** Version-based optimistic locking prevents conflicts
- **Fast:** Read operations <10ms, write operations <15ms
- **Batch-friendly:** Single transaction for multiple updates
- **Auditable:** Every operation logged with actor and timestamp

**Example MCP Tool Usage:**

```python
# Via MCP client
result = await mcp_client.call_tool("keeli_find", {
    "query": "security:auth",
    "status": "Backlog"
})

# Via Python API (direct)
from keeli import query as kquery
tasks = kquery.query_tasks(
    tags=["security:auth", "urgent"],
    status="Backlog",
    limit=20
)
print(f"Found {len(tasks)} task(s)")
```

External agents can call these workflow primitives without re-implementing CLI behavior.

## Tag System and Query Examples

**Tag Categories:**

```python
# Type classification
type:implementation, type:bugfix, type:design, type:test, type:doc, type:refactor

# Security concerns
security:auth, security:payment, security:pii, security:secrets

# Risk levels
risk:critical, risk:high, urgent, breaking

# Performance
performance:optimization, performance:scaling

# Components
api-change, database, frontend, backend
```

**Auto-Inference Examples:**

```bash
# Title: "Fix authentication bug in login endpoint"
# Auto-tags: type:bugfix, security:auth, api-change
# Auto-skills: security, architecture

# Title: "Optimize database queries for dashboard"
# Auto-tags: performance:optimization, database
# Auto-skills: performance, database

# Title: "Document OAuth integration steps"
# Auto-tags: type:doc, security:auth
# Auto-skills: documentation
```

**Query Examples:**

```python
from keeli import query as kquery

# Find all security-related tasks
tasks = kquery.query_tasks(tags=["security:auth", "security:payment"])

# Find urgent high-priority bugs
tasks = kquery.query_tasks(
    tags=["urgent", "type:bugfix"],
    priority="P0",
    status="Backlog"
)

# Search by natural language
tasks = kquery.search_tasks("authentication login oauth")

# Count blocked tasks
count = kquery.count_tasks(status="Blocked")

# Get task history for audit
history = kquery.get_task_history("T-0042", limit=50)

# Batch update multiple tasks
result = kquery.batch_update_status(
    ["T-0001", "T-0002", "T-0003"],
    "Done",
    actor="cleanup-agent"
)

# Add tags to task
result = kquery.add_tags_to_task(
    "T-0042",
    ["urgent", "security:review"],
    actor="security-agent"
)
```

## Repository Layout

- `src/keeli/` contains CLI logic, state helpers, MCP server, templates, and pipeline modules.
- `requirements/` contains the current requirement and architecture documentation.
- `tests/` contains CLI, MCP, and pipeline coverage.
- `sandbox/keeli-pipeline-sandbox/` contains the isolated pipeline experiment.

## Important Behavior

- `keeli init --force` overwrites core docs and instruction files (`docs/project.md`, `docs/decision.md`, `docs/ai_log.md`, `docs/skills.md`, and `.github/*` templates).
- **Schema v2 Migration:** Existing databases automatically migrate from v1 → v2 on first run, adding tags, requires_skills, affects, and version columns.
- **Backward Compatibility:** Legacy persona field is preserved during migration, values auto-converted to tags.
- **Optimistic Locking:** Write operations check version column to prevent concurrent modification conflicts. Retry on version mismatch.
- If the repository is a git project, `keeli init` installs hooks for passive validation and commit capture.

## Performance and Scaling

- **Query Speed:** <10ms for most read operations with <10k tasks
- **Batch Operations:** 10-50x faster than serial updates
- **Concurrent Agents:** <1% conflict rate with 5 agents
- **Scaling:** SQLite with JSON queries handles 10k+ tasks without FTS5
- **Future:** FTS5 full-text search for >50k tasks, semantic search with embeddings

## Roadmap

**Phase 1 (✅ Complete):**
- Schema v2 with tags, skills, affects, version
- Tag auto-inference from content
- Runtime grounding with task search, history, and digest
- Optimistic locking for concurrent updates

**Phase 2 (✅ Complete):**
- Task lifecycle automation (progress, review, complete)
- Audit log and project context snapshot
- Local MCP command surface aligned with project workflow
- Grounded task analysis via `keeli analyze`

**Phase 3 (In Progress):**
- Semantic search with embeddings
- Query telemetry and observability
- Version snapshots for full rollback
- Dashboard: velocity, bottlenecks, tag distribution

**Phase 4 (Planned):**
- Advanced batch operations (batch tag add/remove)
- Server-side retry with exponential backoff
- Real-time change notifications (webhooks/SSE)
- Multi-workspace support

## Notes

- **Hybrid State Model:** SQLite is the canonical source of truth; task artifacts are generated for human readability when project scaffolding is created.
- **Schema Versioning:** Database evolves incrementally with automatic migrations. Current: v2 (tags, skills, optimistic locking).
- **Tag-Based Workflow:** Personas are deprecated in favor of flexible tags. Legacy persona values auto-convert to tags during migration.
- **Concurrent Safety:** Optimistic locking via version column prevents conflicts when multiple agents modify the same task.
- SQLCipher-style encrypted evidence storage is planned work, not finished functionality.
- External connector sync is not yet complete runtime functionality; prompt-driven connector config management is implemented.
- Pipeline gates (PersonaGate, RegressionScope, etc.) are experimental learning modules, not production-ready products.

## Contributors

- [Shankar Patil](https://www.linkedin.com/in/shanvipatil/)
- [Vijay Ranganatha](https://www.linkedin.com/in/vijayranganatha/)

## Community

- Issues: https://github.com/coderkanasu/keeli/issues
- Discussions: https://github.com/coderkanasu/keeli/discussions
- For larger contributions or design ideas, open a draft PR or start a discussion first.

## Related Links

Keeli is open source, and contributions are welcome from builders interested in AI-assisted development workflows, LLM state management, and concurrent-safe task tracking.

- Explore the framework: https://github.com/coderkanasu/keeli
- Study the reference project: https://github.com/coderkanasu/GREENWARD
- Try the live demo: https://greenward-nine.vercel.app