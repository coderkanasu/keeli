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
            updated TEXT                   -- last sync timestamp
        )
    """)
    
    # Audit table (append-only)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT,                   -- T-0001 (NULL for system events)
            action TEXT NOT NULL,           -- start, progress, complete, log, sync
            actor TEXT NOT NULL,            -- developer, system, agent, git, username
            details TEXT,                   -- "Fixed JWT validation"
            created TEXT NOT NULL           -- ISO timestamp
        )
    """)
    
    conn.commit()
    return conn
