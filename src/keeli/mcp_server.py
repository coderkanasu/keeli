"""
Keeli v6.0 MCP Server — Model Context Protocol (Production-Hardened)

Consolidated Architecture (6 Domain-Based Tools):
  • keeli_tasks: Unified task management (create, query, update, conflicts)
  • keeli_context: Context operations (get, set, digest with working memory/knowledge)
  • keeli_sessions: Session management (start, focus, checkpoint, list)
  • keeli_memory: Working memory and project analysis caching
  • keeli_knowledge: Knowledge extraction and persistent storage
  • keeli_system: System operations (sync, doctor)

Critical fixes applied:
  • Per-request engine instantiation (eliminates SQLite threading errors)
  • Input validation guards on all mutation parameters
  • Explicit session_id + branch on every tool call
  • No global shared state
  • LLM-focused context management with caching and knowledge extraction
"""

from mcp.server.fastmcp import FastMCP
from keeli.engine import KeeliEngine
import json

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


# ── Domain-Based Consolidated Tools ──

@mcp.tool()
def keeli_tasks(
    operation: str,
    task_id: str = None,
    title: str = None,
    description: str = None,
    priority: str = None,
    tags: list = None,
    depends_on: str = None,
    status: str = None,
    field: str = None,
    value: str = None,
    tag_operation: str = None,
    filters: dict = None,
    lookback_seconds: int = 300,
    actor: str = None,
    branch: str = None,
    session_id: str = None,
    rationale: str = None,
):
    """Unified task management tool consolidating all task operations.

    Operations:
    - create: Create a new task (requires title)
    - query: List tasks (optional filters: status, branch)
    - get: Get full task markdown (requires task_id)
    - get_state: Get structured CRDT state (requires task_id)
    - next: Get next prioritized task
    - update_status: Change task status (requires task_id, status)
    - update_field: Edit any task field (requires task_id, field, value)
    - update_tags: Add or remove tags (requires task_id, tags, tag_operation)
    - conflicts: Detect concurrent edits (requires task_id)

    Valid statuses: backlog, active, review, blocked, archive
    Valid fields: status, priority, title, description, depends_on, completed
    Tag operations: add, remove
    """
    engine = _engine()
    
    try:
        if operation == "create":
            if not title:
                return "Error: 'title' required for create operation"
            tid = engine.start(
                title=title,
                priority_raw=priority or "p2",
                tags=tags,
                description=description or "",
                depends_on=depends_on,
                actor=actor,
                branch=branch,
                session_id=session_id,
            )
            return f"Created task {tid}"
        
        elif operation == "query":
            filters_dict = filters or {}
            status_filter = filters_dict.get("status") or status
            branch_filter = filters_dict.get("branch") or branch
            tasks = engine.list_tasks(status=status_filter, branch=branch_filter)
            return "\n".join([
                f"[{t['status'].upper()}] {t['id']}: {t['title']} ({t['priority']}) [VC: {t.get('vector_clock', {})}]"
                for t in tasks
            ])
        
        elif operation == "get":
            if not task_id:
                return "Error: 'task_id' required for get operation"
            return engine.get_task(task_id)
        
        elif operation == "get_state":
            if not task_id:
                return "Error: 'task_id' required for get_state operation"
            state = engine.get_task_state(task_id)
            return state
        
        elif operation == "next":
            task = engine.next_task(session_id=session_id, branch=branch)
            if task:
                vc = task.get("vector_clock", {})
                return f"[{task['status'].upper()}] {task['id']}: {task['title']} ({task['priority']}) [VC: {vc}]"
            return "No tasks pending."
        
        elif operation == "update_status":
            if not task_id or not status:
                return "Error: 'task_id' and 'status' required for update_status operation"
            if status not in {"backlog", "active", "review", "blocked", "archive"}:
                return f"Error: Invalid status '{status}'. Valid: backlog, active, review, blocked, archive"
            engine.move_task(task_id, status, actor=actor, branch=branch, session_id=session_id, rationale=rationale)
            if status == "active" and session_id:
                engine.session_focus(task_id, session_id=session_id)
            return f"Task {task_id} status updated to {status}."
        
        elif operation == "update_field":
            if not task_id or not field or not value:
                return "Error: 'task_id', 'field', and 'value' required for update_field operation"
            _validate_field(field)
            coerced = _validate_value(value, field)
            engine.edit_task_field(task_id, field, coerced, actor=actor, branch=branch, session_id=session_id)
            return f"Task {task_id} field '{field}' updated to '{coerced}'."
        
        elif operation == "update_tags":
            if not task_id or not tags:
                return "Error: 'task_id' and 'tags' required for update_tags operation"
            clean_tags = _validate_value(tags, "tags")
            if tag_operation == "add":
                engine.add_tags(task_id, clean_tags, actor=actor, branch=branch, session_id=session_id)
                return f"Tags added to {task_id}."
            elif tag_operation == "remove":
                engine.remove_tags(task_id, clean_tags, actor=actor, branch=branch, session_id=session_id)
                return f"Tags removed from {task_id}."
            else:
                return "Error: 'tag_operation' must be 'add' or 'remove'"
        
        elif operation == "conflicts":
            if not task_id:
                return "Error: 'task_id' required for conflicts operation"
            conflicts = engine.detect_conflicts(task_id, lookback_seconds)
            if not conflicts:
                return f"No concurrent conflicts detected for {task_id} in last {lookback_seconds}s."
            return "\n".join([
                f"Conflict: {c['field']} (events {c['events']}, actors {c['actors']}, resolved via {c['resolution']})"
                for c in conflicts
            ])
        
        else:
            return f"Error: Unknown operation '{operation}'. Valid: create, query, get, get_state, next, update_status, update_field, update_tags, conflicts"
    
    except ValueError as e:
        return f"Validation Error: {e}"
    except Exception as e:
        return f"Error: {e}"


