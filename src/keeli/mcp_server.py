"""
Keeli MCP Server — Thin wrapper around Keeli CLI.
Provides task management tools to LLM agents.
"""

import os
import subprocess
import sys
import json
from mcp.server import Server
from mcp.types import Tool, TextContent, EmbeddedResource, Resource

# Initialize FastMCP-style or standard MCP server
# For simplicity, we use the standard MCP server pattern from the requirements
app = Server("keeli")

def run_keeli(*args):
    """Run keeli CLI with robust error handling and timeout."""
    cmd = [sys.executable, "-m", "keeli.main"] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd()
        )
        if result.returncode != 0:
            return f"Error (code {result.returncode}):\n{result.stderr or result.stdout}"
        return result.stdout
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error: {str(e)}"

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="keeli_next",
            description="Get the next task to work on based on priority and age.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="keeli_get",
            description="Get details of a specific task by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The task ID (e.g., T-0001)"}
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="keeli_start",
            description="Create a new task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "string", "enum": ["p0", "p1", "p2"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "description": {"type": "string"},
                    "depends_on": {"type": "string"}
                },
                "required": ["title"]
            }
        ),
        Tool(
            name="keeli_progress",
            description="Mark a task as In Progress.",
            inputSchema={
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"]
            }
        ),
        Tool(
            name="keeli_complete",
            description="Mark a task as Completed.",
            inputSchema={
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"]
            }
        ),
        Tool(
            name="keeli_list",
            description="List tasks by status.",
            inputSchema={
                "type": "object",
                "properties": {"status": {"type": "string"}},
            }
        ),
        Tool(
            name="keeli_digest",
            description="Get a token-budgeted context snapshot.",
            inputSchema={
                "type": "object",
                "properties": {
                    "budget": {"type": "integer", "default": 2000},
                    "tier": {"type": "string", "enum": ["nano", "brief", "standard", "full"], "default": "standard"}
                },
            }
        ),
        Tool(
            name="keeli_doctor",
            description="Check health of Keeli directories and index.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="keeli_sync",
            description="Explicitly rebuild the task index from Markdown files.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="keeli_configure_copilot",
            description="Get instructions for setting up Keeli as a Copilot Skill.",
            inputSchema={"type": "object", "properties": {}}
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "keeli_next":
        res = run_keeli("next")
    elif name == "keeli_get":
        tid = arguments.get("task_id")
        # For keeli_get, we use keeli find or direct file read, but let's assume we implement 'get' in main.py
        res = run_keeli("get", tid)
    elif name == "keeli_start":
        args = [arguments["title"]]
        if "priority" in arguments: args.extend(["--priority", arguments["priority"]])
        if "tags" in arguments: args.extend(["--tags"] + arguments["tags"])
        if "description" in arguments: args.extend(["--description", arguments["description"]])
        if "depends_on" in arguments: args.extend(["--depends-on", arguments["depends_on"]])
        res = run_keeli("start", *args)
    elif name == "keeli_progress":
        res = run_keeli("progress", arguments["task_id"])
    elif name == "keeli_complete":
        res = run_keeli("complete", arguments["task_id"])
    elif name == "keeli_list":
        status = arguments.get("status")
        args = ["list"]
        if status: args.extend(["--status", status])
        res = run_keeli(*args)
    elif name == "keeli_digest":
        budget = arguments.get("budget", 2000)
        tier = arguments.get("tier", "standard")
        res = run_keeli("digest", "--budget", str(budget), "--tier", tier)
    elif name == "keeli_doctor":
        res = run_keeli("doctor")
    elif name == "keeli_sync":
        res = run_keeli("sync")
    elif name == "keeli_configure_copilot":
        res = run_keeli("configure-copilot")
    else:
        res = f"Unknown tool: {name}"

    return [TextContent(type="text", text=res)]

def main():
    from mcp.server.stdio import stdio_server
    import asyncio
    
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    
    asyncio.run(run())

if __name__ == "__main__":
    main()
