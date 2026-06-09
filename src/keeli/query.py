"""
Query layer for Keeli state database.

Provides fast read operations for LLM consumption.
"""

import contextlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from keeli.main import _connect_state_db, _state_db_path
from keeli import tags as tag_utils


def query_task_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    """Get a single task by ID."""
    if not _state_db_path().exists():
        return None
    
    with contextlib.closing(_connect_state_db()) as conn:
        row = conn.execute(
            """
            SELECT * FROM work_items 
            WHERE item_id = ? AND archived = 0
            """,
            (task_id,)
        ).fetchone()
        
        if not row:
            return None
        
        return _row_to_dict(row)


def query_task_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get a single task by slug."""
    if not _state_db_path().exists():
        return None
    
    with contextlib.closing(_connect_state_db()) as conn:
        row = conn.execute(
            """
            SELECT * FROM work_items 
            WHERE slug = ? AND archived = 0
            """,
            (slug,)
        ).fetchone()
        
        if not row:
            return None
        
        return _row_to_dict(row)


def query_tasks(
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[List[str]] = None,
    requires_skills: Optional[List[str]] = None,
    epic_slug: Optional[str] = None,
    story_slug: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Query tasks with filters.
    
    Args:
        status: Filter by status (Backlog, In Progress, Done, Blocked)
        priority: Filter by priority (P0, P1, P2)
        tags: Filter tasks containing ANY of these tags
        requires_skills: Filter tasks requiring ANY of these skills
        epic_slug: Filter by epic
        story_slug: Filter by story
        limit: Max results (default 50)
        offset: Pagination offset (default 0)
    
    Returns:
        List of task dictionaries
    """
    if not _state_db_path().exists():
        return []
    
    conditions = ["archived = 0"]
    params = []
    
    if status:
        conditions.append("status = ?")
        params.append(status)
    
    if priority:
        conditions.append("priority = ?")
        params.append(priority)
    
    if epic_slug:
        conditions.append("epic_slug = ?")
        params.append(epic_slug)
    
    if story_slug:
        conditions.append("story_slug = ?")
        params.append(story_slug)
    
    # For tags and skills, we need to use JSON queries (SQLite 3.38+)
    if tags:
        # Match if ANY tag matches
        tag_conditions = " OR ".join(
            f"EXISTS (SELECT 1 FROM json_each(tags) WHERE value = ?)"
            for _ in tags
        )
        conditions.append(f"({tag_conditions})")
        params.extend(tags)
    
    if requires_skills:
        # Match if ANY skill matches
        skill_conditions = " OR ".join(
            f"EXISTS (SELECT 1 FROM json_each(requires_skills) WHERE value = ?)"
            for _ in requires_skills
        )
        conditions.append(f"({skill_conditions})")
        params.extend(requires_skills)
    
    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT * FROM work_items 
        WHERE {where_clause}
        ORDER BY 
            CASE priority 
                WHEN 'P0' THEN 0 
                WHEN 'P1' THEN 1 
                WHEN 'P2' THEN 2 
                ELSE 3 
            END,
            created_at ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    
    with contextlib.closing(_connect_state_db()) as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]


