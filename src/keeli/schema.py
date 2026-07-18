"""
SQLite schema definitions for Keeli v4.0.
"""

import sqlite3
from pathlib import Path

def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the Keeli state database with the v4.0 schema."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    # Enable WAL mode for better concurrency and set busy timeout
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    
    # Task table (rebuildable from files)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_index (
            id TEXT PRIMARY KEY,          -- T-0001
            slug TEXT NOT NULL,            -- fix-auth
            title TEXT NOT NULL,
            status TEXT NOT NULL,          -- backlog, active, review, blocked, archive
            priority TEXT,                 -- P0, P1, P2
            created TEXT,                  -- ISO timestamp
            tags TEXT,                     -- comma-separated: "security:auth,type:bugfix"
            path TEXT NOT NULL,            -- docs/tasks/active/T-0001-fix-auth.md
            version_hash TEXT,             -- Optimistic locking
            updated TEXT                   -- last sync timestamp
        )
    """)
    
    # Sessions (Conversation threads)
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

    # Context Store (Global > Branch > Session)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS context_store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            scope TEXT NOT NULL,           -- global, branch, session
            scope_id TEXT,                 -- NULL for global, else branch name or session_id
            source TEXT,                   -- pyproject.toml, user_override, etc.
            updated TEXT NOT NULL
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_context_lookup ON context_store (key, scope, scope_id) WHERE scope != 'global'")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_context_global ON context_store (key) WHERE scope = 'global'")

    # Checkpoints
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

    # Working Memory
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

    # Audit table (append-only)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT,                   -- T-0001
            session_id TEXT,               -- RFC v5.0
            action TEXT NOT NULL,           -- start, progress, complete, log, sync
            actor TEXT NOT NULL,            -- developer, system, agent, git, username
            details TEXT,                   -- "Fixed JWT validation"
            rationale TEXT,                 -- RFC v5.0
            created TEXT NOT NULL           -- ISO timestamp
        )
    """)
    
    # FTS5 (Virtual Table)
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS task_fts USING fts5(task_id UNINDEXED, title, description, tags, content=task_index)")
    except sqlite3.OperationalError:
        # FTS5 might not be available in all sqlite environments
        pass

    
    conn.commit()
    return conn
