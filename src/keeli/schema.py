"""
SQLite schema definitions and migrations for Keeli state database.

Schema versioning:
- v1: Initial schema with personas
- v2: Deprecate personas, add tags/requires_skills, add version column for optimistic locking
"""

import contextlib
import sqlite3
from pathlib import Path
from typing import Callable


# Current schema version
CURRENT_SCHEMA_VERSION = 2


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version from database."""
    try:
        cursor = conn.execute("SELECT value FROM state_meta WHERE key = 'schema_version'")
        row = cursor.fetchone()
        if not row:
            return 0
        # Handle legacy version strings (e.g., "0.4.2") by checking for integer
        value = row[0]
        try:
            return int(value)
        except ValueError:
            # Legacy version string detected, treat as v1
            return 1 if value else 0
    except sqlite3.OperationalError:
        return 0


def init_schema_v1(conn: sqlite3.Connection) -> None:
    """Initialize v1 schema (legacy with personas)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS state_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_items (
            item_id TEXT PRIMARY KEY,
            item_type TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            epic_slug TEXT,
            story_slug TEXT,
            persona TEXT,
            context_note TEXT,
            depends_on TEXT,
            source_path TEXT,
            created_at TEXT,
            completed_at TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
        CREATE INDEX IF NOT EXISTS idx_work_items_priority ON work_items(priority);
        CREATE INDEX IF NOT EXISTS idx_work_items_epic_slug ON work_items(epic_slug);
        CREATE INDEX IF NOT EXISTS idx_work_items_story_slug ON work_items(story_slug);
        CREATE INDEX IF NOT EXISTS idx_work_items_archived ON work_items(archived);

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT,
            actor TEXT,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_item_id ON audit_events(item_id);
        CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_events(created_at);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO state_meta(key, value) VALUES (?, ?)",
        ("schema_version", "1"),
    )
    conn.commit()


def migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """
    Migrate from v1 to v2: Deprecate personas, add tags/requires_skills, add versioning.
    
    Changes:
    - Add tags TEXT (JSON array) to work_items
    - Add requires_skills TEXT (JSON array) to work_items
    - Add version INTEGER for optimistic locking
    - Mark persona as deprecated (keep for backward compat)
    - Migrate existing persona values to tags
    """
    conn.executescript(
        """
        -- Add new columns
        ALTER TABLE work_items ADD COLUMN tags TEXT DEFAULT '[]';
        ALTER TABLE work_items ADD COLUMN requires_skills TEXT DEFAULT '[]';
        ALTER TABLE work_items ADD COLUMN version INTEGER DEFAULT 1;
        ALTER TABLE work_items ADD COLUMN affects TEXT DEFAULT '[]';
        
        -- Create index on tags for fast filtering
        CREATE INDEX IF NOT EXISTS idx_work_items_tags ON work_items(tags);
        
        -- Migrate persona to tags (if persona is set)
        UPDATE work_items 
        SET tags = json_array('persona:' || persona)
        WHERE persona IS NOT NULL AND persona != '';
        
        -- Update schema version
        UPDATE state_meta SET value = '2' WHERE key = 'schema_version';
        """
    )
    conn.commit()


# Migration map: version -> migration function
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: init_schema_v1,
    2: migrate_v1_to_v2,
}


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations to bring database to current schema version."""
    current_version = get_schema_version(conn)
    
    if current_version == 0:
        # Fresh database, apply latest schema directly
        init_schema_v1(conn)
        current_version = 1
    
    # Apply incremental migrations
    while current_version < CURRENT_SCHEMA_VERSION:
        next_version = current_version + 1
        if next_version not in MIGRATIONS:
            raise ValueError(f"No migration path from version {current_version} to {next_version}")
        
        print(f"📦 Migrating database schema: v{current_version} → v{next_version}")
        MIGRATIONS[next_version](conn)
        current_version = next_version
    
    # Ensure version is recorded
    conn.execute(
        "INSERT OR REPLACE INTO state_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(CURRENT_SCHEMA_VERSION)),
    )
    conn.commit()


def init_state_db(db_path: Path) -> None:
    """Initialize or migrate the state database to current schema version."""
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        apply_migrations(conn)
