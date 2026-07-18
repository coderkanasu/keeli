"""
Keeli MCP Server — Thin wrapper around Keeli CLI.
Provides task management tools to LLM agents.
"""

import os
import sys
import json
from mcp.server.fastmcp import FastMCP
from keeli.engine import KeeliEngine

# Initialize FastMCP server and Engine
mcp = FastMCP("keeli")
engine = KeeliEngine()

@mcp.tool()
def keeli_list(status: str = None):
    """List tasks, optionally filtered by status (backlog, active, review, blocked, archive)."""
    tasks = engine.list_tasks(status=status)
    return "\n".join([f"[{t['status'].upper()}] {t['id']}: {t['title']} ({t['priority']}) [Hash: {t['version_hash'][:8]}]" for t in tasks])

@mcp.tool()
def keeli_get(task_id: str):
    """Retrieve the full content of a specific task. Returns VERSION_HASH in metadata."""
    try:
        return engine.get_task(task_id)
    except ValueError as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_next():
    """Get the next recommended task to work on based on priority and age."""
    task = engine.next_task()
    if task:
        return f"[{task['status'].upper()}] {task['id']}: {task['title']} ({task['priority']}) [Hash: {task['version_hash'][:8]}]"
    return "No tasks pending."

@mcp.tool()
def keeli_start(title: str, description: str = "", priority: str = "p2", tags: list = None):
    """Create a new task in the backlog."""
    tid = engine.start(title=title, priority_raw=priority, tags=tags, description=description)
    return f"Created task {tid}"

@mcp.tool()
def keeli_active(task_id: str, expected_hash: str, session_id: str = None):
    """Mark a task as Active. REQUIRES expected_hash for optimistic locking."""
    try:
        engine.move_task(task_id, "active", expected_hash=expected_hash)
        return f"Task {task_id} is now active."
    except ValueError as e:
        return str(e)

@mcp.tool()
def keeli_complete(task_id: str, expected_hash: str, rationale: str = "", session_id: str = None):
    """Mark a task as completed. REQUIRES expected_hash and rationale."""
    try:
        engine.move_task(task_id, "archive", expected_hash=expected_hash, rationale=rationale)
        return f"Task {task_id} completed. Rationale logged."
    except ValueError as e:
        return str(e)

@mcp.tool()
def keeli_block(task_id: str, expected_hash: str, reason: str = ""):
    """Mark a task as blocked. REQUIRES expected_hash."""
    try:
        engine.move_task(task_id, "blocked", expected_hash=expected_hash, rationale=reason)
        return f"Task {task_id} blocked."
    except ValueError as e:
        return str(e)

@mcp.tool()
def keeli_unblock(task_id: str, expected_hash: str):
    """Unblock a task. REQUIRES expected_hash."""
    try:
        engine.move_task(task_id, "backlog", expected_hash=expected_hash)
        return f"Task {task_id} unblocked."
    except ValueError as e:
        return str(e)

@mcp.tool()
def keeli_digest(tier: str = "standard", budget: int = 2000):
    """Get a token-budgeted context snapshot."""
    return engine.digest(tier=tier, budget=budget)

@mcp.tool()
def keeli_session_start(name: str = "Investigation"):
    """Start a new working session."""
    sid = engine.session_start(name=name)
    return f"Session started: {sid}"

@mcp.tool()
def keeli_session_focus(task_id: str):
    """Focus the current session on a specific task."""
    try:
        engine.session_focus(task_id)
        return f"Focused on {task_id}"
    except ValueError as e:
        return str(e)

@mcp.tool()
def keeli_session_checkpoint(note: str = "Sync"):
    """Create a session checkpoint."""
    try:
        engine.session_checkpoint(note=note)
        return "Checkpoint saved."
    except ValueError as e:
        return str(e)

@mcp.tool()
def keeli_sync():
    """Manually reconcile filesystem tasks with the index."""
    count, corrected = engine.sync()
    return f"Synced {count} tasks. {corrected} corrected."

def main():
    mcp.run()

if __name__ == "__main__":
    main()

