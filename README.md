# Keeli

Keeli is an AI-first task management system and grounding framework that uses your filesystem as the source of truth. It is designed to bridge the gap between human intent and AI execution by providing a structured, versioned, and context-aware task layer.

## Key Features

- **Filesystem-Backed State**: Tasks are stored as human-readable Markdown files. Keeli treats the directory structure (`docs/tasks/backlog`, `active`, etc.) as the canonical status signal, which is automatically mirrored into the file's metadata during indexing.
- **Built for AI Agents**: Native support for Model Context Protocol (MCP), allowing GitHub Copilot, Cursor, and other AI tools to manage your backlog directly.
- **Grounded Context**: The `digest` tool provides token-budgeted snapshots of your project state, prioritizing active tasks and recent changes for LLM context windows.
- **Hybrid Performance**: Uses a local SQLite database for fast querying and velocity insights, while ensuring the entire task state remains fully recoverable from Markdown files.
- **Audit Trails**: Maintains a local event log (SQLite) to track task transitions and developer actions, providing a clear history of project progress.

## Installation

1.  Clone the repository and install in editable mode:
    ```bash
    pip install -e .
    ```
2.  Initialize your workspace:
    ```bash
    keeli doctor
    ```

## CLI Usage

Keeli provides a powerful CLI for interacting with your tasks:

- **Creating Tasks**: `keeli start "Implement authentication"`
- **Listing Tasks**: `keeli list --status active`
- **Prioritizing**: `keeli next` (Suggests the most important task to work on)
- **Status Updates**:
  - `keeli active T-0001`
  - `keeli review T-0001`
  - `keeli complete T-0001`
- **Context Injection**: `keeli digest --tier standard --budget 2000`
- **Health Check**: `keeli doctor` (Validates your workspace and reconstructs indices)

## Task Structure

Every task is a Markdown file with structured metadata. This allows both humans and machines to parse task state easily.

```markdown
# T-0001: Implement authentication

**Status:** backlog
**Priority:** p0
**Created:** 2026-07-17T12:00:00Z
**Completed:** —
**Depends On:** 
**Tags:** feature:auth, security:high

## Description
[Detailed description of the task]

## Acceptance Criteria
- [ ] Criterion 1

## Implementation Notes
...
```

## Integration

### GitHub Copilot (VS Code)

Keeli integrates seamlessly with GitHub Copilot as a Skill and MCP Server.

1.  **Skill**: Add the `keeli` skill to your `.github/skills/keeli/SKILL.md` to help Copilot understand task-related prompts.
### MCP Server (VS Code / Cursor)

Configure your `.vscode/mcp.json` or global `mcp.json`:

```json
{
  "mcpServers": {
    "keeli": {
      "command": "/opt/homebrew/anaconda3/bin/keeli",
      "args": ["mcp"],
      "type": "stdio"
    }
  }
}
```

## Configuration

Keeli is highly portable and follows standard Python path conventions.

Keeli can be configured via environment variables:

- `KEELI_ROOT`: Path to the project root (defaults to automatic discovery via `.git` or `docs/tasks`).
- `PYTHONPATH`: Ensure `src` is in your Python path for the MCP server.
- `KEELI_VERSION_APPEND`: Suffix for the version string (e.g., `.dev1`).

## Project Philosophy

1.  **Markdown First**: The filesystem is the authoritative record for current state; the database is a cache.
2.  **Physical State Machine**: A task's status is moved by physically moving the file across status directories.
3.  **No Fluff**: Minimal dependencies, maximum portability.

## Directory Structure

```text
docs/
├── tasks/
│   ├── backlog/     # Planned work
│   ├── active/      # In-progress work
│   ├── review/      # Pending validation
│   ├── blocked/     # Blocked tasks
│   └── archive/     # Completed history
└── learnings/       # AI-captured project insights
keeli_state.db        # Performance index (cached)
```

## License

MIT
