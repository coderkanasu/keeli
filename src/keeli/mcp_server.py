import asyncio
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListResourcesRequest,
    ListResourcesResult,
    ListToolsRequest,
    ListToolsResult,
    Resource,
    Tool,
    TextContent,
)

from keeli.main import (
    _get_next_task, _slugify, _now_iso, _write_file,
    _score_task, _format_hints_block, _build_corpus,
    _load_index, _allocate_id, _index_update_status,
    _parse_task_field, _resolve_task_file, _append_log,
    _db_log_event, _db_sync_task_file,
    _INDEX_PATH, _tail, _find_project_root, _git_output,
    _HINTS_MARKER_START,
)
from keeli.templates import TASK_TEMPLATE
from keeli import query as kquery

# ── HATEOAS: next-action suggestions ──────────────────────────────────────────
# Each entry is a callable: ctx dict → list of {tool, args, why} dicts.
# ctx carries runtime values resolved during the tool call (slug, task_id, …).
# The sentinel string "<slug>" / "<title>" signals the LLM must supply the value.

_NEXT_ACTIONS: dict[str, Any] = {
    "keeli_start": lambda ctx: [
        {
            "tool": "keeli_analyze",
            "args": {"task_slug": ctx.get("slug", "<slug>")},
            "why":  "Inject AI context hints (relevant skills + ADRs) into the new task before starting work.",
        },
        {
            "tool": "keeli_log",
            "args": {"message": f"@architect | Task created: {ctx.get('slug','<slug>')}", "persona": "architect"},
            "why":  "Append a timestamped entry to the audit log.",
        },
    ],
    "keeli_analyze": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Check the next highest-priority task.",
        },
    ],
    "keeli_complete": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Pick up the next highest-priority task immediately.",
        },
        {
            "tool": "keeli_digest",
            "args": {"budget": 2000},
            "why":  "Refresh the context snapshot so the next session starts clean.",
        },
    ],
    "keeli_next": lambda ctx: [
        {
            "tool": "keeli_analyze",
            "args": {"task_slug": ctx.get("slug", "<slug>")},
            "why":  "Inject relevant skills/ADRs into this task before starting.",
        },
        {
            "tool": "keeli_start",
            "args": {"title": "<title>", "priority": "P1", "persona": "developer"},
            "why":  "Create a new task if you need to capture new work.",
        },
    ],
    "keeli_log": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Continue with the next task after logging.",
        },
        {
            "tool": "keeli_digest",
            "args": {"budget": 2000},
            "why":  "Get a full token-budgeted context snapshot.",
        },
    ],
    "keeli_find": lambda ctx: [
        {
            "tool": "keeli_history",
            "args": {"task_id": ctx.get("id", "<task-id>")},
            "why":  "Show the full audit trail (all ai_log entries) for this item.",
        },
        {
            "tool": "keeli_analyze",
            "args": {"task_slug": ctx.get("slug", "<slug>")},
            "why":  "Inject AI context hints into the found task.",
        },
    ],
    "keeli_history": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Resume work on the next priority task.",
        },
        {
            "tool": "keeli_digest",
            "args": {"budget": 1000},
            "why":  "Get a compact context snapshot (1 k-token budget).",
        },
    ],
    "keeli_digest": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Pick up the top-priority task shown in the digest.",
        },
        {
            "tool": "keeli_analyze",
            "args": {"task_slug": "<slug>"},
            "why":  "Inject AI context hints into a specific task from the backlog.",
        },
    ],
    "keeli_archive_task": lambda ctx: [
        {
            "tool": "keeli_next",
            "args": {},
            "why":  "Find the next task to work on after archiving.",
        },
    ],
}


CACHE_BASE = Path.home() / ".keeli_workspace_cache"

