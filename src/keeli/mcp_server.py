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
import re
import sqlite3
import time
import os
from datetime import datetime, timezone
from pathlib import Path

mcp = FastMCP("keeli")

# ── Connection Isolation ──
# CRITICAL FIX: Each tool handler instantiates a fresh KeeliEngine.
# SQLite file-level locking serializes writes; per-request connections
# eliminate sqlite3.ProgrammingError from cross-thread object sharing.
def _engine() -> KeeliEngine:
    return KeeliEngine(root_dir=_resolve_project_root())


def _resolve_project_root() -> Path:
    """Resolve a deterministic project root for MCP operations.

    Priority:
    1. KEELI_ROOT if explicitly set
    2. Current working directory when it looks like a repo/workspace
    3. Source checkout root when running from repository source
    4. Fallback to current working directory
    """
    env_root = os.getenv("KEELI_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    cwd = Path.cwd().resolve()
    if (cwd / ".git").exists() or (cwd / "setup.py").exists() or (cwd / ".keeli").exists():
        return cwd

    source_root = Path(__file__).resolve().parents[2]
    if (source_root / ".git").exists() and (source_root / "setup.py").exists():
        return source_root

    return cwd


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _response(
    ok: bool,
    tool: str,
    operation: str,
    engine: KeeliEngine,
    data=None,
    error: str = None,
    code: str = None,
    session_id: str = None,
    branch: str = None,
    actor: str = None,
    next_action: str = None,
):
    """Unified LLM-facing response envelope for all MCP tools."""
    payload = {
        "ok": ok,
        "tool": tool,
        "operation": operation,
        "timestamp": _now_iso(),
        "project": {
            "name": engine.root_dir.name,
            "root": str(engine.root_dir),
            "workspace": str(engine.workspace_dir),
        },
        "scope": {
            "branch": branch or engine._get_current_branch(),
            "session_id": session_id,
            "actor": actor,
        },
        "data": data,
    }
    if error is not None:
        payload["error"] = {"code": code or "error", "message": error}
    if next_action:
        payload["next_action"] = next_action
    return json.dumps(payload, indent=2)


def _is_lock_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return isinstance(exc, sqlite3.OperationalError) and "database is locked" in msg


def _retry_on_lock(func, attempts: int = 5, base_delay: float = 0.15):
    """Retry short-lived SQLite lock errors with exponential backoff."""
    last_exc = None
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:
            if not _is_lock_error(exc):
                raise
            last_exc = exc
            if attempt == attempts - 1:
                break
            time.sleep(base_delay * (2 ** attempt))
    raise last_exc


def _resolve_session_for_scope(engine: KeeliEngine, branch: str = None, author: str = None) -> str:
    """Resolve the best session for project+branch+author scope when session_id is absent.

    Strategy:
    1) If author + branch provided: choose most recent session on branch with audit by actor.
    2) If branch provided: choose most recent session on that branch.
    3) Fallback: most recent session overall.
    """
    if author and branch:
        row = engine.conn.execute(
            """SELECT s.session_id
               FROM sessions s
               JOIN audit a ON a.session_id = s.session_id
               WHERE s.branch_name = ? AND a.actor = ?
               ORDER BY a.created DESC
               LIMIT 1""",
            (branch, author),
        ).fetchone()
        if row:
            return row["session_id"]

    if branch:
        row = engine.conn.execute(
            "SELECT session_id FROM sessions WHERE branch_name = ? ORDER BY created DESC LIMIT 1",
            (branch,),
        ).fetchone()
        if row:
            return row["session_id"]

    row = engine.conn.execute(
        "SELECT session_id FROM sessions ORDER BY created DESC LIMIT 1"
    ).fetchone()
    return row["session_id"] if row else None


# ── Input Validation ──
_VALID_FIELDS = {"status", "priority", "title", "description", "depends_on", "completed"}
_VALID_OPS = {"set", "add", "remove", "init"}
_TAG_SCHEMA_PREFIXES = {"domain", "area", "risk", "state"}
_TAG_SCHEMA_VALUE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

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


def _normalize_and_validate_tags(tags: list) -> list:
    """Validate tags against the enforced schema: prefix:value."""
    normalized = []
    invalid = []

    for raw in tags or []:
        tag = str(raw).strip().lower()
        if not tag:
            continue

        if ":" not in tag:
            invalid.append(tag)
            continue

        prefix, value = tag.split(":", 1)
        if prefix not in _TAG_SCHEMA_PREFIXES or not _TAG_SCHEMA_VALUE_RE.match(value):
            invalid.append(tag)
            continue

        normalized.append(f"{prefix}:{value}")

    if invalid:
        allowed = ", ".join(sorted(_TAG_SCHEMA_PREFIXES))
        raise ValueError(
            "Invalid tag(s): "
            + ", ".join(invalid)
            + f". Tags must follow schema '<prefix>:<value>' with prefix in {{{allowed}}}."
        )

    return normalized


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
    def _run():
        engine = _engine()
        if operation == "create":
            if not title:
                return _response(False, "keeli_tasks", operation, engine, error="'title' required for create operation", code="missing_title")
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
            task_state = engine.get_task_state(tid)
            return _response(
                True,
                "keeli_tasks",
                operation,
                engine,
                data={"task_id": tid, "task": task_state},
                session_id=session_id,
                branch=branch,
                actor=actor,
                next_action="Use keeli_tasks operation update_status with status active when work begins.",
            )
        
        elif operation == "query":
            filters_dict = filters or {}
            status_filter = filters_dict.get("status") or status
            branch_filter = filters_dict.get("branch") or branch
            tags_filter = filters_dict.get("tags")
            tag_match = filters_dict.get("tag_match", "any")
            if tags_filter is not None:
                tags_filter = _normalize_and_validate_tags(tags_filter)

            tasks = engine.list_tasks(
                status=status_filter,
                branch=branch_filter,
                tags=tags_filter,
                tag_match=tag_match,
            )
            return _response(
                True,
                "keeli_tasks",
                operation,
                engine,
                data={"count": len(tasks), "tasks": tasks, "filters": {"status": status_filter, "branch": branch_filter, "tags": tags_filter, "tag_match": tag_match}},
                session_id=session_id,
                branch=branch_filter,
                actor=actor,
            )
        
        elif operation == "get":
            if not task_id:
                return _response(False, "keeli_tasks", operation, engine, error="'task_id' required for get operation", code="missing_task_id")
            markdown = engine.get_task(task_id)
            state = engine.get_task_state(task_id)
            return _response(
                True,
                "keeli_tasks",
                operation,
                engine,
                data={"task_id": task_id, "state": state, "markdown": markdown},
                session_id=session_id,
                branch=branch,
                actor=actor,
            )
        
        elif operation == "get_state":
            if not task_id:
                return _response(False, "keeli_tasks", operation, engine, error="'task_id' required for get_state operation", code="missing_task_id")
            state = engine.get_task_state(task_id)
            return _response(
                True,
                "keeli_tasks",
                operation,
                engine,
                data={"task_id": task_id, "state": state},
                session_id=session_id,
                branch=branch,
                actor=actor,
            )
        
        elif operation == "next":
            task = engine.next_task(session_id=session_id, branch=branch)
            return _response(
                True,
                "keeli_tasks",
                operation,
                engine,
                data={"task": task, "has_pending": task is not None},
                session_id=session_id,
                branch=branch,
                actor=actor,
                next_action="Use keeli_tasks operation update_status with status active if task is not null.",
            )
        
        elif operation == "update_status":
            if not task_id or not status:
                return _response(False, "keeli_tasks", operation, engine, error="'task_id' and 'status' required for update_status operation", code="missing_status_fields")
            if status not in {"backlog", "active", "review", "blocked", "archive"}:
                return _response(False, "keeli_tasks", operation, engine, error=f"Invalid status '{status}'. Valid: backlog, active, review, blocked, archive", code="invalid_status")
            engine.move_task(task_id, status, actor=actor, branch=branch, session_id=session_id, rationale=rationale)
            if status == "active" and session_id:
                engine.session_focus(task_id, session_id=session_id)
            state = engine.get_task_state(task_id)
            return _response(
                True,
                "keeli_tasks",
                operation,
                engine,
                data={"task_id": task_id, "status": status, "state": state},
                session_id=session_id,
                branch=branch,
                actor=actor,
                next_action="Use keeli_sessions operation checkpoint after major progress.",
            )
        
        elif operation == "update_field":
            if not task_id or not field or not value:
                return _response(False, "keeli_tasks", operation, engine, error="'task_id', 'field', and 'value' required for update_field operation", code="missing_field_update_inputs")
            _validate_field(field)
            coerced = _validate_value(value, field)
            engine.edit_task_field(task_id, field, coerced, actor=actor, branch=branch, session_id=session_id)
            state = engine.get_task_state(task_id)
            return _response(
                True,
                "keeli_tasks",
                operation,
                engine,
                data={"task_id": task_id, "field": field, "value": coerced, "state": state},
                session_id=session_id,
                branch=branch,
                actor=actor,
            )
        
        elif operation == "update_tags":
            if not task_id or not tags:
                return _response(False, "keeli_tasks", operation, engine, error="'task_id' and 'tags' required for update_tags operation", code="missing_tag_inputs")
            if not actor or not session_id:
                return _response(False, "keeli_tasks", operation, engine, error="'actor' and 'session_id' are required for update_tags to ensure auditable tag mutations", code="missing_actor_session")
            clean_tags = _normalize_and_validate_tags(_validate_value(tags, "tags"))
            if tag_operation == "add":
                engine.add_tags(task_id, clean_tags, actor=actor, branch=branch, session_id=session_id)
                state = engine.get_task_state(task_id)
                return _response(True, "keeli_tasks", operation, engine, data={"task_id": task_id, "tag_operation": tag_operation, "tags": clean_tags, "state": state}, session_id=session_id, branch=branch, actor=actor)
            elif tag_operation == "remove":
                engine.remove_tags(task_id, clean_tags, actor=actor, branch=branch, session_id=session_id)
                state = engine.get_task_state(task_id)
                return _response(True, "keeli_tasks", operation, engine, data={"task_id": task_id, "tag_operation": tag_operation, "tags": clean_tags, "state": state}, session_id=session_id, branch=branch, actor=actor)
            else:
                return _response(False, "keeli_tasks", operation, engine, error="'tag_operation' must be 'add' or 'remove'", code="invalid_tag_operation")
        
        elif operation == "conflicts":
            if not task_id:
                return _response(False, "keeli_tasks", operation, engine, error="'task_id' required for conflicts operation", code="missing_task_id")
            conflicts = engine.detect_conflicts(task_id, lookback_seconds)
            return _response(
                True,
                "keeli_tasks",
                operation,
                engine,
                data={"task_id": task_id, "lookback_seconds": lookback_seconds, "conflicts": conflicts, "count": len(conflicts)},
                session_id=session_id,
                branch=branch,
                actor=actor,
            )
        
        else:
            return _response(False, "keeli_tasks", operation, engine, error=f"Unknown operation '{operation}'. Valid: create, query, get, get_state, next, update_status, update_field, update_tags, conflicts", code="unknown_operation")

    try:
        return _retry_on_lock(_run)
    except ValueError as e:
        engine = _engine()
        return _response(False, "keeli_tasks", operation, engine, error=str(e), code="validation_error", session_id=session_id, branch=branch, actor=actor)
    except Exception as e:
        engine = _engine()
        return _response(False, "keeli_tasks", operation, engine, error=str(e), code="internal_error", session_id=session_id, branch=branch, actor=actor)


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
    author: str = None,
    include_working_memory: bool = True,
    include_knowledge: bool = False,
):
    """Unified context management tool for context operations.

    Operations:
    - get: Resolve context item via Session > Branch > Global precedence (requires key)
    - set: Set scoped context override (requires key, value)
    - digest: Get token-budgeted prompt context digest scoped to session/branch
    - fastcontext: Return compact, state-first digest with Keeli MCP announcement banner

    Scopes: session, branch, global
    Tiers: nano, brief, standard, full
    Additional digest options: include_working_memory, include_knowledge
    """
    def _format_fastcontext_result(
        digest_text: str,
        engine: KeeliEngine,
        session_id_val: str = None,
        branch_val: str = None,
        author_val: str = None,
        budget_val: int = 1200,
        tier_val: str = "brief",
    ) -> str:
        return _response(
            True,
            "keeli_context",
            "fastcontext",
            engine,
            data={
                "default_profile": "fast_low_latency",
                "overrides": ["tier", "budget", "session_id", "branch", "author"],
                "tier": tier_val,
                "budget": budget_val,
                "author": author_val or "unspecified",
                "digest": digest_text,
            },
            session_id=session_id_val,
            branch=branch_val,
            actor=author_val,
            next_action="Use keeli_tasks operation next with this scope to pick work.",
        )

    def _run():
        engine = _engine()
        if operation == "get":
            if not key:
                return _response(False, "keeli_context", operation, engine, error="'key' required for get operation", code="missing_key", session_id=session_id, branch=branch, actor=author)
            # Use provided scope_id or fall back to session_id/branch parameters
            effective_scope_id = scope_id
            if scope == "session" and not effective_scope_id:
                effective_scope_id = session_id
            elif scope == "branch" and not effective_scope_id:
                effective_scope_id = branch
            data = engine.context_get(key, session_id=effective_scope_id if scope == "session" else None, 
                                     branch=effective_scope_id if scope == "branch" else None)
            return _response(True, "keeli_context", operation, engine, data=data, session_id=session_id, branch=branch, actor=author)
        
        elif operation == "set":
            if not key or not value:
                return _response(False, "keeli_context", operation, engine, error="'key' and 'value' required for set operation", code="missing_key_value", session_id=session_id, branch=branch, actor=author)
            # Use provided scope_id or fall back to session_id/branch parameters
            effective_scope_id = scope_id
            if scope == "session" and not effective_scope_id:
                effective_scope_id = session_id
            elif scope == "branch" and not effective_scope_id:
                effective_scope_id = branch
            engine.context_set(key=key, value=value, scope=scope, scope_id=effective_scope_id, source=source)
            return _response(
                True,
                "keeli_context",
                operation,
                engine,
                data={"key": key, "scope": scope, "scope_id": effective_scope_id, "source": source},
                session_id=session_id,
                branch=branch,
                actor=author,
            )
        
        elif operation == "digest":
            result = engine.digest(
                tier=tier, 
                budget=budget, 
                session_id=session_id, 
                branch=branch,
                include_working_memory=include_working_memory,
                include_knowledge=include_knowledge
            )
            components = []
            if include_working_memory and session_id:
                components.append("working_memory")
            if include_knowledge:
                components.append("project_knowledge")
            return _response(
                True,
                "keeli_context",
                operation,
                engine,
                data={"tier": tier, "budget": budget, "includes": components, "digest": result},
                session_id=session_id,
                branch=branch,
                actor=author,
            )

        elif operation == "fastcontext":
            fast_tier = tier or "brief"
            # keeli_context has default budget=2000; fastcontext should default lower.
            fast_budget = 1200 if not budget or budget == 2000 else budget
            if fast_tier == "standard":
                fast_tier = "brief"

            resolved_branch = branch or engine._get_current_branch()
            resolved_session_id = session_id or _resolve_session_for_scope(
                engine,
                branch=resolved_branch,
                author=author,
            )

            result = engine.digest(
                tier=fast_tier,
                budget=fast_budget,
                session_id=resolved_session_id,
                branch=resolved_branch,
                include_working_memory=True,
                include_knowledge=True,
            )
            return _format_fastcontext_result(
                result,
                engine=engine,
                session_id_val=resolved_session_id,
                branch_val=resolved_branch,
                author_val=author,
                budget_val=fast_budget,
                tier_val=fast_tier,
            )
        
        else:
            return _response(False, "keeli_context", operation, engine, error=f"Unknown operation '{operation}'. Valid: get, set, digest, fastcontext", code="unknown_operation", session_id=session_id, branch=branch, actor=author)

    try:
        return _retry_on_lock(_run)
    except ValueError as e:
        engine = _engine()
        return _response(False, "keeli_context", operation, engine, error=str(e), code="validation_error", session_id=session_id, branch=branch, actor=author)
    except Exception as e:
        engine = _engine()
        return _response(False, "keeli_context", operation, engine, error=str(e), code="internal_error", session_id=session_id, branch=branch, actor=author)

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
    def _run():
        engine = _engine()
        if operation == "start":
            sid = engine.session_start(name=name, branch=branch, focus_task_id=focus_task_id)
            return _response(
                True,
                "keeli_sessions",
                operation,
                engine,
                data={"session_id": sid, "name": name, "branch": branch, "focus_task_id": focus_task_id},
                session_id=sid,
                branch=branch,
                next_action="Use keeli_context operation fastcontext with this session_id.",
            )
        
        elif operation == "focus":
            if not session_id or not focus_task_id:
                return _response(False, "keeli_sessions", operation, engine, error="'session_id' and 'focus_task_id' required for focus operation", code="missing_focus_inputs", session_id=session_id, branch=branch)
            engine.session_focus(task_id=focus_task_id, session_id=session_id)
            return _response(True, "keeli_sessions", operation, engine, data={"session_id": session_id, "focus_task_id": focus_task_id}, session_id=session_id, branch=branch)
        
        elif operation == "checkpoint":
            if not session_id:
                return _response(False, "keeli_sessions", operation, engine, error="'session_id' required for checkpoint operation", code="missing_session_id")
            engine.session_checkpoint(note=note, session_id=session_id, pending_decisions=pending_decisions)
            return _response(True, "keeli_sessions", operation, engine, data={"session_id": session_id, "note": note, "pending_decisions": pending_decisions or []}, session_id=session_id, branch=branch)
        
        elif operation == "list":
            sessions = engine.session_list()
            return _response(True, "keeli_sessions", operation, engine, data={"count": len(sessions), "sessions": sessions}, session_id=session_id, branch=branch)
        
        else:
            return _response(False, "keeli_sessions", operation, engine, error=f"Unknown operation '{operation}'. Valid: start, focus, checkpoint, list", code="unknown_operation", session_id=session_id, branch=branch)

    try:
        return _retry_on_lock(_run)
    except ValueError as e:
        engine = _engine()
        return _response(False, "keeli_sessions", operation, engine, error=str(e), code="validation_error", session_id=session_id, branch=branch)
    except Exception as e:
        engine = _engine()
        return _response(False, "keeli_sessions", operation, engine, error=str(e), code="internal_error", session_id=session_id, branch=branch)

