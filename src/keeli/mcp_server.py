import asyncio
import json
import os
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
    _INDEX_PATH, _tail, _find_project_root,
)
from keeli.templates import TASK_TEMPLATE, TASK_CHECKLISTS

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
                    "persona": {
                        "type": "string",
                        "description": "The persona assigned to the task.",
                        "enum": ["architect", "developer", "security", "author"],
                        "default": "developer"
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
                    },
                    "persona": {
                        "type": "string",
                        "description": "The persona logging the message.",
                        "enum": ["architect", "developer", "security", "author", "system"],
                        "default": "system"
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
        return [TextContent(type="text", text=f"Next task: {task_slug}\n\n{content}")]

    elif name == "keeli_complete":
        slug = arguments.get("task_slug")
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]

        task_path = _resolve_task_file(tasks_dir, slug)
        if not task_path:
            return [TextContent(type="text", text=f"Error: Task '{slug}' not found.")]

        import re
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

        task_id = _parse_task_field(content, "ID") or None
        _index_update_status(task_id, status="Completed", completed=now, archived=True)
        _append_log(f"Task completed: {slug}", task_id=task_id)

        await _mcp_log("info", f"Task completed and archived: {slug} [{task_id}]")
        return [TextContent(type="text", text=f"Marked {slug} as Completed and archived → archive/{task_path.name}.")]

    elif name == "keeli_start":
        title = arguments.get("title")
        priority = arguments.get("priority", "P1")
        persona = arguments.get("persona", "developer")
        depends_on = arguments.get("depends_on", "")
        
        slug = _slugify(title)
        task_path = tasks_dir / f"{slug}.md"
        
        if task_path.exists():
            return [TextContent(type="text", text=f"Error: Task {slug} already exists.")]
            
        checklist = TASK_CHECKLISTS.get(persona, TASK_CHECKLISTS["developer"])
        task_id = _allocate_id("task", slug, root)

        content = TASK_TEMPLATE.format(
            title=title,
            task_id=task_id,
            priority=priority,
            timestamp=_now_iso(),
            depends_on=depends_on,
            context_note="",
            persona=f"@{persona}",
            checklist=checklist,
        )

        task_path.write_text(content)
        _append_log(f"Created task: {slug}", task_id=task_id)

        await _mcp_log("info", f"Task created: {slug} [{task_id}] priority={priority}")
        return [TextContent(type="text", text=f"Successfully created task {slug} [{task_id}].")]

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
            return [TextContent(type="text", text=f"Analysis for {task_path.name}:\n{hints_block}")]
        if _START in task_text:
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
        if hints["persona"]:
            summary_parts.append(f"Suggested persona: @{hints['persona']}")
        return [TextContent(type="text", text="\n".join(summary_parts))]

    elif name == "keeli_log":
        message = arguments.get("message")
        persona = arguments.get("persona", "system")

        log_path = docs_dir / "ai_log.md"
        if not log_path.exists():
            return [TextContent(type="text", text="Error: ai_log.md not found.")]

        _append_log(message)
        return [TextContent(type="text", text="Successfully appended to ai_log.md.")]

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
            return [TextContent(type="text", text=f"ID match for {query_upper}:\n{result}")]

        q_lower = query.lower()
        kw_matches = [
            i for i in items
            if q_lower in i.get("title", "").lower() or q_lower in i.get("slug", "").lower()
        ]
        if status_filter:
            kw_matches = [i for i in kw_matches if i.get("status", "").lower() == status_filter.lower()]

        if not kw_matches:
            return [TextContent(type="text", text=f"No results for '{query}'.")]
        return [TextContent(type="text", text=f"Keyword results for '{query}':\n{json.dumps(kw_matches, indent=2)}")]

    elif name == "keeli_history":
        task_id = arguments.get("task_id", "").strip().upper()
        log_file = docs_dir / "ai_log.md"
        if not log_file.exists():
            return [TextContent(type="text", text="Error: ai_log.md not found.")]

        lines = log_file.read_text().splitlines()
        matches = [line for line in lines if task_id in line.upper()]
        if not matches:
            return [TextContent(type="text", text=f"No log entries found for '{task_id}'.")]
        return [TextContent(type="text", text=f"History for {task_id} ({len(matches)} entries):\n" + "\n".join(matches))]

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
        return [TextContent(type="text", text=f"{output}\n\n~{used} tokens (budget: {budget})")]

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
        return [TextContent(type="text", text=f"Archived '{slug}' → archive/{task_path.name}")]

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