# ── Context Management Domain ──

@mcp.tool()
def keeli_context(
    operation: str,
    key: str = None,
    value: str = None,
    scope: str = "session",
    scope_id: str = None,
    source: str = "agent_override",
    tier: str = "standard",
    budget: int = 2000,
    session_id: str = None,
    branch: str = None,
    include_working_memory: bool = True,
    include_knowledge: bool = False,
):
    """Unified context management tool for context operations.

    Operations:
    - get: Resolve context item via Session > Branch > Global precedence (requires key)
    - set: Set scoped context override (requires key, value)
    - digest: Get token-budgeted prompt context digest scoped to session/branch

    Scopes: session, branch, global
    Tiers: nano, brief, standard, full
    Additional digest options: include_working_memory, include_knowledge
    """
    engine = _engine()
    
    try:
        if operation == "get":
            if not key:
                return "Error: 'key' required for get operation"
            # Use provided scope_id or fall back to session_id/branch parameters
            effective_scope_id = scope_id
            if scope == "session" and not effective_scope_id:
                effective_scope_id = session_id
            elif scope == "branch" and not effective_scope_id:
                effective_scope_id = branch
            return engine.context_get(key, session_id=effective_scope_id if scope == "session" else None, 
                                     branch=effective_scope_id if scope == "branch" else None)
        
        elif operation == "set":
            if not key or not value:
                return "Error: 'key' and 'value' required for set operation"
            # Use provided scope_id or fall back to session_id/branch parameters
            effective_scope_id = scope_id
            if scope == "session" and not effective_scope_id:
                effective_scope_id = session_id
            elif scope == "branch" and not effective_scope_id:
                effective_scope_id = branch
            engine.context_set(key=key, value=value, scope=scope, scope_id=effective_scope_id, source=source)
            return f"Context '{key}' set for scope '{scope}'."
        
        elif operation == "digest":
            result = engine.digest(
                tier=tier, 
                budget=budget, 
                session_id=session_id, 
                branch=branch,
                include_working_memory=include_working_memory,
                include_knowledge=include_knowledge
            )
            # Add a note about what's included
            components = []
            if include_working_memory and session_id:
                components.append("working memory")
            if include_knowledge:
                components.append("project knowledge")
            if components:
                return f"# DIGEST INCLUDES: {', '.join(components)}\n\n{result}"
            return result
        
        else:
            return f"Error: Unknown operation '{operation}'. Valid: get, set, digest"
    
    except ValueError as e:
        return f"Validation Error: {e}"
    except Exception as e:
        return f"Error: {e}"

# ── Session Management Domain ──