def search_tasks(query_text: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Full-text search across task titles and context notes.
    
    Args:
        query_text: Search text
        limit: Max results (default 20)
    
    Returns:
        List of matching task dictionaries
    """
    if not _state_db_path().exists():
        return []
    
    # Simple LIKE search (can be upgraded to FTS5 later)
    search_pattern = f"%{query_text}%"
    
    with contextlib.closing(_connect_state_db()) as conn:
        rows = conn.execute(
            """
            SELECT * FROM work_items 
            WHERE archived = 0 
              AND (title LIKE ? OR context_note LIKE ?)
            ORDER BY 
                CASE priority 
                    WHEN 'P0' THEN 0 
                    WHEN 'P1' THEN 1 
                    WHEN 'P2' THEN 2 
                    ELSE 3 
                END,
                created_at ASC
            LIMIT ?
            """,
            (search_pattern, search_pattern, limit)
        ).fetchall()
        
        return [_row_to_dict(row) for row in rows]


def count_tasks(
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> int:
    """Count tasks matching filters."""
    if not _state_db_path().exists():
        return 0
    
    conditions = ["archived = 0"]
    params = []
    
    if status:
        conditions.append("status = ?")
        params.append(status)
    
    if priority:
        conditions.append("priority = ?")
        params.append(priority)
    
    if tags:
        tag_conditions = " OR ".join(
            f"EXISTS (SELECT 1 FROM json_each(tags) WHERE value = ?)"
            for _ in tags
        )
        conditions.append(f"({tag_conditions})")
        params.extend(tags)
    
    where_clause = " AND ".join(conditions)
    
    with contextlib.closing(_connect_state_db()) as conn:
        row = conn.execute(
            f"SELECT COUNT(*) as count FROM work_items WHERE {where_clause}",
            params
        ).fetchone()
        
        return row["count"] if row else 0


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert SQLite row to dictionary with parsed JSON fields."""
    result = dict(row)
    
    # Parse JSON arrays
    if "tags" in result and result["tags"]:
        result["tags"] = tag_utils.parse_tags(result["tags"])
    else:
        result["tags"] = []
    
    if "requires_skills" in result and result["requires_skills"]:
        result["requires_skills"] = tag_utils.parse_tags(result["requires_skills"])
    else:
        result["requires_skills"] = []
    
    if "affects" in result and result["affects"]:
        result["affects"] = tag_utils.parse_tags(result["affects"])
    else:
        result["affects"] = []
    
    # Convert archived int to bool
    if "archived" in result:
        result["archived"] = bool(result["archived"])
    
    return result


# ── Write Operations ──────────────────────────────────────────────────────────


def batch_update_status(
    task_ids: List[str],
    new_status: str,
    actor: str = "mcp",
) -> Dict[str, Any]:
    """
    Update status for multiple tasks in a single transaction.
    
    Args:
        task_ids: List of task IDs or slugs to update
        new_status: New status (Backlog, In Progress, Done, Blocked)
        actor: Actor performing the update (for audit log)
    
    Returns:
        Dictionary with success/failure counts and details
    """
    if not _state_db_path().exists():
        return {"success": 0, "failed": 0, "errors": ["Database not found"]}
    
    from keeli.main import _now_iso, _db_log_event
    
    results = {"success": 0, "failed": 0, "updated": [], "errors": []}
    
    with contextlib.closing(_connect_state_db()) as conn:
        for task_id in task_ids:
            try:
                # Try ID first, then slug
                cursor = conn.execute(
                    """
                    UPDATE work_items 
                    SET status = ?, updated_at = ?, version = version + 1
                    WHERE (item_id = ? OR slug = ?) AND archived = 0
                    """,
                    (new_status, _now_iso(), task_id, task_id)
                )
                
                if cursor.rowcount > 0:
                    results["success"] += 1
                    results["updated"].append(task_id)
                    # Log event
                    _db_log_event(task_id, f"status_changed:{new_status}", actor=actor, details=f"Batch update to {new_status}")
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Task '{task_id}' not found")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Task '{task_id}': {str(e)}")
        
        conn.commit()
    
    return results


def add_tags_to_task(
    task_id: str,
    tags_to_add: List[str],
    actor: str = "mcp",
) -> Dict[str, Any]:
    """
    Add tags to a task without replacing existing tags.
    
    Args:
        task_id: Task ID or slug
        tags_to_add: Tags to add
        actor: Actor performing the update
    
    Returns:
        Dictionary with updated tags and success status
    """
    if not _state_db_path().exists():
        return {"success": False, "error": "Database not found"}
    
    from keeli.main import _now_iso, _db_log_event
    
    with contextlib.closing(_connect_state_db()) as conn:
        # Get current tags
        row = conn.execute(
            "SELECT item_id, tags, version FROM work_items WHERE (item_id = ? OR slug = ?) AND archived = 0",
            (task_id, task_id)
        ).fetchone()
        
        if not row:
            return {"success": False, "error": f"Task '{task_id}' not found"}
        
        current_tags = tag_utils.parse_tags(row["tags"])
        task_id_resolved = row["item_id"]
        current_version = row["version"]
        
        # Add new tags (deduplicate)
        updated_tags = list(set(current_tags + [t.strip().lower() for t in tags_to_add]))
        tags_json = tag_utils.serialize_tags(updated_tags)
        
        # Update with optimistic locking
        cursor = conn.execute(
            """
            UPDATE work_items 
            SET tags = ?, updated_at = ?, version = version + 1
            WHERE item_id = ? AND version = ?
            """,
            (tags_json, _now_iso(), task_id_resolved, current_version)
        )
        
        if cursor.rowcount == 0:
            return {"success": False, "error": "Concurrent modification detected, retry"}
        
        conn.commit()
        
        # Log event
        _db_log_event(task_id_resolved, "tags_added", actor=actor, details=f"Added: {', '.join(tags_to_add)}")
        
        return {
            "success": True,
            "task_id": task_id_resolved,
            "tags": updated_tags,
            "added": tags_to_add,
        }


