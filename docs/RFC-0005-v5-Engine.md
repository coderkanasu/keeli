# RFC-0005: Keeli v5.0 Multi-Context Session & Project Scaffolding Engine

**Status:** Approved (Architect Signoff)
**Version:** 5.0.0
**Date:** 2026-07-17

## 1. Executive Summary
Keeli v5.0 evolves from a file-backed task database into a stateful orchestration layer. It introduces persistent sessions, layered context (Global > Branch > Session), and token-budgeted intelligence to eliminate context drift and hallucination in AI-assisted workflows.

## 2. Core Architecture changes
- **Daemonized MCP**: Transition from stateless subprocess-based execution to a persistent FastMCP daemon.
- **Stateful Sessions**: Introduction of `sessions`, `checkpoints`, and `working_memory` tables.
- **Layered Context**: Hierarchical resolution of environment variables and setup steps.
- **Intelligence Layer**: Explicit token budgeting using `tiktoken`.

## 3. Data Model Additions

### New Tables
- `sessions`: Tracks LLM conversation threads and focus tasks.
- `context_store`: Hierarchical key-value store for project settings.
- `checkpoints`: Snapshots of session state for reliability.
- `working_memory`: Ephemeral scratchpad for session-local reasoning.
- `task_fts`: FTS5 virtual table for high-speed task searching.

## 4. Implementation Phases

### Phase 1: Engine Refactoring
- Extract logic from `main.py` into `KeeliEngine` class.
- Separate core operations (Task/Sync) from CLI presentation.

### Phase 2: Schema & Daemon
- Implement SQLite migrations for v5.0 tables.
- Update `mcp_server.py` to support the new stateful API.

### Phase 3: Context Resolution
- Implement the Context Engine (Global > Branch > Session waterfall).
- Add discovery logic for common project manifests (`pyproject.toml`, etc.).

### Phase 4: Session Management
- Implement session lifecycle tools (`start`, `focus`, `checkpoint`).
- Integrate audit logs with session IDs.

### Phase 5: Optimization
- Integrate `tiktoken` for hard-budgeted digests.
- Implement FTS5 search.

## 5. Decision Log (Architectural)
- **Daemonization**: Approved for performance (Cold < 200ms, Cached < 50ms).
- **Conflict Resolution**: Manual LLM merge using `version_hash` (Optimistic Locking).
- **Context Discovery**: Synchronous on cache miss with background refresh.