def _sha256_prefix(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _workspace_namespace_dir() -> Path:
    root = _find_project_root()
    name = root.name
    namespace = f"workspace_{name}_{_sha256_prefix(str(root.resolve()))}"
    path = CACHE_BASE / namespace
    path.mkdir(parents=True, exist_ok=True)
    return path


def _find_module_root(active_file_path: str, workspace_root: Path) -> Path:
    path = Path(active_file_path)
    if not path.is_absolute():
        path = (workspace_root / path).resolve()
    if not path.exists():
        path = workspace_root

    for parent in [path] + list(path.parents):
        if parent == workspace_root or parent == workspace_root.parent:
            break
        for manifest in ("package.json", "pom.xml", "go.mod", "Cargo.toml", "pyproject.toml", "setup.py"):
            if (parent / manifest).exists():
                return parent
    return workspace_root


def _module_namespace_dir(active_file_path: str) -> Path:
    workspace_dir = _workspace_namespace_dir()
    workspace_root = _find_project_root()
    module_root = _find_module_root(active_file_path, workspace_root)
    namespace = f"module_{module_root.name}_{_sha256_prefix(str(module_root.resolve()))}"
    path = workspace_dir / namespace
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_cache_dirs(active_file_path: Optional[str] = None) -> tuple[Path, Path]:
    workspace_dir = _workspace_namespace_dir()
    if active_file_path:
        module_dir = _module_namespace_dir(active_file_path)
    else:
        module_dir = workspace_dir
    return workspace_dir, module_dir


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


def _write_wal_event(cache_dir: Path, event: dict[str, Any]) -> None:
    event = {**event, "timestamp": _now_iso()}
    wal_path = cache_dir / "telemetry.wal"
    wal_path.parent.mkdir(parents=True, exist_ok=True)
    with wal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def _lexicon_path(cache_dir: Path) -> Path:
    if cache_dir.name.startswith("workspace_"):
        return cache_dir / "shared_lexicon.json"
    return cache_dir / "lexicon.json"


def _load_lexicon(cache_dir: Path) -> dict[str, Any]:
    return _json_load(_lexicon_path(cache_dir), {})


def _save_lexicon(cache_dir: Path, data: dict[str, Any]) -> None:
    _json_write(_lexicon_path(cache_dir), data)


def _find_namespace_key(cache_dir: Path) -> str:
    return cache_dir.name


def _state_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS mcp_session_state (namespace TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )


def _set_mcp_state(namespace: str, state: str) -> None:
    db_path = _find_project_root() / "keeli_state.db"
    conn = sqlite3.connect(db_path)
    try:
        _state_table(conn)
        conn.execute(
            "INSERT OR REPLACE INTO mcp_session_state(namespace, state, updated_at) VALUES (?, ?, ?)",
            (namespace, state, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def _get_mcp_state(namespace: str) -> Optional[str]:
    db_path = _find_project_root() / "keeli_state.db"
    conn = sqlite3.connect(db_path)
    try:
        _state_table(conn)
        row = conn.execute(
            "SELECT state FROM mcp_session_state WHERE namespace = ?",
            (namespace,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _parse_pascal_case_terms(text: str) -> list[str]:
    multi_segment = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-zA-Z0-9]+)+\b", text)
    service_names = re.findall(
        r"\b[A-Z][a-zA-Z0-9]+(?:Service|Manager|Client|Controller|Repo|Repository)\b",
        text,
    )
    terms = set(multi_segment) | set(service_names)
    stopwords = {
        "The", "A", "An", "In", "On", "For", "With", "To", "From",
        "And", "Or", "But", "If", "Then", "Else", "This", "That",
        "These", "Those", "It", "Its", "By", "As", "At", "Of",
    }
    return [term for term in terms if term not in stopwords]


def _resolve_term(term: str, module_dir: Path, workspace_dir: Path) -> Optional[dict[str, Any]]:
    module_lexicon = _load_lexicon(module_dir)
    if term in module_lexicon and not module_lexicon[term].get("tombstone"):
        return module_lexicon[term]
    workspace_lexicon = _load_lexicon(workspace_dir)
    if term in workspace_lexicon and not workspace_lexicon[term].get("tombstone"):
        return workspace_lexicon[term]
    return None


def _sanitize_raw_source_text(raw_source_text: str) -> str:
    sanitized = re.sub(r"<[^>]{1,200}>", "", raw_source_text)
    lower = sanitized.lower()
    for marker in ("system:", "[inst]", "### instruction"):
        if marker in lower:
            raise ValueError("POTENTIAL_INJECTION")
    if len(sanitized) > 4096:
        raise ValueError("TRUNCATED")
    return sanitized


def _extract_workflow_entries(file_path: Path, commit_sha: str, scope: str) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    in_code = False
    root = _find_project_root().resolve()
    source_rel = None
    try:
        source_rel = str(file_path.resolve().relative_to(root))
    except ValueError:
        source_rel = str(file_path.resolve())

    with file_path.open("r", encoding="utf-8") as handle:
        for lineno, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            cleaned = None
            if line.lstrip().startswith("#"):
                cleaned = line.lstrip("# ")
            elif line.lstrip().startswith("-") or line.lstrip().startswith("*"):
                cleaned = line.lstrip("-* \t")
            if not cleaned:
                continue
            cleaned = cleaned.strip()
            if not cleaned:
                continue
            entry = {
                "statement": cleaned,
                "source_file": source_rel,
                "line_range": f"{lineno}-{lineno}",
                "verified_by_commit": commit_sha,
                "integrity_hash": hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
                "scope": scope,
            }
            entries.append(entry)
    overflow = 0
    if len(entries) > 30:
        overflow = len(entries) - 30
        entries = entries[:30]
    return entries, overflow


def _workspace_map_path(module_dir: Path) -> Path:
    return module_dir / "workspace.map"


def _load_workspace_map(module_dir: Path) -> dict[str, Any]:
    return _json_load(_workspace_map_path(module_dir), {})


def _lexicon_store_path(cache_dir: Path) -> Path:
    return _lexicon_path(cache_dir)


def _workflow_store_path(cache_dir: Path) -> Path:
    return cache_dir / "workflows.json"


def _load_workflows(cache_dir: Path) -> list[dict[str, Any]]:
    return _json_load(_workflow_store_path(cache_dir), [])


def _save_workflows(cache_dir: Path, entries: list[dict[str, Any]]) -> None:
    _json_write(_workflow_store_path(cache_dir), entries)


def _normalize_active_file_path(active_file_path: str) -> Path:
    candidate = Path(active_file_path)
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    return candidate


def _make_namespace(active_file_path: str) -> str:
    workspace_dir, module_dir = _resolve_cache_dirs(active_file_path)
    return f"{workspace_dir.name}:{module_dir.name}"


def _ensure_cache_roots(active_file_path: Optional[str] = None) -> tuple[Path, Path]:
    workspace_dir = _workspace_namespace_dir()
    module_dir = _module_namespace_dir(active_file_path or str(workspace_dir))
    return workspace_dir, module_dir


def _persist_state(active_file_path: str, state: str) -> None:
    namespace = _make_namespace(active_file_path)
    _set_mcp_state(namespace, state)


def _current_state(active_file_path: str) -> Optional[str]:
    namespace = _make_namespace(active_file_path)
    return _get_mcp_state(namespace)


def _with_next(text: str, tool_name: str, ctx: "dict | None" = None) -> str:
    """Append a HATEOAS '## ⛓ Suggested Next Actions' block to a tool response.

    The block contains:
      - A machine-readable JSON array (``tool``, ``args``, ``why``) that an
        LLM agent can parse and call directly.
      - A human-readable bullet list for developers reading raw output.

    Args:
        text:      The primary tool response text.
        tool_name: The name of the tool that just executed.
        ctx:       Runtime context (slug, task_id, …) used to pre-fill args.
    """
    ctx = ctx or {}
    factory = _NEXT_ACTIONS.get(tool_name)
    if factory is None:
        return text
    try:
        actions: list[dict] = factory(ctx)
    except Exception:
        return text  # never break a response for the sake of hints
    if not actions:
        return text

    bullet_lines = "\n".join(
        f"  - **{a['tool']}**({json.dumps(a['args'])})  — {a['why']}"
        for a in actions
    )
    json_block = json.dumps(actions, indent=2)
    suffix = (
        f"\n\n---\n## ⛓ Suggested Next Actions\n"
        f"```json\n{json_block}\n```\n\n"
        f"**Or pick one:**\n{bullet_lines}"
    )
    return text + suffix


# Initialize the MCP server
app = Server("keeli-mcp")

# Helper to get the workspace root
def get_workspace_root() -> Path:
    """Return the project root by walking up from cwd to find docs/project.md."""
    return _find_project_root()

@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available Keeli documentation resources."""
    root = get_workspace_root()
    resources = []
    
    docs_dir = root / "docs"
    if not docs_dir.exists():
        return resources

    # Add core docs
    for doc_name in ["project.md", "decision.md", "ai_log.md", "skills.md"]:
        doc_path = docs_dir / doc_name
        if doc_path.exists():
            resources.append(
                Resource(
                    uri=f"file://{doc_path.absolute()}",
                    name=f"Keeli {doc_name}",
                    description=f"The {doc_name} file for the current Keeli project.",
                    mimeType="text/markdown",
                )
            )
            
    # Add tasks
    tasks_dir = docs_dir / "tasks"
    if tasks_dir.exists():
        for task_file in tasks_dir.glob("*.md"):
            resources.append(
                Resource(
                    uri=f"file://{task_file.absolute()}",
                    name=f"Task: {task_file.name}",
                    description=f"Keeli task file: {task_file.name}",
                    mimeType="text/markdown",
                )
            )

    return resources

@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read a specific Keeli resource."""
    if not uri.startswith("file://"):
        raise ValueError(f"Unsupported URI scheme: {uri}")
        
    path = Path(uri[7:])
    if not path.exists():
        raise ValueError(f"Resource not found: {path}")
        
    return path.read_text()

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Keeli tools."""
    return [
        Tool(
            name="keeli_next",
            description="Get the next task to work on based on priority and age.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="keeli_complete",
            description="Mark a task as completed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "The slug of the task to complete (e.g., 'add-login')."
                    }
                },
                "required": ["task_slug"],
            },
        ),
        Tool(
            name="keeli_progress",
            description="Mark a task as In Progress. Fails if the Objective section is empty.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "The slug of the task (e.g., 'add-login')."
                    }
                },
                "required": ["task_slug"],
            },
        ),
        Tool(
            name="keeli_start",
            description="Create a new task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title of the task."
                    },
                    "priority": {
                        "type": "string",
                        "description": "The priority of the task (P0, P1, P2).",
                        "enum": ["P0", "P1", "P2"],
                        "default": "P1"
                    },
                    "depends_on": {
                        "type": "string",
                        "description": "Comma-separated list of task slugs this task depends on."
                    }
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="keeli_analyze",
            description=(
                "Analyze a task using TF-IDF to find relevant skills and ADRs from the "
                "project corpus, then inject an AI Context Hints block into the task file. "
                "Uses scikit-learn if available, otherwise pure-Python TF-IDF."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "The slug (or prefix) of the task to analyze."
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, return hints without writing to the task file.",
                        "default": False
                    },
                },
                "required": ["task_slug"],
            },
        ),
        Tool(
            name="keeli_log",
            description="Append a message to the AI log.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to log."
                    }
                },
                "required": ["message"],
            },
        ),
        Tool(
            name="keeli_find",
            description="Search the task index by exact ID (e.g. T-0003) or keyword across title/slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Exact task ID (T-0001) or keyword to search."
                    },
                    "status": {
                        "type": "string",
                        "description": "Optional status filter (e.g. 'Backlog', 'In Progress', 'Completed')."
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="keeli_get",
            description="Get a single task by ID or slug. Returns full task details including tags, required skills, and affects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID (e.g., 'T-0001') or slug (e.g., 'add-login-form')."
                    }
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="keeli_search",
            description="Full-text search across task titles and context notes. Fast alternative to keeli_find for natural language queries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text to match against task titles and context."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 20, max 100).",
                        "default": 20
                    }
                },
                "required": ["query"],
            },
        ),

        Tool(
            name="keeli_history",
            description="Return all ai_log entries that mention a specific task ID or keyword.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID (e.g. T-0003) or keyword to filter log entries."
                    }
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="keeli_digest",
            description=(
                "Return a token-budgeted context snapshot: active tasks, project overview, "
                "backlog, recent completions, and recent log lines."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "budget": {
                        "type": "integer",
                        "description": "Target token budget (default 2000).",
                        "default": 2000
                    }
                },
            },
        ),
        Tool(
            name="keeli_archive_task",
            description="Move a task file to docs/tasks/archive/ without marking it as completed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_slug": {
                        "type": "string",
                        "description": "The slug of the task to archive."
                    }
                },
                "required": ["task_slug"],
            },
        ),













    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a Keeli tool."""
    # ── S-3: acquire session for notifications (safe — no-ops outside request) ──
    try:
        _session = app.request_context.session
        _progress_token = (arguments or {}).get("_meta", {}).get("progressToken")
    except LookupError:
        _session = None
        _progress_token = None

    async def _mcp_log(level: str, data: str) -> None:
        """Emit a LoggingMessageNotification if a session is active."""
        if _session is not None:
            await _session.send_log_message(level=level, data=data)

    async def _emit_progress(progress: float, total: float, message: str = "") -> None:
        """Emit a ProgressNotification if a progress token was supplied."""
        if _session is not None and _progress_token is not None:
            await _session.send_progress_notification(
                progress_token=_progress_token,
                progress=progress,
                total=total,
                message=message,
            )

    root = get_workspace_root()
    docs_dir = root / "docs"
    tasks_dir = docs_dir / "tasks"

    if not docs_dir.exists():
        return [TextContent(type="text", text="Error: Not a Keeli project. Run 'keeli init' first.")]

    if name == "keeli_next":
        task_path, task_slug = _get_next_task()
        if not task_path:
            return [TextContent(type="text", text="No tasks available. All tasks are complete or blocked.")]

        content = task_path.read_text()
        enhanced_output = f"""Next task: {task_slug}

{content}"""
        return [TextContent(type="text", text=_with_next(enhanced_output, "keeli_next", {"slug": task_slug}))]

    elif name == "keeli_complete":
        slug = arguments.get("task_slug")
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        task_path = _resolve_task_file(tasks_dir, slug)
        if not task_path:
            return [TextContent(type="text", text=f"Error: Task '{slug}' not found.")]

        content = task_path.read_text()
        for old_status in ("In Progress", "Backlog", "Review", "Blocked"):
            content = content.replace(f"**Status:** {old_status}", "**Status:** Completed")
        now = _now_iso()
        content = re.sub(r"\*\*Completed:\*\*.*", f"**Completed:** {now}", content)
        task_path.write_text(content)

        # Auto-archive
        archive_dir = tasks_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        dest = archive_dir / task_path.name
        task_path.rename(dest)
        _db_sync_task_file(dest)

        task_id = _parse_task_field(content, "ID") or None
        _index_update_status(task_id, status="Completed", completed=now, archived=True)
        _append_log(f"Task completed: {slug}", task_id=task_id)
        _db_log_event(task_id, "completed", actor="mcp", details=slug)
        transition_events = [{"type": "completed", "task_id": task_id, "slug": slug}]

        await _mcp_log("info", f"Task completed and archived: {slug} [{task_id}]")
        result_text = f"Marked {slug} as Completed and archived → archive/{task_path.name}.\n\nTransition events:\n```json\n{json.dumps(transition_events, indent=2)}\n```"
        return [TextContent(type="text", text=_with_next(result_text, "keeli_complete", {"slug": slug}))]

    elif name == "keeli_progress":
        slug = arguments.get("task_slug", "").strip()
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        task_path = _resolve_task_file(tasks_dir, slug)
        if not task_path:
            return [TextContent(type="text", text=f"Error: Task '{slug}' not found.")]

        content = task_path.read_text()
        current = _parse_task_field(content, "Status")
        if current.lower() == "in progress":
            return [TextContent(type="text", text=f"Task '{slug}' is already In Progress.")]

        content = re.sub(r"\*\*Status:\*\*.*", "**Status:** In Progress", content)
        task_path.write_text(content)
        _db_sync_task_file(task_path)
        task_id = _parse_task_field(content, "ID") or None
        _index_update_status(task_id, status="In Progress")
        _append_log(f"Task started: {slug}", task_id=task_id)
        _db_log_event(task_id, "in_progress", actor="mcp", details=slug)
        transition_events = [{"type": "in_progress", "task_id": task_id, "slug": slug}]
        await _mcp_log("info", f"Task marked In Progress: {slug}")
        result_text = f"Marked {slug} as In Progress.\n\nTransition events:\n```json\n{json.dumps(transition_events, indent=2)}\n```"
        return [TextContent(type="text", text=_with_next(result_text, "keeli_progress", {"slug": slug}))]

    elif name == "keeli_start":
        title = arguments.get("title")
        priority = arguments.get("priority", "P1")
        persona = arguments.get("persona", "developer")
        depends_on = arguments.get("depends_on", "")
        epic = arguments.get("epic", "")
        story = arguments.get("story", "")
        objective = arguments.get("objective", "")

        slug = _slugify(title)
        task_path = tasks_dir / f"{slug}.md"

        if task_path.exists():
            return [TextContent(type="text", text=f"Error: Task {slug} already exists.")]

        task_id = _allocate_id("task", title, slug, priority=priority, epic=epic or None, story=story or None)

        content = TASK_TEMPLATE.format(
            title=title,
            task_id=task_id,
            priority=priority,
            timestamp=_now_iso(),
            depends_on=depends_on,
            context_note="",
            epic=epic,
            story=story,
            tags="",
            requires_skills="",
            affects="",
            what=objective or "<!-- Be specific about the implementation work. -->",
            why="<!-- Explain the user or business impact. -->",
            acceptance="<!-- Add verification steps or test evidence here. -->",
            evidence="<!-- Link delivery artifacts (PR, commit, docs, screenshots, build logs). -->",
            verification="<!-- Link validation artifacts (tests, checks, commands with outcomes). -->",
        )

        task_path.write_text(content)
        _db_sync_task_file(task_path)
        _append_log(f"Created task: {slug}", task_id=task_id)
        _db_log_event(task_id, "created", actor=persona, details=title)

        await _mcp_log("info", f"Task created: {slug} [{task_id}] priority={priority}")
        return [TextContent(type="text", text=_with_next(f"Successfully created task {slug} [{task_id}].", "keeli_start", {"slug": slug, "task_id": task_id}))]

    elif name == "keeli_analyze":
        slug = arguments.get("task_slug")
        dry_run = arguments.get("dry_run", False)
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        candidates = sorted(tasks_dir.glob(f"{slug}*.md"))
        if not candidates:
            return [TextContent(type="text", text=f"Error: No task matching '{slug}' in docs/tasks/")]
        task_path = candidates[0]
        task_text = task_path.read_text()

        # S-1: coarse-grained progress (4 steps: load → corpus → score → format/inject)
        await _emit_progress(0, 4, f"Loading task: {task_path.name}")
        try:
            await _emit_progress(1, 4, "Building corpus (skills, ADRs, tasks)…")
            hints = _score_task(task_text)
            await _emit_progress(2, 4, f"Scored {len(hints.get('skills', []))} skill(s), {len(hints.get('adrs', []))} ADR(s)")
            hints_block = _format_hints_block(hints)
            await _emit_progress(3, 4, "Hints formatted")
        except Exception as exc:
            return [TextContent(type="text", text=f"Error during analysis: {exc}")]

        if dry_run:
            await _emit_progress(4, 4, "Done (dry-run)")
            return [TextContent(type="text", text=_with_next(f"Analysis for {task_path.name}:\n{hints_block}", "keeli_analyze", {"slug": slug}))]
        if _HINTS_MARKER_START in task_text:
            pat = r"\n---\n\n## AI Context Hints.*?" + re.escape("<!-- KEELI_HINTS_END -->")
            new_text = re.sub(pat, hints_block, task_text, flags=re.DOTALL)
        else:
            new_text = task_text.rstrip() + "\n" + hints_block + "\n"
        task_path.write_text(new_text)

        summary_parts = [f"Hints injected into {task_path.name}"]
        if hints["skills"]:
            summary_parts.append(f"Skills: {', '.join(m['name'] for _, m in hints['skills'])}")
        if hints["adrs"]:
            summary_parts.append(f"ADRs: {', '.join(m['ref'] for _, m in hints['adrs'])}")
        return [TextContent(type="text", text=_with_next("\n".join(summary_parts), "keeli_analyze", {"slug": slug}))]

    elif name == "keeli_log":
        message = arguments.get("message")
        persona = arguments.get("persona", "system")

        log_path = docs_dir / "ai_log.md"
        if not log_path.exists():
            return [TextContent(type="text", text="Error: ai_log.md not found.")]

        _append_log(message)
        return [TextContent(type="text", text=_with_next("Successfully appended to ai_log.md.", "keeli_log", {}))]

    elif name == "keeli_find":
        query = arguments.get("query", "").strip()
        status_filter = arguments.get("status")

        if not _INDEX_PATH.exists():
            return [TextContent(type="text", text="Index not found. Create tasks first.")]

        index = _load_index()
        items = index.get("items", [])
        query_upper = query.upper()

        id_matches = [i for i in items if i.get("id", "").upper() == query_upper]
        if id_matches:
            result = json.dumps(id_matches, indent=2)
            return [TextContent(type="text", text=_with_next(f"ID match for {query_upper}:\n{result}", "keeli_find", {"id": query_upper}))]

        q_lower = query.lower()
        kw_matches = [
            i for i in items
            if q_lower in i.get("title", "").lower() or q_lower in i.get("slug", "").lower()
        ]
        if status_filter:
            kw_matches = [i for i in kw_matches if i.get("status", "").lower() == status_filter.lower()]

        if not kw_matches:
            return [TextContent(type="text", text=f"No results for '{query}'.")]
        return [TextContent(type="text", text=_with_next(f"Keyword results for '{query}':\n{json.dumps(kw_matches, indent=2)}", "keeli_find", {}))]

    elif name == "keeli_get":
        task_id = arguments.get("task_id", "").strip()
        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required.")]
        
        # Try ID lookup first, then slug
        task_dict = kquery.query_task_by_id(task_id) or kquery.query_task_by_slug(task_id)
        
        if not task_dict:
            return [TextContent(type="text", text=f"Error: Task '{task_id}' not found.")]
        
        result = json.dumps(task_dict, indent=2)
        return [TextContent(type="text", text=f"Task {task_dict['item_id']}:\n{result}")]

    elif name == "keeli_search":
        query_text = arguments.get("query", "").strip()
        limit = min(arguments.get("limit", 20), 100)  # Cap at 100
        
        if not query_text:
            return [TextContent(type="text", text="Error: query is required.")]
        
        results = kquery.search_tasks(query_text, limit=limit)
        
        if not results:
            return [TextContent(type="text", text=f"No tasks match '{query_text}'.")]
        
        result_json = json.dumps(results, indent=2)
        return [TextContent(type="text", text=f"Found {len(results)} task(s) matching '{query_text}':\n{result_json}")]

    elif name == "keeli_history":
        task_id = arguments.get("task_id", "").strip().upper()
        log_file = docs_dir / "ai_log.md"
        if not log_file.exists():
            return [TextContent(type="text", text="Error: ai_log.md not found.")]

        lines = log_file.read_text().splitlines()
        matches = [line for line in lines if task_id in line.upper()]
        if not matches:
            return [TextContent(type="text", text=f"No log entries found for '{task_id}'.")]
        return [TextContent(type="text", text=_with_next(f"History for {task_id} ({len(matches)} entries):\n" + "\n".join(matches), "keeli_history", {"id": task_id}))]

    elif name == "keeli_digest":
        budget: int = arguments.get("budget", 2000)
        sections: list[str] = []
        used = 0

        def _tokens(text: str) -> int:
            return int(len(text.split()) * 1.35)

        def _fits(text: str) -> bool:
            return used + _tokens(text) <= budget

        # Active tasks
        if tasks_dir.exists():
            active_lines: list[str] = []
            for tf in sorted(tasks_dir.glob("*.md")):
                if tf.name == ".gitkeep":
                    continue
                text = tf.read_text()
                status = _parse_task_field(text, "Status").lower()
                if status in ("in progress", "blocked"):
                    tid = _parse_task_field(text, "ID") or "—"
                    title = text.splitlines()[0].lstrip("# ").strip()
                    active_lines.append(f"- [{tid}] {title} ({status})")
            if active_lines:
                sec = "## Active\n" + "\n".join(active_lines)
                sections.append(sec)
                used += _tokens(sec)
                await _mcp_log("info", f"[digest] Active tasks: {len(active_lines)} item(s) (~{_tokens(sec)} tokens)")

        # Project overview
        project = docs_dir / "project.md"
        if project.exists():
            first5 = "\n".join(project.read_text().splitlines()[:5])
            sec = f"## Project\n{first5}"
            if _fits(sec):
                sections.append(sec)
                used += _tokens(sec)
                await _mcp_log("info", f"[digest] Project section added (~{_tokens(sec)} tokens)")

        # Backlog from index
        if _INDEX_PATH.exists():
            index = _load_index()
            backlog = [
                i for i in index.get("items", [])
                if i.get("status", "").lower() == "backlog" and not i.get("archived")
            ]
            backlog.sort(key=lambda i: (i.get("priority", "P2"), i.get("created", "")))
            lines = [f"- [{i['id']}] [{i['priority']}] {i['title']}" for i in backlog[:10]]
            if lines:
                sec = "## Backlog (top 10)\n" + "\n".join(lines)
                if _fits(sec):
                    sections.append(sec)
                    used += _tokens(sec)

        # Recent log
        log_file = docs_dir / "ai_log.md"
        if log_file.exists():
            tail = _tail(log_file, n=10)
            sec = f"## Recent Log\n```\n{tail}\n```"
            if _fits(sec):
                sections.append(sec)
                used += _tokens(sec)
                await _mcp_log("info", f"[digest] Log section added (~{_tokens(sec)} tokens)")

        await _mcp_log("info", f"[digest] Complete: {len(sections)} section(s), ~{used}/{budget} tokens used")
        output = "\n\n".join(sections) if sections else "No Keeli context found."
        return [TextContent(type="text", text=_with_next(f"{output}\n\n~{used} tokens (budget: {budget})", "keeli_digest", {}))]

    elif name == "keeli_archive_task":
        slug = arguments.get("task_slug")
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        task_path = _resolve_task_file(tasks_dir, slug)
        if not task_path:
            return [TextContent(type="text", text=f"Error: Task '{slug}' not found.")]

        if task_path.parent.name == "archive":
            return [TextContent(type="text", text=f"Task '{slug}' is already archived.")]

        archive_dir = tasks_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        dest = archive_dir / task_path.name
        task_path.rename(dest)

        content = dest.read_text()
        task_id = _parse_task_field(content, "ID") or None
        _index_update_status(task_id, archived=True)
        _append_log(f"Archived task: {slug}", task_id=task_id)

        await _mcp_log("info", f"Task archived: {slug}")
        return [TextContent(type="text", text=_with_next(f"Archived '{slug}' → archive/{task_path.name}", "keeli_archive_task", {"slug": slug}))]

    else:
        return [TextContent(type="text", text=f"Error: Unknown tool {name}")]

async def run_stdio():
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

def run_sse(port: int = 8000):
    """Run the MCP server over HTTP/SSE."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from mcp.server.sse import SseServerTransport

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await app.run(
                streams[0], streams[1], app.create_initialization_options()
            )

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    starlette_app = Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ],
    )

    print(f"Starting Keeli MCP Server on http://localhost:{port}/sse")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)

def main(transport: str = "stdio", port: int = 8000):
    """Entry point for the MCP server."""
    if transport == "sse":
        run_sse(port)
    else:
        asyncio.run(run_stdio())

if __name__ == "__main__":
    import sys
    transport = "sse" if "--sse" in sys.argv else "stdio"
    main(transport=transport)