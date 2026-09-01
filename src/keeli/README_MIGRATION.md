# Keeli v6.0 — Production-Ready Architecture

## Architectural Evolution Summary

| Feature | v5.1 (Current) | v6.0 (Production-Ready) |
|---------|---------------|------------------------|
| **File Location** | `docs/tasks/*.md` (pollutes LLM context) | `.keeli/tasks/*.md` (gitignored, isolated) |
| **Concurrency** | Full-file SHA-256 (409 collisions) | Field-level CRDTs (LWW / OR-Set) |
| **Session Tracking** | Global SQLite `active_session_id` key | Connection-scoped explicit parameters |
| **Multi-Branch** | Inferred from `git branch --show-current` | Explicit `branch` payload per command |
| **Source of Truth** | Markdown files + SQLite index | SQLite event log; Markdown = materialized view |
| **System Interface** | File moves + local CLI | CLI + FastMCP with scoped headers |

---

## Step 1: Storage Isolation

All task data now lives in `.keeli/` at the project root:

```
project-root/
├── .keeli/                 ← NEW: Hidden workspace (gitignored)
│   ├── keeli_state.db      ← SQLite event log + materialized views
│   ├── tasks/              ← Materialized markdown views
│   │   ├── backlog/
│   │   ├── active/
│   │   ├── review/
│   │   ├── blocked/
│   │   └── archive/
│   └── ...
├── src/                    ← Clean: no task noise in code index
├── .gitignore              ← Auto-injected with `.keeli/`
└── README.md
```

**Why this matters:** Cursor, Copilot, Repomix, and other code-indexing tools no longer parse task management metadata alongside your application code. The `.keeli/` folder is automatically added to `.gitignore` on first run.

---

## Step 2: Field-Level CRDTs

### The Problem with v5.1

In v5.1, two agents editing the same task file trigger a `409 CONFLICT` because the entire file is SHA-256 locked:

```
Agent A: edits Description  ──┐
                               ├──> 409 CONFLICT (whole file changed)
Agent B: edits Status      ──┘
```

### The v6.0 Solution

Every field mutation is an append-only event in `task_events`. The engine reconstructs state by replaying events through CRDT merge rules:

```
Agent A: set Description = "New desc"  ──┐
                                          ├──> Auto-merged! No conflict.
Agent B: set Status = "active"         ──┘
                                          Result: Description updated, Status = active
```

### CRDT Primitives

| Primitive | Use Case | Merge Rule |
|-----------|----------|------------|
| **LWW Register** | `status`, `priority`, `title`, `description` | Last write wins by timestamp; vector clock for causality |
| **OR-Set** | `tags`, `dependencies` | Add-wins semantics; concurrent adds preserved, removes only delete observed elements |

### Vector Clocks

Each event carries a vector clock (`{"agent-a": 3, "agent-b": 2}`) enabling:
- **Causal ordering**: `agent-a:3` happened after `agent-a:2`
- **Concurrency detection**: `agent-a:3` and `agent-b:2` are concurrent → trigger LWW tiebreaker
- **Conflict observability**: `keeli_detect_conflicts(task_id)` surfaces concurrent same-field edits

---

## Step 3: Connection-Scoped Sessions

### v5.1 Anti-Pattern

```python
# v5.1: Global mutable flag in SQLite
context_store["active_session_id"] = "abc-123"  # Race condition!
```

### v6.0 Pattern

Every MCP tool and CLI command accepts explicit `session_id` and `branch`:

```python
# v6.0: Stateless engine, stateful connections
keeli_active(task_id="T-0001", session_id="abc-123", branch="feature/auth")
keeli_active(task_id="T-0002", session_id="def-456", branch="feature/ui")
# Both succeed independently — no global flag mutated.
```

### Session Lifecycle

1. **Start**: `keeli_session_start(name="Auth Refactor", branch="feature/auth")` → returns `session_id`
2. **Focus**: `keeli_session_focus(task_id="T-0001", session_id="...")` → scoped to connection
3. **Checkpoint**: `keeli_session_checkpoint(note="Mid-refactor", session_id="...")` → saves context snapshot
4. **Digest**: `keeli_digest(session_id="...", branch="feature/auth")` → token-budgeted scoped context

---

## Step 4: System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐    │
│  │  Cursor IDE │  │  Copilot    │  │  Custom Agent       │    │
│  │  (FastMCP)  │  │  (FastMCP)  │  │  (HTTP/gRPC future) │    │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘    │
└─────────┼────────────────┼────────────────────┼───────────────┘
          │                │                    │
          └────────────────┴────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  FastMCP    │  ← Connection-scoped session_id + branch headers
                    │   Server    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌──▼───┐ ┌─────▼──────┐
        │  CRDT     │ │Context│ │  Materialized│
        │  Event    │ │Store  │ │  Views (MD)  │
        │  Log      │ │(scoped)│ │  .keeli/tasks│
        │ (SQLite)  │ │       │ │              │
        └───────────┘ └───────┘ └──────────────┘
```

---

## Migration Guide

### 1. Install v6.0

```bash
cd keeli
pip install -e .
```

### 2. Migrate Existing Tasks

```bash
# v6.0 auto-detects legacy docs/tasks/ and imports on first sync
keeli doctor        # Initializes .keeli/ workspace
keeli sync          # Rebuilds event log from existing tasks + creates .keeli/ structure
```

### 3. Update MCP Configuration

Replace `.vscode/mcp.json`:

```json
{
  "mcpServers": {
    "keeli": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "keeli.mcp_server"],
      "env": { "PYTHONPATH": "." }
    }
  }
}
```

### 4. Update Agent Prompts

Remove v5.1 expected_hash workflow from agent instructions. Replace with:

> "Use `keeli_get(task_id)` to read state. Use `keeli_active/complete/edit_field` directly without hash checks. CRDTs handle concurrency automatically. Always pass `session_id` and `branch` explicitly."

---

## New CLI Commands

| Command | Description |
|---------|-------------|
| `keeli state <id>` | Show structured CRDT state + vector clock |
| `keeli edit <id> --field X --value Y` | Generic field mutation |
| `keeli tag-add <id> tag1 tag2` | OR-Set add |
| `keeli tag-rm <id> tag1 tag2` | OR-Set remove |
| `keeli conflicts <id>` | Detect concurrent same-field edits |
| `keeli doctor` | Health check + .gitignore verification |

---

## Schema Changes

### New Tables

- **`task_events`** — Append-only CRDT event log (source of truth)
- **`branch_snapshots`** — Per-branch materialized views
- **`conflict_log`** — Observability for auto-resolved concurrent edits

### Removed Patterns

- ❌ `version_hash` column in `task_index` — replaced by `vector_clock`
- ❌ Global `active_session_id` in `context_store` — sessions are connection-scoped
- ❌ `expected_hash` parameter in all mutation APIs — CRDTs handle convergence

---

## Performance Characteristics

| Metric | v5.1 | v6.0 |
|--------|------|------|
| Task creation | File write + SHA-256 + SQLite upsert | Event append + materialize |
| Concurrent edits | 409 CONFLICT (retry loop) | Zero-conflict merge (O(1) per field) |
| Sync/Rebuild | File tree walk + hash comparison | Event log replay + view rebuild |
| Branch isolation | None (single working tree) | Explicit branch snapshots |
| LLM context pollution | High (`docs/` indexed) | Zero (`.keeli/` gitignored) |