def remove_tags_from_task(
    task_id: str,
    tags_to_remove: List[str],
    actor: str = "mcp",
) -> Dict[str, Any]:
    """
    Remove tags from a task.
    
    Args:
        task_id: Task ID or slug
        tags_to_remove: Tags to remove
        actor: Actor performing the update
    
    Returns:
        Dictionary with updated tags and success status
    """
    if not _state_db_path().exists():
        return {"success": False, "error": "Database not found"}
    
    from keeli.main import _now_iso, _db_log_event
    
    with contextlib.closing(_connect_state_db()) as conn:
        # Get current tags
        row = conn.execute(
            "SELECT item_id, tags, version FROM work_items WHERE (item_id = ? OR slug = ?) AND archived = 0",
            (task_id, task_id)
        ).fetchone()
        
        if not row:
            return {"success": False, "error": f"Task '{task_id}' not found"}
        
        current_tags = tag_utils.parse_tags(row["tags"])
        task_id_resolved = row["item_id"]
        current_version = row["version"]
        
        # Remove tags
        tags_to_remove_normalized = [t.strip().lower() for t in tags_to_remove]
        updated_tags = [t for t in current_tags if t not in tags_to_remove_normalized]
        tags_json = tag_utils.serialize_tags(updated_tags)
        
        # Update with optimistic locking
        cursor = conn.execute(
            """
            UPDATE work_items 
            SET tags = ?, updated_at = ?, version = version + 1
            WHERE item_id = ? AND version = ?
            """,
            (tags_json, _now_iso(), task_id_resolved, current_version)
        )
        
        if cursor.rowcount == 0:
            return {"success": False, "error": "Concurrent modification detected, retry"}
        
        conn.commit()
        
        # Log event
        _db_log_event(task_id_resolved, "tags_removed", actor=actor, details=f"Removed: {', '.join(tags_to_remove)}")
        
        return {
            "success": True,
            "task_id": task_id_resolved,
            "tags": updated_tags,
            "removed": tags_to_remove,
        }


def get_task_history(task_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get audit history for a task.
    
    Args:
        task_id: Task ID or slug
        limit: Max events to return
    
    Returns:
        List of audit events
    """
    if not _state_db_path().exists():
        return []
    
    with contextlib.closing(_connect_state_db()) as conn:
        # Resolve task_id
        row = conn.execute(
            "SELECT item_id FROM work_items WHERE item_id = ? OR slug = ?",
            (task_id, task_id)
        ).fetchone()
        
        if not row:
            return []
        
        task_id_resolved = row["item_id"]
        
        # Get audit events
        rows = conn.execute(
            """
            SELECT id, item_id, actor, action, details, created_at
            FROM audit_events
            WHERE item_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (task_id_resolved, limit)
        ).fetchall()
        
        return [dict(row) for row in rows]


def rollback_task(task_id: str, target_version: int) -> Dict[str, Any]:
    """
    Rollback a task to a previous version.
    
    Note: This is a placeholder - full rollback requires storing version snapshots.
    Current implementation only validates version numbers.
    
    Args:
        task_id: Task ID or slug
        target_version: Version to roll back to
    
    Returns:
        Dictionary with rollback status
    """
    if not _state_db_path().exists():
        return {"success": False, "error": "Database not found"}
    
    with contextlib.closing(_connect_state_db()) as conn:
        row = conn.execute(
            "SELECT item_id, version FROM work_items WHERE (item_id = ? OR slug = ?) AND archived = 0",
            (task_id, task_id)
        ).fetchone()
        
        if not row:
            return {"success": False, "error": f"Task '{task_id}' not found"}
        
        current_version = row["version"]
        task_id_resolved = row["item_id"]
        
        if target_version >= current_version:
            return {
                "success": False,
                "error": f"Target version {target_version} must be less than current version {current_version}"
            }
        
        # TODO: Implement version snapshot storage and restore
        # For now, just return metadata
        return {
            "success": False,
            "error": "Rollback not yet implemented - requires version snapshot storage",
            "task_id": task_id_resolved,
            "current_version": current_version,
            "target_version": target_version,
            "note": "Version column is ready, but snapshot storage needs implementation"
        }
