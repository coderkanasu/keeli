# Keeli

Keeli is an AI-first task management system and grounding framework that uses your filesystem as the source of truth. It is designed to bridge the gap between human intent and AI execution by providing a structured, versioned, and context-aware task layer.

## Key Features

- **Filesystem-Backed State**: Tasks are stored as human-readable Markdown files. Keeli treats the directory structure (`.keeli/tasks/backlog`, `active`, etc.) as the canonical status signal, which is automatically mirrored into the file's metadata during indexing.
- **Built for AI Agents**: Native support for Model Context Protocol (MCP), allowing GitHub Copilot, Cursor, and other AI tools to manage your backlog directly.
- **Intelligent Context Management**: Advanced working memory caching, project analysis caching, and knowledge extraction for LLM context continuity.
- **Grounded Context**: The `digest` tool provides token-budgeted snapshots of your project state, prioritizing active tasks and recent changes for LLM context windows.
- **Hybrid Performance**: Uses a local SQLite database for fast querying and velocity insights, while ensuring the entire task state remains fully recoverable from Markdown files.
- **Audit Trails**: Maintains a local event log (SQLite) to track task transitions and developer actions, providing a clear history of project progress.

## Installation

1.  Clone the repository and install in editable mode:
    ```bash
    pip install -e .
    ```

## MCP Integration

Keeli is designed primarily for MCP (Model Context Protocol) integration with AI tools like Cursor, GitHub Copilot, Devin, and other MCP-compatible clients.

### MCP Server Configuration

Configure your `.vscode/mcp.json` or global `mcp.json`:

```json
{
  "mcpServers": {
    "keeli": {
      "command": "python",
      "args": ["-m", "keeli.mcp_server"],
      "type": "stdio"
    }
  }
}
```

### Available MCP Tools

Keeli provides 6 domain-based MCP tools:

1. **`keeli_tasks`** - Unified task management
   - Operations: `create`, `query`, `get`, `get_state`, `next`, `update_status`, `update_field`, `update_tags`, `conflicts`

2. **`keeli_context`** - Context operations
   - Operations: `get`, `set`, `digest` (enhanced with working memory and knowledge integration)

3. **`keeli_sessions`** - Session management
   - Operations: `start`, `focus`, `checkpoint`, `list`

4. **`keeli_memory`** - Working memory and project analysis caching
   - Operations: `set`, `get`, `delete`, `list`, `clear_expired`, `save_analysis`, `get_analysis`, `get_context`

5. **`keeli_knowledge`** - Knowledge extraction and persistent storage
   - Operations: `save`, `get`, `extract`, `list`

6. **`keeli_system`** - System operations
   - Operations: `sync`, `doctor`

### Example MCP Usage

```python
# Create a task
keeli_tasks(operation="create", title="Implement authentication", priority="p1")

# Get project context
keeli_memory(operation="get_context")

# Cache expensive analysis
keeli_memory(operation="save_analysis", analysis_type="code_structure", analysis_content="...")

# Get enhanced digest with working memory
keeli_context(operation="digest", session_id="...", include_working_memory=True)

# Save important knowledge
keeli_knowledge(operation="save", knowledge_type="architecture_pattern", content="...")
```

### Using Keeli with Devin

For detailed instructions on using Keeli with Devin AI, provide Devin with the following prompt structure:

**Keeli Integration Prompt for Devin:**

> You are working with Keeli, an AI-first task management system that uses the filesystem as the source of truth. Keeli provides MCP integration for managing tasks, context, and knowledge.
>
> **Key MCP Tools:**
> - `keeli_tasks` - Create, query, update tasks and manage their lifecycle
> - `keeli_context` - Get project context and token-budgeted digests
> - `keeli_sessions` - Manage work sessions and checkpoints
> - `keeli_memory` - Cache analysis and maintain working memory
> - `keeli_knowledge` - Extract and store project knowledge
> - `keeli_system` - Sync filesystem and run diagnostics
>
> **Typical Workflow:**
> 1. Start a session: `keeli_sessions(operation="start", context="...")`
> 2. Get next task: `keeli_tasks(operation="next")`
> 3. Move to active: `keeli_tasks(operation="update_status", task_id="T-XXXX", new_status="active")`
> 4. Focus session: `keeli_sessions(operation="focus", task_id="T-XXXX")`
> 5. Get context: `keeli_context(operation="digest", session_id="...", include_working_memory=True)`
> 6. Perform work, create checkpoints, and save knowledge
> 7. Move to review: `keeli_tasks(operation="update_status", task_id="T-XXXX", new_status="review")`
>
> **Best Practices:**
> - Always handle conflicts using `keeli_tasks(operation="conflicts")` before updates
> - Use working memory to cache expensive analysis
> - Extract and save important architectural decisions
> - Remember that Markdown files in `.keeli/tasks/` are the source of truth

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

## Configuration

Keeli is highly portable and follows standard Python path conventions.

Keeli can be configured via environment variables:

- `KEELI_ROOT`: Path to the project root (defaults to automatic discovery via `.git` or `.keeli`).
- `PYTHONPATH`: Ensure `src` is in your Python path for the MCP server.
- `KEELI_VERSION_APPEND`: Suffix for the version string (e.g., `.dev1`).
- `KEELI_ENABLE_CLI`: Set to `1` to enable the legacy CLI interface (disabled by default).

## Project Philosophy

1.  **Markdown First**: The filesystem is the authoritative record for current state; the database is a cache.
2.  **Physical State Machine**: A task's status is moved by physically moving the file across status directories.
3.  **AI-Native Design**: Optimized for MCP integration with intelligent context management.
4.  **No Fluff**: Minimal dependencies, maximum portability.

## Directory Structure

```text
.keeli/
├── tasks/
│   ├── backlog/     # Planned work
│   ├── active/      # In-progress work
│   ├── review/      # Pending validation
│   ├── blocked/     # Blocked tasks
│   └── archive/     # Completed history
└── keeli_state.db   # Performance index and context storage
```

## License

MIT
