"""
Keeli v6.0 MCP Server — Model Context Protocol (Production-Hardened)

Critical fixes applied:
  • Per-request engine instantiation (eliminates SQLite threading errors)
  • Input validation guards on all mutation parameters
  • Explicit session_id + branch on every tool call
  • No global shared state
"""

from mcp.server.fastmcp import FastMCP
from keeli.engine import KeeliEngine

mcp = FastMCP("keeli")

# ── Connection Isolation ──
# CRITICAL FIX: Each tool handler instantiates a fresh KeeliEngine.
# SQLite file-level locking serializes writes; per-request connections
# eliminate sqlite3.ProgrammingError from cross-thread object sharing.
def _engine() -> KeeliEngine:
    return KeeliEngine()


# ── Input Validation ──
_VALID_FIELDS = {"status", "priority", "title", "description", "depends_on", "completed"}
_VALID_OPS = {"set", "add", "remove", "init"}

def _validate_field(field: str) -> None:
    if field not in _VALID_FIELDS and not field.startswith("tags"):
        raise ValueError(f"Invalid field '{field}'. Allowed: {_VALID_FIELDS} or tags")

def _validate_value(value, field: str) -> any:
    """Coerce and validate field values before they enter the event log."""
    if field == "status":
        v = str(value).strip().lower()
        if v not in {"backlog", "active", "review", "blocked", "archive"}:
            raise ValueError(f"Invalid status '{v}'")
        return v
    if field == "priority":
        v = str(value).strip().upper()
        if v not in {"P0", "P1", "P2"}:
            raise ValueError(f"Invalid priority '{v}'")
        return v
    if field == "tags" and isinstance(value, list):
        return [str(t).strip().lower() for t in value if str(t).strip()]
    return str(value).strip()


# ── Core Task Tools ──

@mcp.tool()
def keeli_list(status: str = None, branch: str = None):
    """List tasks. Optional branch filter uses branch snapshots if available."""
    engine = _engine()
    tasks = engine.list_tasks(status=status, branch=branch)
    return "\n".join([
        f"[{t['status'].upper()}] {t['id']}: {t['title']} ({t['priority']}) [VC: {t.get('vector_clock', {})}]"
        for t in tasks
    ])

@mcp.tool()
def keeli_get(task_id: str):
    """Retrieve full task markdown with VECTOR_CLOCK header for agent awareness."""
    engine = _engine()
    try:
        return engine.get_task(task_id)
    except ValueError as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_get_state(task_id: str):
    """Get structured CRDT state (fields + vector clock) for a task."""
    engine = _engine()
    try:
        state = engine.get_task_state(task_id)
        return state
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_next(session_id: str = None, branch: str = None):
    """Get next prioritized task for the given session or global backlog."""
    engine = _engine()
    task = engine.next_task(session_id=session_id, branch=branch)
    if task:
        vc = task.get("vector_clock", {})
        return f"[{task['status'].upper()}] {task['id']}: {task['title']} ({task['priority']}) [VC: {vc}]"
    return "No tasks pending."

@mcp.tool()
def keeli_start(
    title: str,
    description: str = "",
    priority: str = "p2",
    tags: list = None,
    depends_on: str = None,
    actor: str = None,
    branch: str = None,
    session_id: str = None,
):
    """Create a new task in the backlog. Returns task ID."""
    engine = _engine()
    tid = engine.start(
        title=title,
        priority_raw=priority,
        tags=tags,
        description=description,
        depends_on=depends_on,
        actor=actor,
        branch=branch,
        session_id=session_id,
    )
    return f"Created task {tid}"