# ── System Management Domain ──

@mcp.tool()
def keeli_system(operation: str = "sync"):
    """Unified system management tool for system operations.

    Operations:
    - sync: Reconcile physical filesystem state with database index
    - doctor: Perform health check and workspace validation

    System operations help maintain workspace integrity and consistency.
    """
    def _run():
        engine = _engine()
        if operation == "sync":
            count, corrected = engine.sync()
            return _response(True, "keeli_system", operation, engine, data={"count": count, "corrected": corrected})
        
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
            
            return _response(True, "keeli_system", operation, engine, data={"report": status_lines})
        
        else:
            return _response(False, "keeli_system", operation, engine, error=f"Unknown operation '{operation}'. Valid: sync, doctor", code="unknown_operation")

    try:
        return _retry_on_lock(_run)
    except Exception as e:
        engine = _engine()
        return _response(False, "keeli_system", operation, engine, error=str(e), code="internal_error")


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
    def _run():
        engine = _engine()
        if operation == "set":
            if not key or not value or not session_id:
                return _response(False, "keeli_memory", operation, engine, error="'key', 'value', and 'session_id' required for set operation", code="missing_memory_inputs", session_id=session_id, branch=branch)
            engine.working_memory_set(key, value, session_id, ttl_minutes)
            return _response(True, "keeli_memory", operation, engine, data={"key": key, "ttl_minutes": ttl_minutes}, session_id=session_id, branch=branch)
        
        elif operation == "get":
            if not key or not session_id:
                return _response(False, "keeli_memory", operation, engine, error="'key' and 'session_id' required for get operation", code="missing_memory_lookup_inputs", session_id=session_id, branch=branch)
            result = engine.working_memory_get(key, session_id)
            return _response(True, "keeli_memory", operation, engine, data={"key": key, "value": result}, session_id=session_id, branch=branch)
        
        elif operation == "delete":
            if not key or not session_id:
                return _response(False, "keeli_memory", operation, engine, error="'key' and 'session_id' required for delete operation", code="missing_memory_delete_inputs", session_id=session_id, branch=branch)
            engine.working_memory_delete(key, session_id)
            return _response(True, "keeli_memory", operation, engine, data={"deleted_key": key}, session_id=session_id, branch=branch)
        
        elif operation == "list":
            if not session_id:
                return _response(False, "keeli_memory", operation, engine, error="'session_id' required for list operation", code="missing_session_id", branch=branch)
            items = engine.working_memory_list(session_id)
            return _response(True, "keeli_memory", operation, engine, data={"count": len(items), "items": items}, session_id=session_id, branch=branch)
        
        elif operation == "clear_expired":
            cleared = engine.working_memory_clear_expired(session_id)
            return _response(True, "keeli_memory", operation, engine, data={"cleared": cleared}, session_id=session_id, branch=branch)
        
        elif operation == "save_analysis":
            if not analysis_type or not analysis_content:
                return _response(False, "keeli_memory", operation, engine, error="'analysis_type' and 'analysis_content' required for save_analysis operation", code="missing_analysis_inputs", session_id=session_id, branch=branch)
            result = engine.save_project_analysis(analysis_type, analysis_content, session_id, branch)
            return _response(True, "keeli_memory", operation, engine, data={"analysis_type": analysis_type, "result": result}, session_id=session_id, branch=branch)
        
        elif operation == "get_analysis":
            if not analysis_type:
                return _response(False, "keeli_memory", operation, engine, error="'analysis_type' required for get_analysis operation", code="missing_analysis_type", session_id=session_id, branch=branch)
            result = engine.get_project_analysis(analysis_type, session_id, branch)
            return _response(True, "keeli_memory", operation, engine, data={"analysis_type": analysis_type, "value": result}, session_id=session_id, branch=branch)
        
        elif operation == "get_context":
            context = engine.get_project_context()
            return _response(True, "keeli_memory", operation, engine, data=context, session_id=session_id, branch=branch)
        
        else:
            return _response(False, "keeli_memory", operation, engine, error=f"Unknown operation '{operation}'. Valid: set, get, delete, list, clear_expired, save_analysis, get_analysis, get_context", code="unknown_operation", session_id=session_id, branch=branch)

    try:
        return _retry_on_lock(_run)
    except Exception as e:
        engine = _engine()
        return _response(False, "keeli_memory", operation, engine, error=str(e), code="internal_error", session_id=session_id, branch=branch)


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
    def _run():
        engine = _engine()
        if operation == "save":
            if not knowledge_type or not content:
                return _response(False, "keeli_knowledge", operation, engine, error="'knowledge_type' and 'content' required for save operation", code="missing_knowledge_inputs", session_id=session_id, branch=branch)
            result = engine.save_project_knowledge(knowledge_type, content, source_session, tags, branch)
            return _response(True, "keeli_knowledge", operation, engine, data={"knowledge_type": knowledge_type, "result": result, "source_session": source_session, "tags": tags or []}, session_id=session_id, branch=branch)
        
        elif operation == "get":
            knowledge = engine.get_project_knowledge(knowledge_type)
            return _response(True, "keeli_knowledge", operation, engine, data={"knowledge_type": knowledge_type, "count": len(knowledge), "knowledge": knowledge}, session_id=session_id, branch=branch)
        
        elif operation == "extract":
            if not session_id:
                return _response(False, "keeli_knowledge", operation, engine, error="'session_id' required for extract operation", code="missing_session_id", branch=branch)
            knowledge = engine.extract_knowledge_from_session(session_id)
            return _response(True, "keeli_knowledge", operation, engine, data={"session_id": session_id, "knowledge": knowledge}, session_id=session_id, branch=branch)
        
        elif operation == "list":
            knowledge = engine.get_project_knowledge()
            return _response(True, "keeli_knowledge", operation, engine, data={"count": len(knowledge), "types": [k["type"] for k in knowledge]}, session_id=session_id, branch=branch)
        
        else:
            return _response(False, "keeli_knowledge", operation, engine, error=f"Unknown operation '{operation}'. Valid: save, get, extract, list", code="unknown_operation", session_id=session_id, branch=branch)

    try:
        return _retry_on_lock(_run)
    except Exception as e:
        engine = _engine()
        return _response(False, "keeli_knowledge", operation, engine, error=str(e), code="internal_error", session_id=session_id, branch=branch)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
