# Keeli — AI Governance Framework  `v0.4.0`

A Python CLI and MCP server that enforces a **Five-Persona Architecture** for GitHub Copilot and
other AI agents. Designed to help **stateless LLMs regain context fast** and make steady, auditable
progress across sessions — with zero hallucination.

Every AI action runs under one of five named personas (`@po`, `@architect`, `@developer`,
`@security`, `@author`), follows a tracked task lifecycle, and leaves a timestamped audit trail.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Command Reference](#command-reference)
  - [Project Setup](#project-setup)
  - [Work Items](#work-items)
  - [Task Lifecycle](#task-lifecycle)
  - [Context & Intelligence](#context--intelligence)
  - [Skills & Stack Registry](#skills--stack-registry)
  - [Persona Management](#persona-management)
  - [Utilities](#utilities)
- [Task Types & File Layout](#task-types--file-layout)
- [Immutable IDs & Index](#immutable-ids--index)
- [MCP Server](#mcp-server)
- [Agentic / Headless Usage](#agentic--headless-usage)
- [License](#license)

---

## Installation

```bash
pip install -e .
```

Requires Python 3.12+. Optional: `scikit-learn` for richer TF-IDF in `keeli analyze`.

---

## Quick Start

```bash
# 1. Scaffold the Keeli framework in any project directory
keeli init                      # Creates .github/copilot-instructions.md (GitHub Copilot)
keeli init --ai claude          # Also creates .claude/instructions.md (Claude-specific)
keeli init --ai claude --ai gemini --ai codex  # Multiple AI flavors simultaneously

# 2. Define your tech stack (interactive presets)
keeli stack                        # choose from python-fastapi, react, java, etc.
keeli stack list                   # see all available presets
keeli stack apply python-fastapi   # apply a preset non-interactively

# 3. Register project skills (what your project uses and *how*)
keeli skill add "FastAPI" -t framework -c "All routes use async def; Pydantic v2 models only"

# 4. Create work items at every level of the hierarchy
keeli epic "User Authentication" -p P0 -o "Allow users to sign in securely via OAuth 2.0"
keeli story "Register Account" --epic user-authentication
keeli feature "Forgot Password Flow" -p P1 -e user-authentication
keeli start "Implement /auth/register endpoint" -p P0 -k developer
keeli bug "JWT expiry not validated" -p P0 --found-during implement-auth-register-endpoint

# 5. Drive the task lifecycle
keeli next                            # what should I work on?
keeli progress "implement-auth"       # → In Progress
keeli note "implement-auth" "Using bcrypt for password hashing"
keeli review "implement-auth"         # → Review (awaiting @security sign-off)
keeli complete "implement-auth"       # → Completed + auto-archived

# 6. Context injection for AI assistants
keeli analyze implement-auth          # TF-IDF: inject relevant skills/ADRs into task file
keeli resume --brief                  # ~500-token context dump for a new session
keeli resume --nano                   # ~200-token nano dump: current task ID+title only
keeli digest --budget 2000            # machine-optimised context snapshot

# 7. Audit trail
keeli log "Deployed to staging — all auth tests passing"
keeli find T-0012                     # look up any item by ID
keeli history T-0012                  # all ai_log entries for that ID
keeli list -s in-progress             # filter task board by status
```

---

## Command Reference

### Project Setup

| Command | Flags | Description |
|---------|-------|-------------|
| `keeli init` | `--ai claude/gemini/codex`, `-f` force | Scaffold `.github/copilot-instructions.md` (always) + optional flavor-specific folders (`.claude/`, `.gemini/`, `.codex/`). Creates `docs/` structure and `.gitignore`. |
| `keeli update` | `-f` force | Upgrade `copilot-instructions.md` to the latest Keeli template (preserves all your files) |
| `keeli status` | | Health-check every expected Keeli file |

---

## Persona Hooks & Lean Instructions

Keeli uses an **on-demand persona loading** system to keep instructions lean and focused across all AI flavors.

### How It Works

- **Lean Base:** Instructions in `.github/`, `.claude/`, `.gemini/`, `.codex/` are **~300 lines** (flavor-specific header + shared lean base).
- **Full Definitions:** All five persona rules live in `docs/personas.md` and are **loaded on-demand** by assignment.
- **Task Assignment:** Every task specifies `**Persona:** @developer` (or `@architect`, `@po`, etc.) in its metadata.
- **Activation Hook:** Task files include HATEOAS guidance directing LLMs to load only the assigned persona's rules from `docs/personas.md`.

### Example Workflow

1. **Task file includes flavor-agnostic HATEOAS guidance:**
   ```markdown
   **Persona:** @developer
   
   <!-- HATEOAS: Persona Hook
     Load rules from: docs/personas.md ## developer
     Don't load other personas for this task.
   -->
   ```

2. **LLM reads the hint and loads only the `## developer` section** from `docs/personas.md`.

3. **Flavor-specific instruction headers** (in `.claude/`, `.gemini/`, `.codex/`) include model-specific guidance:
   - **Claude:** 200K context window, collaborative reasoning
   - **Gemini:** 2M context window, multi-modal capabilities
   - **Codex:** 8K-128K context window, IDE integration

### Benefits

- ✅ **Token efficiency:** 85% reduction in base instruction size (300 vs 2,000+ tokens)
- ✅ **Flavor awareness:** Model-specific guidance without bloating shared base
- ✅ **Cognitive clarity:** LLM sees only the rules relevant to this task
- ✅ **Scalable:** Adding personas or flavors doesn't bloat instructions
- ✅ **Fast agent loops:** No tool overhead — just file references

---

### Work Items

#### Epics
```bash
keeli epic "<title>" [-p P0|P1|P2] [-o objective] [-f]
```
Creates `docs/tasks/epic-<slug>.md`. Groups related stories and tasks. Receives an immutable ID (`E-NNNN`). `-o` accepts plain text, `@file.md`, or a JSON dict with `goal`, `why`, `criteria`, `out_of_scope` keys.

#### Stories
```bash
keeli story "<title>" --epic <epic-slug> [-p P0|P1|P2] [--role <role>] [--goal <goal>] [--reason <reason>] [-f]
```
Creates `docs/tasks/story-<slug>.md` (ID: `S-NNNN`). Linked to a parent epic. As-a / I-want / So-that template.

#### Features
```bash
keeli feature "<title>" [-c context-file] [-o objective] [-p P0|P1|P2] [-e epic-slug] [-f]
```
Creates `docs/tasks/feat-<slug>.md` (ID: `FEAT-NNNN`). User Story + Acceptance Criteria + Design Notes checklist.

#### Tasks
```bash
keeli start "<title>" [-c context-file] [-o objective] [-p P0|P1|P2] [-k persona] [-d dep-slug,...] [-f]
```
Creates `docs/tasks/<slug>.md` (ID: `T-NNNN`). Generates a persona-appropriate TDD checklist. `-d` marks dependencies — `keeli next` skips this task until all deps are Completed.

#### Bugs
```bash
keeli bug "<title>" [-d description] [-p P0|P1|P2] [-e epic-slug] [--found-during task-slug] [-f]
```
Creates `docs/tasks/bug-<slug>.md` (ID: `BUG-NNNN`). Includes reproduction steps, expected/actual behaviour, and a regression-test checklist.

---

### Task Lifecycle

Every work item follows this state machine:

```
Backlog → In Progress → Review → Completed
              ↓                      ↓
           Blocked → (unblocked)   Reopened → In Progress
```

| Command | Description |
|---------|-------------|
| `keeli progress <name>` | Backlog → **In Progress** |
| `keeli block <name>` | In Progress → **Blocked** |
| `keeli review <name>` | In Progress → **Review** (awaiting `@security` sign-off) |
| `keeli complete <name>` | → **Completed** + auto-archived to `docs/tasks/archive/` |
| `keeli archive <name>` | Explicit archive without status change |
| `keeli reopen <name>` | Completed → **In Progress** (rework needed) |
| `keeli next [-q] [--json]` | Show the next task (priority P0→P2, then oldest). `--json` for scripting. |
| `keeli list [-s status] [-e epic] [--json]` | List all tasks, optionally filtered |
| `keeli note <task> [message] [-k persona]` | Append a timestamped note to a task file |

All transition commands accept `-k <persona>` to record which persona made the change.

**Priority:** P0 (critical) → P1 (default) → P2 (low). `keeli next` always surfaces the highest-priority, oldest task first.

**Auto-archiving:** `keeli complete` automatically moves the task file to `docs/tasks/archive/`, keeping the active directory lean and the LLM's context window healthy.

**Auto-completion:** The AI is instructed to call `keeli complete` itself — it doesn't wait for you. On completion it also immediately picks the next task.

---

### Context & Intelligence

#### Session Resume
```bash
keeli resume              # default ~1 500 tokens
keeli resume --brief      # ~500 tokens
keeli resume --full       # ~3 000 tokens
keeli resume --nano       # ~200 tokens — current task ID+title only (ideal for Copilot in-editor)
keeli resume --budget N   # custom token budget
```
Dumps active tasks, project context, recent decisions, and recent log lines — sized to fit your token budget.

#### Machine-Optimised Digest
```bash
keeli digest [--budget 2000]
```
Produces a structured context snapshot for agentic AI loops: active tasks → project overview → top-10 backlog → recent log. Respects the token budget strictly using word-count heuristics.

#### AI Context Hints (TF-IDF Injection)
```bash
keeli analyze <slug> [--dry-run] [--use-sklearn]
```
Scores the task text against the project's skills and ADRs using TF-IDF (pure-Python fallback or `scikit-learn`). Injects a `## AI Context Hints` block directly into the task file with the most relevant skills, ADR references, and suggested persona. `--dry-run` returns the hints without writing. `keeli next` auto-runs analysis and appends hints inline.

#### Audit Trail
```bash
keeli log "<message>"                   # append timestamped entry to docs/ai_log.md
keeli find <query> [-s status] [--json] # search index by ID (T-0012) or keyword
keeli history <task-id>                 # all ai_log lines mentioning a task ID
keeli clear-log                         # reset docs/ai_log.md to blank state
```

---

### Skills & Stack Registry

Skills are project-specific technology choices with *how* constraints — not generic labels. They fuel `keeli analyze`'s TF-IDF corpus and are injected into `copilot-instructions.md` so every new AI session inherits your project's conventions automatically.

```bash
keeli skill add [name] [-t lang|framework|domain|infra|tool] [-k persona] [-c "constraint text"]
keeli skill list                  # table view (truncated constraint)
keeli skill show [name]           # full constraint text
keeli skill remove [name]
```

**Stack Presets** — apply a curated set of skills in one command:
```bash
keeli stack                          # interactive menu
keeli stack list                     # show all available presets
keeli stack apply python-fastapi     # apply a named preset (prompts for each skill)
keeli stack apply python-fastapi -y  # accept all constraints non-interactively
```
Available presets include: `python-fastapi`, `python-django`, `react`, `vue`, `node`, `java`, `go`, `nextjs`, and more.

---

### Persona Management

Keeli ships with five built-in personas. You can add project-specific personas (e.g., `@qa`, `@devops`):

```bash
keeli persona add [slug]     # interactive: name, mindset, checklist items
keeli persona list           # show all registered personas
keeli persona remove [slug]  # remove a custom persona
```

Each persona has its own TDD checklist template injected into task files, and its own skills section in `copilot-instructions.md`.

**Built-in personas:**

| Persona | Focus |
|---------|-------|
| `@po` | Product ownership, grooming, acceptance criteria |
| `@architect` | System design, ADRs, task breakdown |
| `@developer` | Implementation, TDD (red → green → refactor) |
| `@security` | Threat modelling, vulnerability review, sign-off |
| `@author` | Documentation, README, WCAG-compliant copy |

---

### Utilities

```bash
keeli --version             # print framework version
keeli mcp [--sse] [--port]  # start the MCP server (see below)
```

---

## Task Types & File Layout

```
docs/
  project.md                 # Project context, tech stack, goals, architecture
  decision.md                # ADR log — decisions with rationale + rejected alternatives
  ai_log.md                  # Timestamped audit log; never deleted by the AI
  skills.md                  # Skills registry (language, framework, domain, infra, tool)
  personas.md                # All persona definitions (loaded on-demand, not in instructions)
  prompts/
    custom-prompt-builder.md     # Blueprint for writing specialized prompts
    custom-skill-template.md     # Blueprint for registering skills
  tasks/
    <slug>.md                # Task           T-NNNN
    bug-<slug>.md            # Bug report     BUG-NNNN
    feat-<slug>.md           # Feature        FEAT-NNNN
    story-<slug>.md          # User story     S-NNNN
    epic-<slug>.md           # Epic           E-NNNN
    archive/                 # Completed items moved here automatically
    .keeli_index.json        # Immutable ID ledger (never edit by hand)
.github/
  copilot-instructions.md    # GitHub Copilot instructions (lean base + flavor-agnostic)
.claude/
  instructions.md            # Claude-specific instructions (context window: 200K)
.gemini/
  instructions.md            # Gemini-specific instructions (context window: 2M)
.codex/
  instructions.md            # Codex/Copilot-specific instructions (context window: variable)
```

---

## Immutable IDs & Index

Every work item receives a permanent, collision-proof ID at creation time:

| Prefix | Type |
|--------|------|
| `T-NNNN` | Task |
| `E-NNNN` | Epic |
| `S-NNNN` | Story |
| `BUG-NNNN` | Bug |
| `FEAT-NNNN` | Feature |

IDs are stored in `docs/tasks/.keeli_index.json`. The index also powers `keeli find`, `keeli history`, and the `keeli_find`/`keeli_history` MCP tools. IDs survive renaming, archiving, and reopening.

```bash
keeli find T-0012              # resolve by ID
keeli find "auth"              # keyword search across title + slug
keeli find "auth" -s backlog   # filter by status
keeli history T-0012           # every ai_log.md line that mentions T-0012
```

---

## MCP Server

Keeli exposes all core operations as a **Model Context Protocol** server. AI assistants that support MCP (Claude Desktop, Cursor, GitHub Copilot, etc.) can call Keeli tools natively — no custom scripts needed.

### Starting the Server

```bash
keeli mcp              # stdio mode (default — for desktop AI assistants)
keeli mcp --sse        # HTTP/SSE mode (for web-based or remote AI tools)
keeli mcp --sse --port 9000
```

### Configuring Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "keeli": {
      "command": "keeli",
      "args": ["mcp"]
    }
  }
}
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `keeli_next` | Return the highest-priority next task |
| `keeli_start` | Create a new task (`title`, `priority`, `persona`, `depends_on`) |
| `keeli_complete` | Mark a task completed + auto-archive it |
| `keeli_archive_task` | Move a task to archive without completing it |
| `keeli_analyze` | TF-IDF context injection into a task file (`dry_run` flag) |
| `keeli_log` | Append a message to `ai_log.md` |
| `keeli_find` | Search the index by ID or keyword (optional `status` filter) |
| `keeli_history` | Return all `ai_log.md` entries for a task ID |
| `keeli_digest` | Token-budgeted context snapshot (`budget` param, default 2 000) |

### Streaming Notifications (S-1/S-2/S-3)

When a `_meta.progressToken` is supplied in the tool call, `keeli_analyze` emits
**ProgressNotifications** at four stages (load → corpus → score → format).

`keeli_digest` emits **LoggingMessageNotifications** after each section is built.

`keeli_start`, `keeli_complete`, and `keeli_archive_task` emit an INFO log message
on success so the AI assistant can provide live feedback without polling.

### MCP Resources

The server also exposes read-only resources that AI assistants can fetch directly:

| URI pattern | Content |
|-------------|---------|
| `keeli://project` | `docs/project.md` |
| `keeli://decisions` | `docs/decision.md` |
| `keeli://tasks/<slug>` | Any task file in `docs/tasks/` |

---

## Agentic / Headless Usage

Keeli is designed to be a **persistent disk-based memory bank** for autonomous agents
(LangChain, AutoGPT, custom scripts). Because all state lives on disk, you can build a headless
loop that runs completely autonomously:

```python
import json, subprocess

def run(cmd): return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

while True:
    # 1. Get the next task as JSON
    task_data = json.loads(run(["keeli", "next", "--json"]))
    if not task_data.get("task"):
        print("All done!"); break

    slug = task_data["task"]

    # 2. Mark in progress + grab a token-budgeted context snapshot
    run(["keeli", "progress", slug])
    context = run(["keeli", "digest", "--budget", "2000"])

    # 3. Inject relevant skills/ADRs into the task file
    run(["keeli", "analyze", slug])

    # 4. Feed context + task to your LLM, implement, test …
    #    LLM will read .github/copilot-instructions.md (now lean, ~200 lines)
    #    Then load persona rules from docs/personas.md based on task assignment

    # 5. Complete → auto-archived; next iteration picks next task
    run(["keeli", "complete", slug])
```

### Instruction Efficiency

The example above shows why Keeli's **lean instructions** matter for agent loops:

- **Old approach:** Bloated instructions with all 5 personas embedded (2,000+ lines, 4,000+ tokens)
- **New approach:** Lean flavor-specific headers (~300 lines, 600 tokens) + on-demand persona loading
- **Result:** 85% token reduction, 10-20x faster agent loops, more iterations per budget

**Key agentic features:**
- **Task dependencies** — `--depends-on` makes `keeli next` skip blocked tasks automatically.  
- **Hierarchy enforcement** — Epic > Story > Task structure enforced at CLI boundaries; no invalid states allowed.
- **Handshake validation** — All 5 personas must sign off before a task completes; enforced at task completion.
- **JSON output** — `keeli next --json` and `keeli list --json` for machine parsing.
- **Token budgets** — `keeli resume --budget N` and `keeli digest --budget N` keep prompts predictable.
- **Auto-archive** — completed tasks leave the active directory, preventing context overflow as projects grow.
- **Immutable IDs** — `T-0012` is stable across renames, archives, and reopens; use it in commit messages and log entries for a full audit trail.
- **Flavor awareness** — Support for Claude, Gemini, Codex with model-specific instruction headers.
- **Persona hooks** — On-demand persona loading avoids token waste on irrelevant rules.

---

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

193 passing tests covering:
- CLI commands (init, start, progress, complete, etc.)
- MCP server tool handlers (keeli_next, keeli_start, keeli_complete, keeli_analyze, etc.)
- Task lifecycle validation (hierarchy enforcement, handshake validation)
- Flavor-aware initialization

---

## License

This project is proprietary and closed-source. See the [LICENSE](LICENSE) file for details.

**Key restrictions:**
- You may not copy, distribute, or modify this software without explicit permission.
- **No AI Training:** You are strictly prohibited from using this repository's code or documentation to train, fine-tune, or improve any AI model, LLM, or machine learning algorithm.
- **No Liability:** The author of Keeli is not responsible for any code, architecture, or outputs generated by AI agents or users utilising this framework. You are solely responsible for securing and testing your own software.