@mcp.tool()
def keeli_sessions(
    operation: str,
    session_id: str = None,
    name: str = "Investigation",
    focus_task_id: str = None,
    branch: str = None,
    note: str = "Sync",
    pending_decisions: list = None,
):
    """Unified session management tool for session operations.

    Operations:
    - start: Start an isolated stateful agent session (returns session_id)
    - focus: Set session focus task (requires session_id, focus_task_id)
    - checkpoint: Save execution checkpoint and context snapshot (requires session_id)
    - list: List all active sessions

    Session parameters:
    - name: Session goal/name for start operation
    - focus_task_id: Task to focus on for start/focus operations
    - branch: Git branch scope for start operation
    - note: Checkpoint note for checkpoint operation
    - pending_decisions: List of pending decisions for checkpoint operation
    """
    engine = _engine()
    
    try:
        if operation == "start":
            sid = engine.session_start(name=name, branch=branch, focus_task_id=focus_task_id)
            return f"Session started: {sid}"
        
        elif operation == "focus":
            if not session_id or not focus_task_id:
                return "Error: 'session_id' and 'focus_task_id' required for focus operation"
            engine.session_focus(task_id=focus_task_id, session_id=session_id)
            return f"Focused on task: {focus_task_id}"
        
        elif operation == "checkpoint":
            if not session_id:
                return "Error: 'session_id' required for checkpoint operation"
            engine.session_checkpoint(note=note, session_id=session_id, pending_decisions=pending_decisions)
            return "Checkpoint saved."
        
        elif operation == "list":
            sessions = engine.session_list()
            return "\n".join([
                f"{s['session_id']} | {s['goal']} | {s['branch_name'] or 'unspecified'} | {s['created']}{' [FOCUS: ' + s['focus_task_id'] + ']' if s['focus_task_id'] else ''}"
                for s in sessions
            ])
        
        else:
            return f"Error: Unknown operation '{operation}'. Valid: start, focus, checkpoint, list"
    
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"

# ── System Management Domain ──

@mcp.tool()
def keeli_system(operation: str = "sync"):
    """Unified system management tool for system operations.

    Operations:
    - sync: Reconcile physical filesystem state with database index
    - doctor: Perform health check and workspace validation

    System operations help maintain workspace integrity and consistency.
    """
    engine = _engine()
    
    try:
        if operation == "sync":
            count, corrected = engine.sync()
            return f"Synced {count} tasks. {corrected} status inconsistencies corrected."
        
        elif operation == "doctor":
            # Perform health check
            status_lines = [
                f"Root:      {engine.root_dir}",
                f"Workspace: {engine.workspace_dir} ({'OK' if engine.workspace_dir.exists() else 'MISSING'})",
                f"DB:        {engine.db_path} ({'OK' if engine.db_path.exists() else 'Missing - will initialize'})"
            ]
            
            for s, d in engine.status_dirs.items():
                status_lines.append(f"Folder {s:10}: {'OK' if d.exists() else 'MISSING'}")
            
            count, corrected = engine.sync()
            status_lines.append(f"Indexing: {count} tasks found, {corrected} corrected.")
            
            gitignore = engine.root_dir / ".gitignore"
            if gitignore.exists() and ".keeli/" in gitignore.read_text():
                status_lines.append("✅ .gitignore: .keeli/ is excluded from code indexing")
            else:
                status_lines.append("⚠️  .gitignore: .keeli/ not found — LLM tools may index task noise")
            
            return "\n".join(status_lines)
        
        else:
            return f"Error: Unknown operation '{operation}'. Valid: sync, doctor"
    
    except Exception as e:
        return f"Error: {e}"


# ── Working Memory & Project Analysis Domain ──

