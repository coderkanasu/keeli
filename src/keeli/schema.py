"""
Keeli v6.0 — SQLite Schema for Event-Sourced CRDT Architecture.

Source of truth: append-only task_events table (CRDT event log).
Materialized views: task_index (global merged state), branch_snapshots (per-branch).
"""

import sqlite3
from pathlib import Path


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the Keeli v6.0 state database with CRDT event sourcing."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")

    # ── CRDT Event Log (Append-Only Source of Truth) ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            field TEXT NOT NULL,
            op TEXT NOT NULL CHECK(op IN ('init', 'set', 'add', 'remove')),
            value TEXT,                     -- JSON-encoded
            timestamp TEXT NOT NULL,        -- ISO-8601 UTC
            actor TEXT NOT NULL,
            branch TEXT,                    -- Git branch scope (nullable = global)
            session_id TEXT,                -- Session scope (nullable = unscoped)
            vector_clock TEXT NOT NULL,     -- JSON dict
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_task ON task_events (task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_branch ON task_events (branch)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON task_events (session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON task_events (timestamp)")

    # ── Materialized Task Index (Rebuildable from event log) ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_index (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'backlog',
            priority TEXT DEFAULT 'P2',
            created TEXT,
            tags TEXT,                      -- Comma-separated
            depends_on TEXT,
            description TEXT,
            completed TEXT,
            path TEXT,                      -- Path to materialized .md file
            updated TEXT NOT NULL,
            vector_clock TEXT NOT NULL      -- Merged vector clock
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON task_index (status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_priority ON task_index (priority)")

    # ── Branch-Specific Snapshots (isolated branch views) ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS branch_snapshots (
            branch TEXT NOT NULL,
            task_id TEXT NOT NULL,
            status TEXT,
            priority TEXT,
            title TEXT,
            tags TEXT,
            updated TEXT NOT NULL,
            vector_clock TEXT NOT NULL,
            PRIMARY KEY (branch, task_id)
        )
    """)

    # ── Sessions (Connection-Scoped, NO global active flag) ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            branch_name TEXT,
            focus_task_id TEXT REFERENCES task_index(id),
            goal TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            last_ping TEXT NOT NULL,
            created TEXT NOT NULL,
            ended TEXT
        )
    """)

    # ── Scoped Context Store (Session > Branch > Global waterfall) ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS context_store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            scope TEXT NOT NULL CHECK(scope IN ('session', 'branch', 'global')),
            scope_id TEXT,
            source TEXT,
            updated TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_context_scoped 
        ON context_store (key, scope, scope_id) WHERE scope != 'global'
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_context_global 
        ON context_store (key) WHERE scope = 'global'
    """)

    # ── Checkpoints ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            llm_summary TEXT NOT NULL,
            active_digest TEXT,
            pending_decisions TEXT,
            context_snapshot TEXT,
            created TEXT NOT NULL
        )
    """)

    # ── Working Memory (Ephemeral) ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS working_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            ttl_minutes INTEGER,
            updated TEXT NOT NULL,
            UNIQUE(session_id, key)
        )
    """)

    # ── Append-Only Audit Trail ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT,
            session_id TEXT,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            details TEXT,
            rationale TEXT,
            created TEXT NOT NULL
        )
    """)

    # ── Conflict Detection Log (for observability) ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conflict_log (
            conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            field TEXT NOT NULL,
            event_a_id INTEGER NOT NULL,
            event_b_id INTEGER NOT NULL,
            resolution TEXT NOT NULL,       -- 'lww', 'merged', 'manual'
            resolved_value TEXT,
            detected_at TEXT NOT NULL
        )
    """)

    # ── FTS5 (rebuildable from task_index) ──
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS task_fts 
            USING fts5(task_id UNINDEXED, title, description, tags, content=task_index)
        """)
    except sqlite3.OperationalError:
        pass  # FTS5 extension not available

    conn.commit()
    return conn