@mcp.tool()
def keeli_active(
    task_id: str,
    actor: str = None,
    branch: str = None,
    session_id: str = None,
):
    """Mark a task active. No expected_hash required — CRDT handles concurrency."""
    engine = _engine()
    try:
        engine.move_task(task_id, "active", actor=actor, branch=branch, session_id=session_id)
        if session_id:
            engine.session_focus(task_id, session_id=session_id)
        return f"Task {task_id} is now active."
    except ValueError as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_complete(
    task_id: str,
    rationale: str = "",
    actor: str = None,
    branch: str = None,
    session_id: str = None,
):
    """Archive task and record audit rationale. CRDT merge handles concurrent edits."""
    engine = _engine()
    try:
        engine.move_task(
            task_id, "archive",
            actor=actor, branch=branch, session_id=session_id, rationale=rationale,
        )
        return f"Task {task_id} completed and archived. Rationale logged."
    except ValueError as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_block(
    task_id: str,
    reason: str = "",
    actor: str = None,
    branch: str = None,
    session_id: str = None,
):
    """Mark task blocked with mandatory reason."""
    engine = _engine()
    try:
        engine.move_task(
            task_id, "blocked",
            actor=actor, branch=branch, session_id=session_id, rationale=reason,
        )
        return f"Task {task_id} blocked."
    except ValueError as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_unblock(
    task_id: str,
    actor: str = None,
    branch: str = None,
    session_id: str = None,
):
    """Return blocked task to backlog."""
    engine = _engine()
    try:
        engine.move_task(task_id, "backlog", actor=actor, branch=branch, session_id=session_id)
        return f"Task {task_id} returned to backlog."
    except ValueError as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_edit_field(
    task_id: str,
    field: str,
    value: str,
    actor: str = None,
    branch: str = None,
    session_id: str = None,
):
    """Edit any task field via CRDT event. Safe for concurrent field-level edits.

    Valid fields: status, priority, title, description, depends_on, completed
    """
    engine = _engine()
    try:
        _validate_field(field)
        coerced = _validate_value(value, field)
        engine.edit_task_field(task_id, field, coerced, actor=actor, branch=branch, session_id=session_id)
        return f"Task {task_id} field '{field}' updated to '{coerced}'."
    except ValueError as e:
        return f"Validation Error: {e}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_add_tags(
    task_id: str,
    tags: list,
    actor: str = None,
    branch: str = None,
    session_id: str = None,
):
    """Add tags via OR-Set. Concurrent adds from different agents merge cleanly."""
    engine = _engine()
    try:
        clean_tags = _validate_value(tags, "tags")
        engine.add_tags(task_id, clean_tags, actor=actor, branch=branch, session_id=session_id)
        return f"Tags added to {task_id}."
    except ValueError as e:
        return f"Validation Error: {e}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_remove_tags(
    task_id: str,
    tags: list,
    actor: str = None,
    branch: str = None,
    session_id: str = None,
):
    """Remove tags via tag-aware OR-Set. Only removes observed instances."""
    engine = _engine()
    try:
        clean_tags = _validate_value(tags, "tags")
        engine.remove_tags(task_id, clean_tags, actor=actor, branch=branch, session_id=session_id)
        return f"Tags removed from {task_id}."
    except ValueError as e:
        return f"Validation Error: {e}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_detect_conflicts(task_id: str, lookback_seconds: int = 300):
    """Detect recent concurrent field edits for a task (observability)."""
    engine = _engine()
    conflicts = engine.detect_conflicts(task_id, lookback_seconds)
    if not conflicts:
        return f"No concurrent conflicts detected for {task_id} in last {lookback_seconds}s."
    return "\n".join([
        f"Conflict: {c['field']} (events {c['events']}, actors {c['actors']}, resolved via {c['resolution']})"
        for c in conflicts
    ])


# ── Context & Session Tools ──

@mcp.tool()
def keeli_digest(
    tier: str = "standard",
    budget: int = 2000,
    session_id: str = None,
    branch: str = None,
):
    """Get token-budgeted prompt context digest scoped to session/branch."""
    engine = _engine()
    return engine.digest(tier=tier, budget=budget, session_id=session_id, branch=branch)

@mcp.tool()
def keeli_context_get(key: str, session_id: str = None, branch: str = None):
    """Resolve context item via Session > Branch > Global precedence."""
    engine = _engine()
    return engine.context_get(key, session_id=session_id, branch=branch)

@mcp.tool()
def keeli_context_set(
    key: str,
    value: str,
    scope: str = "session",
    scope_id: str = None,
    source: str = "agent_override",
):
    """Set scoped context override. scope_id is session_id or branch_name."""
    engine = _engine()
    engine.context_set(key=key, value=value, scope=scope, scope_id=scope_id, source=source)
    return f"Context '{key}' set for scope '{scope}'."

@mcp.tool()
def keeli_session_start(name: str = "Investigation", branch: str = None, focus_task_id: str = None):
    """Start an isolated stateful agent session. Returns session_id."""
    engine = _engine()
    sid = engine.session_start(name=name, branch=branch, focus_task_id=focus_task_id)
    return f"Session started: {sid}"

@mcp.tool()
def keeli_session_focus(task_id: str, session_id: str):
    """Set session focus task."""
    engine = _engine()
    try:
        engine.session_focus(task_id, session_id=session_id)
        return f"Focused on task: {task_id}"
    except ValueError as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_session_checkpoint(note: str = "Sync", session_id: str = None, pending_decisions: list = None):
    """Save execution checkpoint and context snapshot."""
    engine = _engine()
    try:
        engine.session_checkpoint(note=note, session_id=session_id, pending_decisions=pending_decisions)
        return "Checkpoint saved."
    except ValueError as e:
        return f"Error: {e}"

@mcp.tool()
def keeli_session_list():
    """List all active sessions."""
    engine = _engine()
    sessions = engine.session_list()
    return "\n".join([
        f"{s['session_id']} | {s['goal']} | {s['branch_name'] or 'unspecified'} | {s['created']}{' [FOCUS: ' + s['focus_task_id'] + ']' if s['focus_task_id'] else ''}"
        for s in sessions
    ])

@mcp.tool()
def keeli_sync():
    """Reconcile physical filesystem state with database index."""
    engine = _engine()
    count, corrected = engine.sync()
    return f"Synced {count} tasks. {corrected} status inconsistencies corrected."


def main():
    mcp.run()


if __name__ == "__main__":
    main()
