# Keeli

Keeli is an AI-first task management system and grounding framework that uses your filesystem as the source of truth. It is designed to bridge the gap between human intent and AI execution by providing a structured, versioned, and context-aware task layer.

## Key Features

- **Filesystem as Source of Truth**: Tasks are stored as human-readable Markdown files. Directory structure defines task status (`docs/tasks/backlog`, `docs/tasks/active`, etc.).
- **Built for AI Agents**: Native support for Model Context Protocol (MCP), allowing GitHub Copilot, Cursor, and other AI tools to manage your backlog directly.
- **Grounded Context**: The `digest` tool provides token-budgeted snapshots of your project state, ensuring your AI agent always has the most relevant context.
- **Performance Indexing**: Uses a local SQLite database for fast querying and insights while remaining fully recoverable from the filesystem.

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
2.  **MCP Server**: Configure your `.vscode/mcp.json`:
    ```json
    {
      "mcpServers": {
        "keeli": {
          "command": "python3",
          "args": ["-m", "keeli.mcp_server"],
          "env": {
            "PYTHONPATH": "src"
          }
        }
      }
    }
    ```

## Configuration

Keeli can be configured via environment variables:

- `KEELI_ROOT`: Path to the project root (defaults to automatic discovery via `.git` or `docs/tasks`).
- `PYTHONPATH`: Ensure `src` is in your Python path for the MCP server.
- `KEELI_VERSION_APPEND`: Suffix for the version string (e.g., `.dev1`).

## Project Philosophy

1.  **Markdown First**: If the database is lost, the filesystem is the recovery signal.
2.  **Status is Directory**: A task's status is its physical location on disk.
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
