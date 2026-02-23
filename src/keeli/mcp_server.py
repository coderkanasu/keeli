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
)
from keeli.templates import TASK_TEMPLATE, TASK_CHECKLISTS

# Initialize the MCP server
app = Server("keeli-mcp")

# Helper to get the workspace root
def get_workspace_root() -> Path:
    return Path.cwd()

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
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a Keeli tool."""
    root = get_workspace_root()
    docs_dir = root / "docs"
    tasks_dir = docs_dir / "tasks"
    
    if not docs_dir.exists():
        return [TextContent(type="text", text="Error: Not a Keeli project. Run 'keeli init' first.")]

    if name == "keeli_next":
        task = _get_next_task(tasks_dir)
        if not task:
            return [TextContent(type="text", text="No tasks available. All tasks are complete or blocked.")]
        
        task_path = tasks_dir / task
        content = task_path.read_text()
        return [TextContent(type="text", text=f"Next task: {task}\n\n{content}")]

    elif name == "keeli_complete":
        slug = arguments.get("task_slug")
        if not slug:
            return [TextContent(type="text", text="Error: task_slug is required.")]
            
        task_path = tasks_dir / f"{slug}.md"
        if not task_path.exists():
            return [TextContent(type="text", text=f"Error: Task {slug} not found.")]
            
        content = task_path.read_text()
        content = content.replace("**Status:** In Progress", "**Status:** Completed")
        content = content.replace("**Status:** Backlog", "**Status:** Completed")
        content = content.replace("**Status:** Review", "**Status:** Completed")
        
        # Update completion time if not already set
        if "**Completed:** —" in content or "**Completed:** \n" in content or "**Completed:**\n" in content:
            import re
            content = re.sub(r"\*\*Completed:\*\*.*", f"**Completed:** {_now_iso()}", content)
            
        task_path.write_text(content)
        
        # Log it
        log_path = docs_dir / "ai_log.md"
        if log_path.exists():
            with open(log_path, "a") as f:
                f.write(f"{_now_iso()} | @developer | Completed task: {slug}\n")
                
        return [TextContent(type="text", text=f"Successfully marked {slug} as Completed.")]

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
        
        content = TASK_TEMPLATE.format(
            title=title,
            priority=priority,
            timestamp=_now_iso(),
            depends_on=depends_on,
            context_note="",
            persona=f"@{persona}",
            checklist=checklist,
        )
        
        task_path.write_text(content)
        
        # Log it
        log_path = docs_dir / "ai_log.md"
        if log_path.exists():
            with open(log_path, "a") as f:
                f.write(f"{_now_iso()} | @architect | Created task: {slug}\n")
                
        return [TextContent(type="text", text=f"Successfully created task {slug}.")]

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

        try:
            hints = _score_task(task_text)
            hints_block = _format_hints_block(hints)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error during analysis: {exc}")]

        if dry_run:
            return [TextContent(type="text", text=f"Analysis for {task_path.name}:\n{hints_block}")]

        import re
        _START = "<!-- KEELI_HINTS_START -->"
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
            
        with open(log_path, "a") as f:
            f.write(f"{_now_iso()} | @{persona} | {message}\n")
            
        return [TextContent(type="text", text="Successfully appended to ai_log.md.")]

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