@mcp.tool()
def keeli_memory(
    operation: str,
    key: str = None,
    value: str = None,
    session_id: str = None,
    ttl_minutes: int = 60,
    analysis_type: str = None,
    analysis_content: str = None,
    branch: str = None,
):
    """Unified working memory and project analysis caching tool.

    Operations:
    - set: Store working memory item (requires key, value, session_id)
    - get: Retrieve working memory item (requires key, session_id)
    - delete: Delete working memory item (requires key, session_id)
    - list: List all working memory items for a session (requires session_id)
    - clear_expired: Clear expired working memory items (optional session_id)
    - save_analysis: Save project analysis for fast context retrieval (requires analysis_type, analysis_content)
    - get_analysis: Retrieve cached project analysis (requires analysis_type)
    - get_context: Get current project context (branch, session, task)

    Working memory provides fast, temporary context storage with TTL.
    Project analysis caching preserves expensive LLM analysis across sessions.
    """
    engine = _engine()
    
    try:
        if operation == "set":
            if not key or not value or not session_id:
                return "Error: 'key', 'value', and 'session_id' required for set operation"
            engine.working_memory_set(key, value, session_id, ttl_minutes)
            return f"Working memory set: {key}"
        
        elif operation == "get":
            if not key or not session_id:
                return "Error: 'key' and 'session_id' required for get operation"
            result = engine.working_memory_get(key, session_id)
            if result:
                return f"Working memory value: {result}"
            return f"No working memory found for key: {key}"
        
        elif operation == "delete":
            if not key or not session_id:
                return "Error: 'key' and 'session_id' required for delete operation"
            engine.working_memory_delete(key, session_id)
            return f"Deleted working memory: {key}"
        
        elif operation == "list":
            if not session_id:
                return "Error: 'session_id' required for list operation"
            items = engine.working_memory_list(session_id)
            if not items:
                return "No working memory items found"
            return "\n".join([
                f"- {item['key']}: {item['value'][:100]}{'...' if len(item['value']) > 100 else ''} (TTL: {item['ttl_minutes']}m)"
                for item in items
            ])
        
        elif operation == "clear_expired":
            cleared = engine.working_memory_clear_expired(session_id)
            return f"Cleared {cleared} expired working memory items"
        
        elif operation == "save_analysis":
            if not analysis_type or not analysis_content:
                return "Error: 'analysis_type' and 'analysis_content' required for save_analysis operation"
            return engine.save_project_analysis(analysis_type, analysis_content, session_id, branch)
        
        elif operation == "get_analysis":
            if not analysis_type:
                return "Error: 'analysis_type' required for get_analysis operation"
            result = engine.get_project_analysis(analysis_type, session_id, branch)
            if result:
                return f"Cached analysis: {result}"
            return f"No cached analysis found for type: {analysis_type}"
        
        elif operation == "get_context":
            context = engine.get_project_context()
            return json.dumps(context, indent=2)
        
        else:
            return f"Error: Unknown operation '{operation}'. Valid: set, get, delete, list, clear_expired, save_analysis, get_analysis, get_context"
    
    except Exception as e:
        return f"Error: {e}"


# ── Knowledge Management Domain ──

@mcp.tool()
def keeli_knowledge(
    operation: str,
    knowledge_type: str = None,
    content: str = None,
    source_session: str = None,
    tags: list = None,
    branch: str = None,
    session_id: str = None,
):
    """Unified knowledge management tool for extracting and storing project insights.

    Operations:
    - save: Save knowledge as persistent project insight (requires knowledge_type, content)
    - get: Retrieve knowledge by type (optional knowledge_type filter)
    - extract: Extract knowledge from a session (requires session_id)
    - list: List all available knowledge types

    Knowledge management preserves valuable insights across sessions and projects.
    Extracted knowledge can be retrieved and summarized for new LLM interactions.
    """
    engine = _engine()
    
    try:
        if operation == "save":
            if not knowledge_type or not content:
                return "Error: 'knowledge_type' and 'content' required for save operation"
            return engine.save_project_knowledge(knowledge_type, content, source_session, tags, branch)
        
        elif operation == "get":
            knowledge = engine.get_project_knowledge(knowledge_type)
            if not knowledge:
                return "No knowledge found"
            if knowledge_type:
                return f"Knowledge ({knowledge_type}): {knowledge[0]['content']}"
            return "\n".join([
                f"- {k['type']}: {k['content'][:100]}{'...' if len(k['content']) > 100 else ''} (from: {k['source']})"
                for k in knowledge
            ])
        
        elif operation == "extract":
            if not session_id:
                return "Error: 'session_id' required for extract operation"
            knowledge = engine.extract_knowledge_from_session(session_id)
            return json.dumps(knowledge, indent=2)
        
        elif operation == "list":
            knowledge = engine.get_project_knowledge()
            if not knowledge:
                return "No knowledge types available"
            return "\n".join([f"- {k['type']}" for k in knowledge])
        
        else:
            return f"Error: Unknown operation '{operation}'. Valid: save, get, extract, list"
    
    except Exception as e:
        return f"Error: {e}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
